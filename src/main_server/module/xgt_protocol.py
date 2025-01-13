import asyncio
import copy
import datetime
import logging
import multiprocessing as mp
import time
import traceback

from collections import deque
from logging import Logger
from src.main_server.module.communication_module import number_to_bytes, bytes_to_number, deviceDataConversion
from src.main_server.module.logger import get_logger, LoggerPrint
from src.main_server.module.tcp_socket.tcp_socket_module import TcpSocketModule
from src.main_server.module.thread_with_exception import ThreadWithException


# 헤더 데이터 생성
def create_header_data(length):
    header_data = b'LSIS-XGT\x00\x00\x00\x00\x00\x33\x00\x00'
    header_data += number_to_bytes(length, 2)  # 데이터 크기
    header_data += b'\x00\x00'
    return header_data


# 쓰기 명령 데이터 생성
def create_write_data(word_devices, word_datas, dword_devices, dword_datas, bit_devices, bit_datas):
    block_count = len(word_devices) + len(dword_devices)
    write_data = b'\x58\x00\x02\x00\x00\x00'  # 명령어 / 데이터 타입 / 예약 영역
    write_data += number_to_bytes(block_count, 2)  # 블록 수

    # 변수 영역
    for device_name in word_devices:
        device = f"%{device_name[0]}W{device_name[1:]}"
        write_data += number_to_bytes(len(device), 2)    # 변수 길이
        write_data += device.encode()                      # 변수명
    for device_name in dword_devices:
        device = f"%{device_name[0]}D{device_name[1:]}"
        write_data += number_to_bytes(len(device), 2)
        write_data += device.encode()
    for device_name in bit_devices:
        device = f"%{device_name[0]}X{device_name[1:]}"
        write_data += number_to_bytes(len(device), 2)
        write_data += device.encode()

    # 데이터 영역
    for word_data in word_datas:
        write_data += number_to_bytes(2, 2)     # 데이터 개수
        write_data += number_to_bytes(word_data, 2)      # 데이터
    for dword_data in dword_datas:
        write_data += number_to_bytes(4, 2)     # 데이터 개수
        write_data += number_to_bytes(dword_data, 4)      # 데이터
    for bit_data in bit_datas:
        write_data += number_to_bytes(1, 2)             # 데이터 개수
        write_data += number_to_bytes(bit_data, 1)      # 데이터

    return create_header_data(len(write_data)) + write_data


# 읽기 명령 데이터 생성
def create_read_data(word_devices, dword_flag=False):
    block_count = len(word_devices)
    read_data = b'\x54\x00'
    read_data += b'\x02' if dword_flag is False else b'\x03'
    read_data += b'\x00\x00\x00'  # 명령어 / 데이터 타입 / 예약 영역
    read_data += number_to_bytes(block_count, 2)  # 블록 수

    # 변수 영역
    for device_name in word_devices:
        device = f"%{device_name[0]}W{device_name[1:]}"
        read_data += number_to_bytes(len(device), 2)    # 변수 길이
        read_data += device.encode()                      # 변수명
    return create_header_data(len(read_data)) + read_data


# bit 읽기 명령 데이터 생성
def create_bit_read_data(bit_devices):
    block_count = len(bit_devices)
    read_data = b'\x54\x00'
    read_data += b'\x00'
    read_data += b'\x00\x00\x00'  # 명령어 / 데이터 타입 / 예약 영역
    read_data += number_to_bytes(block_count, 2)  # 블록 수

    # 변수 영역
    for device_name in bit_devices:
        device = f"%{device_name[0]}X{device_name[1:]}"
        read_data += number_to_bytes(len(device), 2)    # 변수 길이
        read_data += device.encode()                      # 변수명
    return create_header_data(len(read_data)) + read_data


# 수신 데이터 파싱
def recv_data_parser(data):
    # 헤더 영역
    header_area = data[0:20]
    company_id = header_area[0:8]
    reserved = header_area[8:10]
    plc_info = header_area[10:12]
    cpu_info = header_area[12:13]
    source_of_frame = header_area[13:14]
    invoke_id = header_area[14:16]
    length = header_area[16:18]
    fenet_position = header_area[18:19]
    reserved2 = header_area[19:20]

    # 데이터 영역
    data_area = data[20:]
    command = data_area[0:2]
    data_type = data_area[2:4]
    if command == b'\x55\x00':
        return read_response_parser(data_area)
    elif command == b'\x59\x00':
        return write_response_parser(data_area)
    else:
        raise Exception(f"올바르지않은 데이터")


# 읽기 응답 데이터 파싱
def read_response_parser(data):
    command = data[0:2]
    data_type = data[2:4]
    reserved_area = data[4:6]
    error_stata = data[6:8]

    if error_stata != b'\x00\x00':
        # 에러일 경우
        error_code = bytes_to_number(data[8:9])
        raise Exception(f"Error Code: {error_code}")
    block_count = bytes_to_number(data[8:10])
    recv_data_list = []

    start_index = 10
    end_index = 10
    for i in range(block_count):
        start_index = end_index
        data_size = bytes_to_number(data[start_index:start_index + 2])
        end_index = start_index + 2 + data_size

        recv_data = bytes_to_number(data[start_index + 2:end_index])
        recv_data_list.append(recv_data)
    return recv_data_list


# 쓰기 응답 데이터 파싱
def write_response_parser(data):
    command = data[0:2]
    data_type = data[2:4]
    reserved_area = data[4:6]
    error_stata = data[6:8]

    if error_stata != b'\x00\x00':
        # 에러일 경우
        error_code = bytes_to_number(data[8:9])
        raise Exception(f"Error Code: {error_code}")


class XgtProtocol:
    # 생성자
    def __init__(self, program_name: str = 'xgt_protocol',
                 xgt_protocol_param: dict = {}, device_types: dict = {}, device_data_info: dict = {},
                 send_queue: mp.Queue = mp.Queue(), recv_queue: mp.Queue = mp.Queue(),
                 logger: logging.Logger = None, stop_event = mp.Event()):
        # 변수 선언
        self.stop_event: mp.Event =  stop_event # 프로그램 종료 여부
        self.data_buffer: bytes = bytes()
        self.data_index: int = 0
        self.task_list: list = []

        self.send_queue: mp.Queue = send_queue
        self.recv_queue: mp.Queue = recv_queue

        # TCP 소켓 통신 관련 변수
        ip_address: str = xgt_protocol_param.get('ip_address', "localhost")   # IP 주소
        port: int = xgt_protocol_param.get('port', 4000)   # 포트 번호
        socket_timeout: int = xgt_protocol_param.get('socket_timeout', 5)   # -1 = None = blocking mode | 0 이상 = non-blocking mode
        socket_timeout = None if socket_timeout == -1 else socket_timeout
        receive_timeout: int = xgt_protocol_param.get('receive_timeout', 0)
        server_flag: bool = False
        cycle_time: float = xgt_protocol_param.get('cycle_time', 0.1)  # 통신 주기
        bind_ip: str = xgt_protocol_param.get("bind_ip")
        self.max_device_count = 16
        self.send_cycle: datetime.timedelta = datetime.timedelta(seconds=cycle_time)  # 보낼 사이클 시간 (단위: 초)

        # 시리얼 통신 및 로거 설정
        self.socket_name: str = program_name
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger

        # 상태 관련 변수
        self.connect_flag: bool | None = None  # 연결 정보
        self.socket_pre_connect_flag: bool = False  # 이전 소켓 연결 여부
        self.send_time: datetime.datetime = datetime.datetime.now()  # 보낸 시간
        self.write_time: datetime.datetime = datetime.datetime.now()   # 쓴 시간
        self.init_recv_flag: bool = False  # 최초 연결 시 강제 읽기 여부

        self.device_types: dict = device_types
        read_device_types: dict = device_types.get('read', {})
        read_word_device_info: dict = read_device_types.get('word', {})
        read_dword_device_info: dict = read_device_types.get('dword', {})
        read_bit_device_info: dict = read_device_types.get('bit', {})

        write_device_types: dict = device_types.get('write', {})
        self.write_word_device_type: dict = write_device_types.get('word', {})
        self.write_dword_device_type: dict = write_device_types.get('dword', {})
        self.write_bit_device_type: dict = write_device_types.get('bit', {})

        self.send_update_data: dict = {}  # 보낼 데이터
        self.pre_send_update_data: dict = {}  # 이전 보낸 데이터

        self.pre_send_update_word_data: dict = {}  # 이전 보낸 Word 데이터
        self.pre_send_update_dword_data: dict = {}  # 이전 보낸 DWord 데이터
        self.pre_send_update_bit_data: dict = {}  # 이전 보낸 Bit 데이터

        self.pre_send_update_raw_word_data: dict = {}  # 이전 보낸 원본 Word 데이터
        self.pre_send_update_raw_dword_data: dict = {}  # 이전 보낸 원본 DWord 데이터
        self.pre_send_update_raw_bit_data: dict = {}  # 이전 보낸 원본 Bit 데이터

        self.recv_update_data: deque = deque()  # 받은 데이터
        self.pre_received_update_word_data: dict = {}  # 이전 받은 Word 데이터
        self.pre_received_update_dword_data: dict = {}  # 이전 받은 DWord 데이터
        self.pre_received_update_bit_data: dict = {}   # 이전 받은 Bit 데이터
        self.pre_received_update_data: dict = {}   # 이전 받은 데이터

        ##########################################################
        # 쓰기 디바이스 타입 정의
        ##########################################################
        write_device_info: dict = device_data_info.get('write', {})
        write_word_device_info: dict = write_device_info.get('word', {})
        write_dword_device_info: dict = write_device_info.get('dword', {})

        self.write_word_device_name: dict = {}
        for device, device_info in write_word_device_info.items():
            if type(device_info) is dict:
                for index, device_info_data in device_info.items():
                    self.write_word_device_name[device_info_data] = {
                        "device": device,
                        "index": index
                    }
            else:
                self.write_word_device_name[device_info] = {
                    "device": device
                }

        self.write_dword_device_name: dict = {}
        for device, device_info in write_dword_device_info.items():
            if type(device_info) is dict:
                for index, device_info_data in device_info.items():
                    self.write_dword_device_name[device_info_data] = {
                        "device": device,
                        "index": index
                    }
            else:
                self.write_dword_device_name[device_info] = {
                    "device": device
                }
        self.read_device_info = device_data_info.get('read', {})
        ##########################################################

        ##########################################################
        # 읽을 디바이스 개수 정의
        ##########################################################
        read_word_devices = read_word_device_info.keys()
        read_dword_devices = read_dword_device_info.keys()
        read_bit_devices = read_bit_device_info.keys()
        self.read_devices: list = []
        device_count: int = 0
        devices_info: dict = {
            'word': [],
            'dword': [],
            'bit': []
        }
        for _device in read_word_devices:
            if device_count >= self.max_device_count:
                self.read_devices.append(copy.deepcopy(devices_info))
                devices_info['word'].clear()
                devices_info['dword'].clear()
                devices_info['bit'].clear()
                device_count = 1
            else:
                device_count += 1
            devices_info['word'].append(_device)
        for _device in read_dword_devices:
            if device_count >= self.max_device_count:
                self.read_devices.append(copy.deepcopy(devices_info))
                devices_info['word'].clear()
                devices_info['dword'].clear()
                devices_info['bit'].clear()
                device_count = 1
            else:
                device_count += 1
            devices_info['dword'].append(_device)
        for _device in read_bit_devices:
            if device_count >= self.max_device_count:
                self.read_devices.append(copy.deepcopy(devices_info))
                devices_info['word'].clear()
                devices_info['dword'].clear()
                devices_info['bit'].clear()
                device_count = 1
            else:
                device_count += 1
            devices_info['bit'].append(_device)

        if len(devices_info['word']) != 0 or len(devices_info['dword']) != 0 or len(devices_info['bit']) != 0:
            self.read_devices.append(copy.deepcopy(devices_info))
        del devices_info
        ##########################################################

        self.socket_module = TcpSocketModule(
            socket_name=self.socket_name,
            ip_address=ip_address,
            port=port,
            server_flag=server_flag,
            socket_timeout=socket_timeout,
            receive_timeout=receive_timeout,
            bind_ip=bind_ip,
            logger=self.logger)

        # 수신 프로세스 실행
        self.socket_data_process_thread = ThreadWithException(self.socket_data_process)
        self.socket_data_process_thread.start()

        # 통신 프로세스 실행
        self.comm_process_thread = ThreadWithException(self.thread_comm_process)
        self.comm_process_thread.start()

    # 소멸자
    def __del__(self):
        self.close()

    def close(self):
        self.socket_module.finallyCloseTCP()
        self.socket_data_process_thread.raise_exception()
        self.comm_process_thread.raise_exception()
        self.logger.info("프로그램 종료")

    # 프로세스 시작
    async def run_process(self):
        # 보낼 데이터 처리
        # self.task_list.append(asyncio.create_task(self.socket_data_process()))
        self.task_list.append(asyncio.create_task(self.recv_process()))
        self.task_list.append(asyncio.create_task(self.send_process()))
        # self.task_list.append(asyncio.create_task(self.comm_process()))

        for task_item in self.task_list:
            await task_item

    def socket_data_process(self):
        while not self.stop_event.is_set():
            self.socket_module.socketDataProcess()
            time.sleep(0.01)
            # await asyncio.sleep(0.01)

    # 송신 처리 프로세스
    async def send_process(self):
        while self.stop_event.is_set() is False:
            # 프로그램 종료할때까지 동작
            try:
                while self.send_queue.qsize() != 0:
                    # 보낼 데이터가 들어있을 경우
                    try:
                        send_dict: dict = self.send_queue.get()
                        data_type: str = send_dict.get("type")
                        if data_type == "send":
                            data_dict: dict = send_dict.get("data")
                            self.send_update_process(data_dict)
                        elif data_type == "disable":
                            if send_dict.get("data") is True:
                                self.socket_module.socket_send_queue.put(bytes(2))
                            else:
                                self.socket_module.socket_send_queue.put(bytes(3))
                        elif data_type == "reconnect":
                            self.socket_module.socket_send_queue.put(bytes(0))
                        elif data_type == "exit":
                            self.close()
                            break
                    except Exception as e:
                        print(traceback.format_exc())
                        self.logger.warning(f'Exception: {e}\n{traceback.format_exc()}')

                now_time = datetime.datetime.now()
                time_diff = now_time - self.write_time
                if time_diff >= datetime.timedelta(seconds=5):
                    self.all_write()
                    self.write_time = now_time
                self.send_connect_state()
            except Exception as e:
                print(traceback.format_exc())
                self.logger.warning(f'Exception: {e}\n{traceback.format_exc()}')
            await asyncio.sleep(0.01)

    # 전체 쓰기 (5초마다 업데이트)
    def all_write(self):
        self.send_update_data.update(self.pre_send_update_data)

    # 받은 데이터 받기
    async def get_recv_data(self, send_data):
        # 받은 데이터 초기화
        self.socket_module.data_buffer.clear()

        request_flag: bool = False
        start_time: datetime.datetime = datetime.datetime.now()
        while self.stop_event.is_set() is False and self.socket_module.connect_flag is True:
            # 데이터 전송
            if request_flag is False:
                self.socket_module.socket_send_queue.put(send_data)
                request_flag = True

            if len(self.socket_module.data_buffer) != 0:
                recv_data: any = self.socket_module.data_buffer.popleft()
                self.socket_module.data_buffer.clear()  # 받은 데이터 초기화
                return recv_data_parser(recv_data)

            now_time: datetime.datetime = datetime.datetime.now()
            if now_time - start_time >= datetime.timedelta(seconds=2):
                raise TimeoutError(f"{self.socket_name} TimeoutError")
            await asyncio.sleep(0.01)
        raise Exception(f"{self.socket_name} not connect")

    def get_recv_data_thread(self, send_data):
        # 받은 데이터 초기화
        self.socket_module.data_buffer.clear()

        request_flag: bool = False
        start_time: datetime.datetime = datetime.datetime.now()
        while self.stop_event.is_set() is False and self.socket_module.connect_flag is True:
            # 데이터 전송
            if request_flag is False:
                self.socket_module.socket_send_queue.put(send_data)
                request_flag = True

            if len(self.socket_module.data_buffer) != 0:
                recv_data: any = self.socket_module.data_buffer.popleft()
                self.socket_module.data_buffer.clear()  # 받은 데이터 초기화
                return recv_data_parser(recv_data)

            now_time: datetime.datetime = datetime.datetime.now()
            if now_time - start_time >= datetime.timedelta(seconds=1):
                raise TimeoutError(f"{self.socket_name} TimeoutError")
            time.sleep(0.01)
        raise Exception(f"{self.socket_name} not connect")

    def thread_comm_process(self):
        write_read_device_types: dict = self.device_types.get('write', {})
        write_word_device_types: dict = write_read_device_types.get('word', {})
        write_dword_device_types: dict = write_read_device_types.get('dword', {})

        while self.stop_event.is_set() is False:
            if self.socket_module.connect_flag is True and (datetime.datetime.now() - self.send_time) >= self.send_cycle:
                try:
                    ##########################
                    #       송신 파트
                    ##########################
                    if len(self.send_update_data) != 0:
                        # 보낼 데이터가 존재한다면

                        send_update_word_data: dict = {}  # 보낼 Word 데이터
                        send_update_dword_data: dict = {}  # 보낼 DWord 데이터
                        send_update_bit_data: dict = {}  # 보낼 Bit 데이터

                        log_send_update_word_data: dict = {}  # 보낼 Word 로그 데이터
                        log_send_update_dword_data: dict = {}  # 보낼 DWord 로그 데이터
                        log_send_update_bit_data: dict = {}  # 보낼 Bit 로그 데이터

                        for data_name in list(self.send_update_data.keys()):
                            data_value = self.send_update_data.pop(data_name)
                            device_info = self.write_word_device_name.get(data_name)
                            if device_info is not None:
                                # word 타입일 경우
                                device = device_info.get("device")
                                index = device_info.get("index")
                                if index is not None:
                                    # index가 존재할 경우 bool 형태
                                    pre_data = send_update_word_data.get(device)
                                    if pre_data is None:
                                        pre_data = self.pre_send_update_word_data.get(device)
                                        if pre_data is None:
                                            pre_data = [False] * 16
                                    pre_data[index] = data_value
                                    send_update_word_data[device] = pre_data
                                else:
                                    # index가 존재하지않다면 raw 그대로 사용
                                    send_update_word_data[device] = data_value
                                # 로그 기록
                                if log_send_update_word_data.get(device) is None:
                                    log_send_update_word_data[device] = {}
                                log_send_update_word_data[device][data_name] = data_value

                            device_info = self.write_dword_device_name.get(data_name)
                            if device_info is not None:
                                # dword 타입일 경우
                                device = device_info.get("device")
                                index = device_info.get("index")
                                if index is not None:
                                    # index가 존재할 경우 bool 형태
                                    pre_data = send_update_dword_data.get(device)
                                    if pre_data is None:
                                        pre_data = self.pre_send_update_dword_data.get(device)
                                        if pre_data is None:
                                            pre_data = [False] * 32
                                    pre_data[index] = data_value
                                    send_update_dword_data[device] = pre_data[index]
                                else:
                                    # index가 존재하지않다면 raw 그대로 사용
                                    send_update_dword_data[device] = data_value
                                # 로그 기록
                                if log_send_update_dword_data.get(device) is None:
                                    log_send_update_dword_data[device] = {}
                                log_send_update_dword_data[device][data_name] = data_value

                        while len(send_update_word_data) != 0 or len(send_update_dword_data) != 0:
                            send_count: int = 0
                            try:
                                # 보낼 데이터가 있을 경우
                                send_word_devices: list = []
                                send_word_raw_datas: list = []
                                for _device in list(send_update_word_data.keys()):
                                    if send_count >= self.max_device_count:
                                        break
                                    else:
                                        send_count += 1
                                    _value: any = send_update_word_data.pop(_device)
                                    conversion_data = deviceDataConversion(_value,
                                                                           device_type=write_word_device_types.get(
                                                                               _device, 'short'),
                                                                           conversion_type='short')
                                    send_word_devices.append(_device)
                                    send_word_raw_datas.append(conversion_data)

                                    pre_data = self.pre_send_update_raw_word_data.get(_device, "")
                                    if pre_data != conversion_data:
                                        self.logger.info(
                                            f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_word_data.get(_device, '')})")
                                        self.pre_send_update_raw_word_data[_device] = conversion_data
                                        self.pre_send_update_word_data[_device] = _value

                                send_dword_devices: list = []
                                send_dword_raw_datas: list = []
                                for _device in send_update_dword_data.keys():
                                    if send_count >= self.max_device_count:
                                        break
                                    else:
                                        send_count += 1
                                    _value: any = send_update_dword_data.pop(_device)
                                    conversion_data = deviceDataConversion(_value,
                                                                           device_type=write_dword_device_types.get(
                                                                               _device, 'int'),
                                                                           conversion_type='int')
                                    send_dword_devices.append(_device)
                                    send_dword_raw_datas.append(conversion_data)

                                    pre_data = self.pre_send_update_raw_dword_data.get(_device, "")
                                    if pre_data != conversion_data:
                                        self.logger.info(
                                            f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_dword_data.get(_device, '')})")
                                        self.pre_send_update_raw_dword_data[_device] = conversion_data
                                        self.pre_send_update_dword_data[_device] = _value

                                send_bit_devices: list = []
                                send_bit_raw_datas: list = []
                                for _device in send_update_bit_data.keys():
                                    if send_count >= self.max_device_count:
                                        break
                                    else:
                                        send_count += 1
                                    _value: any = send_update_bit_data.pop(_device)
                                    conversion_data = int(_value)
                                    send_bit_devices.append(_device)
                                    send_bit_raw_datas.append(conversion_data)

                                    pre_data = self.pre_send_update_raw_bit_data.get(_device, "")
                                    if pre_data != conversion_data:
                                        self.logger.info(
                                            f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_bit_data.get(_device, '')})")
                                        self.pre_send_update_raw_bit_data[_device] = conversion_data
                                        self.pre_send_update_bit_data[_device] = _value

                                request_write_data = create_write_data(
                                    send_word_devices, send_word_raw_datas, send_dword_devices, send_dword_raw_datas, send_bit_devices, send_bit_raw_datas)
                                # self.socket_module.socket_send_queue.put(write_data)
                                self.get_recv_data_thread(request_write_data)
                            except Exception as e:
                                print(traceback.format_exc())
                                # self.logger.warning('송신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
                                raise Exception('송신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
                                # raise Exception('송신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))

                    ##########################
                    #       수신 파트
                    ##########################
                    try:
                        for read_device in self.read_devices:
                            read_word_devices: list = read_device.get('word', [])
                            read_dword_devices: list = read_device.get('dword', [])
                            read_bit_devices: list = read_device.get('bit', [])

                            read_word_datas = []
                            read_dword_datas = []
                            read_bit_datas = []
                            if len(read_word_devices) != 0:
                                request_word_data = create_read_data(read_word_devices)
                                # self.socket_module.socket_send_queue.put(read_word_data)
                                read_word_datas = self.get_recv_data_thread(request_word_data)
                            if len(read_dword_devices) != 0:
                                request_dword_data = create_read_data(read_dword_devices, True)
                                # self.socket_module.socket_send_queue.put(read_dword_data)
                                read_dword_datas = self.get_recv_data_thread(request_dword_data)
                            if len(read_bit_devices) != 0:
                                request_bit_data = create_bit_read_data(read_bit_datas)
                                # self.socket_module.socket_send_queue.put(read_dword_data)
                                read_bit_datas = self.get_recv_data_thread(request_bit_data)
                            # len_read_word_devices = len(read_word_devices)
                            # for i in range(len(recv_datas)):
                            #     if i >= len_read_word_devices:
                            #         # 인덱스가 word 디바이스 크기보다 클 경우 dword에 저장
                            #         read_dword_datas.append(recv_datas[i])
                            #     else:
                            #         read_word_datas.append(recv_datas[i])
                            self.recv_update_data.append(
                                (read_word_devices, read_word_datas, read_dword_devices, read_dword_datas, read_bit_devices, read_bit_datas)
                            )
                    except Exception as e:
                        print(traceback.format_exc())
                        # self.logger.warning('수신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
                        raise Exception('수신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
                    self.send_time = datetime.datetime.now()
                except Exception as e:
                    print(traceback.format_exc())
                    self.logger.warning(e)
                    # self.socket_module.closeTCP()
            time.sleep(0.01)

    # 통신 프로세스
    # async def comm_process(self):
    #     write_read_device_types: dict = self.device_types.get('write', {})
    #     write_word_device_types: dict = write_read_device_types.get('word', {})
    #     write_dword_device_types: dict = write_read_device_types.get('dword', {})
    #
    #     while self.stop_event.is_set() is False:
    #         if self.socket_module.connect_flag is True and (datetime.datetime.now() - self.send_time) >= self.send_cycle:
    #             try:
    #                 ##########################
    #                 #       송신 파트
    #                 ##########################
    #                 if len(self.send_update_data) != 0:
    #                     # 보낼 데이터가 존재한다면
    #
    #                     send_update_word_data: dict = {}  # 보낼 Word 데이터
    #                     send_update_dword_data: dict = {}  # 보낼 DWord 데이터
    #
    #                     log_send_update_word_data: dict = {}  # 보낼 Word 로그 데이터
    #                     log_send_update_dword_data: dict = {}  # 보낼 DWord 로그 데이터
    #
    #                     for data_name in list(self.send_update_data.keys()):
    #                         data_value = self.send_update_data.pop(data_name)
    #                         device_info = self.write_word_device_name.get(data_name)
    #                         if device_info is not None:
    #                             # word 타입일 경우
    #                             device = device_info.get("device")
    #                             index = device_info.get("index")
    #                             if index is not None:
    #                                 # index가 존재할 경우 bool 형태
    #                                 pre_data = send_update_word_data.get(device)
    #                                 if pre_data is None:
    #                                     pre_data = self.pre_send_update_word_data.get(device)
    #                                     if pre_data is None:
    #                                         pre_data = [False] * 16
    #                                 pre_data[index] = data_value
    #                                 send_update_word_data[device] = pre_data
    #                             else:
    #                                 # index가 존재하지않다면 raw 그대로 사용
    #                                 send_update_word_data[device] = data_value
    #                             # 로그 기록
    #                             if log_send_update_word_data.get(device) is None:
    #                                 log_send_update_word_data[device] = {}
    #                             log_send_update_word_data[device][data_name] = data_value
    #
    #                         device_info = self.write_dword_device_name.get(data_name)
    #                         if device_info is not None:
    #                             # dword 타입일 경우
    #                             device = device_info.get("device")
    #                             index = device_info.get("index")
    #                             if index is not None:
    #                                 # index가 존재할 경우 bool 형태
    #                                 pre_data = send_update_dword_data.get(device)
    #                                 if pre_data is None:
    #                                     pre_data = self.pre_send_update_dword_data.get(device)
    #                                     if pre_data is None:
    #                                         pre_data = [False] * 32
    #                                 pre_data[index] = data_value
    #                                 send_update_dword_data[device] = pre_data[index]
    #                             else:
    #                                 # index가 존재하지않다면 raw 그대로 사용
    #                                 send_update_dword_data[device] = data_value
    #                             # 로그 기록
    #                             if log_send_update_dword_data.get(device) is None:
    #                                 log_send_update_dword_data[device] = {}
    #                             log_send_update_dword_data[device][data_name] = data_value
    #
    #                     while len(send_update_word_data) != 0 or len(send_update_dword_data) != 0:
    #                         send_count: int = 0
    #                         try:
    #                             # 보낼 데이터가 있을 경우
    #                             send_word_devices: list = []
    #                             send_word_raw_datas: list = []
    #                             for _device in list(send_update_word_data.keys()):
    #                                 if send_count >= self.max_device_count:
    #                                     break
    #                                 else:
    #                                     send_count += 1
    #                                 _value: any = send_update_word_data.pop(_device)
    #                                 conversion_data = deviceDataConversion(_value,
    #                                                                        device_type=write_word_device_types.get(_device, 'short'),
    #                                                                        conversion_type='short')
    #                                 send_word_devices.append(_device)
    #                                 send_word_raw_datas.append(conversion_data)
    #
    #                                 pre_data = self.pre_send_update_raw_word_data.get(_device, "")
    #                                 if pre_data != conversion_data:
    #                                     self.logger.info(f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_word_data.get(_device, '')})")
    #                                     self.pre_send_update_raw_word_data[_device] = conversion_data
    #                                     self.pre_send_update_word_data[_device] = _value
    #
    #                             send_dword_devices: list = []
    #                             send_dword_raw_datas: list = []
    #                             for _device in send_update_dword_data.keys():
    #                                 if send_count >= self.max_device_count:
    #                                     break
    #                                 else:
    #                                     send_count += 1
    #                                 _value: any = send_update_dword_data.pop(_device)
    #                                 conversion_data = deviceDataConversion(_value,
    #                                                                        device_type=write_dword_device_types.get(_device, 'int'),
    #                                                                        conversion_type='int')
    #                                 send_dword_devices.append(_device)
    #                                 send_dword_raw_datas.append(conversion_data)
    #
    #                                 pre_data = self.pre_send_update_raw_dword_data.get(_device, "")
    #                                 if pre_data != conversion_data:
    #                                     self.logger.info(f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_dword_data.get(_device, '')})")
    #                                     self.pre_send_update_raw_dword_data[_device] = conversion_data
    #                                     self.pre_send_update_dword_data[_device] = _value
    #
    #                             request_write_data = create_write_data(
    #                                 send_word_devices, send_word_raw_datas, send_dword_devices, send_dword_raw_datas)
    #                             # self.socket_module.socket_send_queue.put(write_data)
    #                             await self.get_recv_data(request_write_data)
    #                         except Exception as e:
    #                             print(traceback.format_exc())
    #                             self.logger.warning('송신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
    #                             # raise Exception('송신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
    #
    #                 ##########################
    #                 #       수신 파트
    #                 ##########################
    #                 try:
    #                     for read_device in self.read_devices:
    #                         read_word_devices: list = read_device.get('word', [])
    #                         read_dword_devices: list = read_device.get('dword', [])
    #
    #                         read_word_datas = []
    #                         read_dword_datas = []
    #                         if len(read_word_devices) != 0:
    #                             request_word_data = create_read_data(read_word_devices)
    #                             # self.socket_module.socket_send_queue.put(read_word_data)
    #                             read_word_datas = await self.get_recv_data(request_word_data)
    #                         if len(read_dword_devices) != 0:
    #                             request_dword_data = create_read_data(read_dword_devices, True)
    #                             # self.socket_module.socket_send_queue.put(read_dword_data)
    #                             read_dword_datas = await self.get_recv_data(request_dword_data)
    #                         # len_read_word_devices = len(read_word_devices)
    #                         # for i in range(len(recv_datas)):
    #                         #     if i >= len_read_word_devices:
    #                         #         # 인덱스가 word 디바이스 크기보다 클 경우 dword에 저장
    #                         #         read_dword_datas.append(recv_datas[i])
    #                         #     else:
    #                         #         read_word_datas.append(recv_datas[i])
    #                         self.recv_update_data.append(
    #                             (read_word_devices, read_word_datas, read_dword_devices, read_dword_datas)
    #                         )
    #                 except Exception as e:
    #                     print(traceback.format_exc())
    #                     self.logger.warning('수신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
    #                     # raise Exception('수신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))
    #                 self.send_time = datetime.datetime.now()
    #             except Exception as e:
    #                 print(traceback.format_exc())
    #                 self.logger.warning(e)
    #                 # self.socket_module.closeTCP()
    #         await asyncio.sleep(0.01)

    # 수신 처리 프로세스
    async def recv_process(self):
        read_device_types: dict = self.device_types.get('read', {})
        read_word_device_types: dict = read_device_types.get('word', {})
        read_dword_device_types: dict = read_device_types.get('dword', {})

        word_device_info: dict = self.read_device_info.get('word', {})
        dword_device_info: dict = self.read_device_info.get('dword', {})
        bit_device_info: dict = self.read_device_info.get('bit', {})

        all_read_time: datetime.datetime = datetime.datetime.now()   # 전체 읽은 시간

        while self.stop_event.is_set() is False:
            try:
                while len(self.recv_update_data) != 0:
                    # =======================================
                    # 5초마다 강제 읽기
                    now_time = datetime.datetime.now()
                    all_read_flag = False
                    if now_time - all_read_time >= datetime.timedelta(seconds=5):
                        all_read_time = now_time
                        all_read_flag = True

                    if self.init_recv_flag is False:
                        all_read_flag = True
                        self.init_recv_flag = True
                    # =======================================
                    read_data: dict = {}

                    read_word_devices, read_word_raw_datas, read_dword_devices, read_dword_raw_datas, read_bit_devices, read_bit_datas = self.recv_update_data.popleft()

                    ##########################
                    #       WORD 파트
                    ##########################
                    if (read_word_raw_datas is not None and read_dword_raw_datas is not None and
                            len(read_word_devices) == len(read_word_raw_datas) and
                            len(read_dword_devices) == len(read_dword_raw_datas)):
                        for i in range(len(read_word_devices)):
                            _device: str = read_word_devices[i]
                            pre_data: int | str = self.pre_received_update_word_data.get(_device)
                            now_data: int = read_word_raw_datas[i]

                            if pre_data is None or pre_data != now_data or all_read_flag is True:
                                # 이전 값과 비교해 상이한 경우
                                self.pre_received_update_word_data[_device] = now_data
                                conversion_data = deviceDataConversion(now_data, device_type='short',
                                                                       conversion_type=read_word_device_types.get(_device, 'short'))

                                data_info = word_device_info.get(_device)
                                log_update_data = {}
                                if data_info is not None:
                                    if type(data_info) is dict:
                                        for _index, _data_info in data_info.items():
                                            pre_data_info_data = self.pre_received_update_data.get(_data_info)
                                            if pre_data_info_data != conversion_data[_index] or all_read_flag is True:
                                                read_data[_data_info] = conversion_data[_index]
                                                log_update_data[_data_info] = conversion_data[_index]
                                                self.pre_received_update_data[_data_info] = conversion_data[_index]
                                    else:
                                        pre_data_info_data = self.pre_received_update_data.get(data_info)
                                        if pre_data_info_data != conversion_data or all_read_flag is True:
                                            read_data[data_info] = conversion_data
                                            log_update_data[data_info] = conversion_data
                                            self.pre_received_update_data[data_info] = conversion_data
                                # if type(data_info) is dict:
                                #     for _index, _data_info in data_info.items():
                                #         read_data[_data_info] = conversion_data[_index]
                                # else:
                                #     read_data[data_info] = conversion_data

                                if pre_data != now_data:
                                    if pre_data is None:
                                        pre_data = ""
                                    self.logger.info(f"[recv] [{_device}] {pre_data} -> {now_data} ({log_update_data})")

                        ##########################
                        #      DWORD 파트
                        ##########################
                        for i in range(len(read_dword_devices)):
                            _device: str = read_dword_devices[i]
                            pre_data: int | str = self.pre_received_update_dword_data.get(_device)
                            now_data: int = read_dword_raw_datas[i]
                            if pre_data is None or pre_data != now_data or all_read_flag is True:
                                # 이전 값과 비교해 상이한 경우
                                self.pre_received_update_dword_data[_device] = now_data
                                conversion_data = deviceDataConversion(now_data, device_type='int',
                                                                       conversion_type=read_dword_device_types.get(_device, 'int'))

                                data_info = dword_device_info.get(_device)
                                log_update_data = {}
                                if data_info is not None:
                                    if type(data_info) is dict:
                                        for _index, _data_info in data_info.items():
                                            pre_data_info_data = self.pre_received_update_data.get(_data_info)
                                            if pre_data_info_data != conversion_data[_index] or all_read_flag is True:
                                                read_data[_data_info] = conversion_data[_index]
                                                log_update_data[_data_info] = conversion_data[_index]
                                                self.pre_received_update_data[_data_info] = conversion_data[_index]
                                    else:
                                        pre_data_info_data = self.pre_received_update_data.get(data_info)
                                        if pre_data_info_data != conversion_data or all_read_flag is True:
                                            read_data[data_info] = conversion_data
                                            log_update_data[data_info] = conversion_data
                                            self.pre_received_update_data[data_info] = conversion_data
                                # if type(data_info) is dict:
                                #     for _index, _data_info in data_info.items():
                                #         read_data[_data_info] = conversion_data[_index]
                                # else:
                                #     read_data[data_info] = conversion_data
                                if pre_data != now_data:
                                    if pre_data is None:
                                        pre_data = ""
                                    self.logger.info(f"[recv] [{_device}] {pre_data} -> {now_data} ({log_update_data})")
                    else:
                        # 개수가 맞지 않을 경우
                        print(f"[{self.socket_name}] 받은 데이터의 길이 맞지 않습니다. {read_word_devices} {read_word_raw_datas} {read_dword_devices} {read_dword_raw_datas}")
                        self.logger.warning(f"받은 데이터의 길이 맞지 않습니다. {read_word_devices} {read_word_raw_datas} {read_dword_devices} {read_dword_raw_datas}")

                    ##########################
                    #      BIT 파트
                    ##########################
                    if read_bit_datas is not None and len(read_bit_devices) == len(read_bit_datas):
                        for i in range(len(read_bit_devices)):
                            _device: str = read_bit_devices[i]
                            pre_data: int | str = self.pre_received_update_bit_data.get(_device)
                            now_data: int = read_bit_datas[i]

                            if pre_data is None or pre_data != now_data or all_read_flag is True:
                                # 이전 값과 비교해 상이한 경우
                                self.pre_received_update_bit_data[_device] = now_data
                                conversion_data = bool(now_data)

                                data_info = bit_device_info.get(_device)
                                log_update_data = {}
                                if data_info is not None:
                                    pre_data_info_data = self.pre_received_update_data.get(data_info)
                                    if pre_data_info_data != conversion_data or all_read_flag is True:
                                        read_data[data_info] = conversion_data
                                        log_update_data[data_info] = conversion_data
                                        self.pre_received_update_data[data_info] = conversion_data
                                if pre_data != now_data:
                                    if pre_data is None:
                                        pre_data = ""
                                    self.logger.info(f"[recv] [{_device}] {pre_data} -> {now_data} ({log_update_data})")
                    else:
                        # 개수가 맞지 않을 경우
                        print(f"[{self.socket_name}] 받은 데이터의 길이 맞지 않습니다. {read_bit_devices} {read_bit_datas}")
                        self.logger.warning(f"받은 데이터의 길이 맞지 않습니다. {read_bit_devices} {read_bit_datas}")

                    if len(read_data) != 0:
                        self.recv_queue.put({
                            "type": "receive",
                            "data": read_data
                        })
            except Exception as e:
                print(traceback.format_exc())
                self.logger.warning(e)
            await asyncio.sleep(0.01)

    # 업데이트할 데이터 처리
    def send_update_process(self, send_datas):
        for send_name, send_data in send_datas.items():
            pre_data: any = self.pre_send_update_data.get(send_name)
            if pre_data is None or pre_data != send_data:
                # 이전 값과 비교해 상이한 경우
                self.send_update_data[send_name] = send_data
                self.pre_send_update_data[send_name] = send_data

    # 연결 상태 보내기
    def send_connect_state(self):
        # 연결 상태 보내기
        now_connect_flag: bool = True if (self.socket_module.connect_flag is True and
                                          self.socket_module.received_connect is True) else False

        if self.socket_pre_connect_flag != self.socket_module.connect_flag:
            # 연결 값이 다르다면
            if self.socket_module.connect_flag is True:
                # 읽기 및 쓰기
                self.init_recv_flag = False
                self.all_write()
            self.socket_pre_connect_flag = self.socket_module.connect_flag

        if self.connect_flag != now_connect_flag:
            self.recv_queue.put({
                "type": "connect",
                "data": now_connect_flag
            })
            self.connect_flag = now_connect_flag


# def run_xgt_protocol(program_name, xgt_protocol_param, device_types, device_data_info, send_queue, recv_queue):
#     try:
#         XgtProtocol(program_name=program_name,
#                     xgt_protocol_param=xgt_protocol_param, device_types=device_types, device_data_info=device_data_info,
#                     send_queue=send_queue, recv_queue=recv_queue)
#     except Exception:
#         print(traceback.format_exc())


# if __name__ == "__main__":
#     mp.freeze_support()
#     send_queue = mp.Queue()
#     recv_queue = mp.Queue()
#     run_xgt_protocol("xgt_program", plc_address_param["agv_1_plc"], plc_device_types["agv_1_plc"], plc_device_data_info["agv_1_plc"], send_queue, recv_queue)
