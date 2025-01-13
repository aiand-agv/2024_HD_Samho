# -*- coding: utf-8 -*-
import datetime
import asyncio
import traceback
import pymcprotocol
import copy
import multiprocessing as mp

from collections import deque
from src.main_server.module.communication_module import deviceDataConversion

# MC프로토콜
class MCProtocol:
    # 생성자
    # host : 서버 주소
    # port : 서버 포트
    # socket_type : 소켓 타입 (예시: acs_client)
    # received_queue : 받은 데이터를 저장하는 큐
    # send_queue : 서버에 전송할 데이터 큐
    def __init__(self, host: str, port: int, socket_type: str, timeout: int = 5,
                 plc_type: str = "Q", comm_type: str = "binary", cycle_time: float = 0.3,
                 device_types: dict = {}, device_data_info: dict = {}, stop_event: mp.Event = mp.Event()):
        self.host = host  # 서버 주소
        self.port = port  # 포트 번호
        self.socket_type = socket_type  # 소켓 타입 (예시: acs_client)
        self.received_queue = deque()  # 수신 데이터 큐
        self.send_queue = deque()  # 송신 데이터 큐
        self.timeout = timeout
        self.connect_fail = False   #연결 실패 로그 1회

        self.stop_event = stop_event
        self.isDisable = False  # 비활성화 여부
        self.init_start_flag = False  # 초기화 시작 여부
        self.client_connect = False  # 소켓 클라이언트 연결 여부
        self.init_recv_flag = False  # 최초 강제 읽기 여부
        self.max_write_count = 160
        self.max_read_count = 192

        self.send_cycle: datetime.timedelta = datetime.timedelta(seconds=cycle_time)  # 보낼 사이클 시간 (단위: 초)
        self.send_time: datetime.datetime = datetime.datetime.now()  # 보낸 시간
        self.write_time: datetime.datetime = datetime.datetime.now()   # 쓴 시간

        self.device_types: dict = device_types
        read_device_types: dict = device_types.get('read', {})
        read_word_device_info: dict = read_device_types.get('word', {})
        read_dword_device_info: dict = read_device_types.get('dword', {})
        self.read_bit_device_info: dict = read_device_types.get('bit', {})

        self.send_update_data: dict = {}  # 보낼 데이터
        self.pre_send_update_data: dict = {}  # 이전 보낸 데이터

        self.pre_send_update_word_data: dict = {}  # 이전 보낸 Word 데이터
        self.pre_send_update_dword_data: dict = {}  # 이전 보낸 DWord 데이터
        self.pre_send_update_raw_word_data: dict = {}  # 이전 보낸 원본 Word 데이터
        self.pre_send_update_raw_dword_data: dict = {}  # 이전 보낸 원본 DWord 데이터

        self.received_update_data: deque = deque()  # 받은 데이터
        self.pre_received_update_word_data: dict = {}  # 이전 받은 Word 데이터
        self.pre_received_update_dword_data: dict = {}  # 이전 받은 DWord 데이터
        self.pre_received_update_bit_data: dict = {}  # 이전 받은 Bit 데이터
        self.pre_received_update_data: dict = {}  # 이전 받은 데이터

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
        self.read_devices: list = []
        device_count: int = 0
        devices_info: dict = {
            'word': [],
            'dword': [],
        }
        for _device in read_word_devices:
            if device_count >= self.max_read_count:
                self.read_devices.append(copy.deepcopy(devices_info))
                devices_info['word'] = []
                device_count = 1
            else:
                device_count += 1
            devices_info['word'].append(_device)
        for _device in read_dword_devices:
            if device_count >= self.max_read_count:
                self.read_devices.append(copy.deepcopy(devices_info))
                devices_info['word'] = []
                devices_info['dword'] = []
                device_count = 1
            else:
                device_count += 1
            devices_info['dword'].append(_device)
        if len(devices_info['word']) != 0 or len(devices_info['dword']) != 0:
            self.read_devices.append(copy.deepcopy(devices_info))
        del devices_info
        ##########################################################

        self.mp_protocol_client: pymcprotocol.Type3E = pymcprotocol.Type3E(plctype=plc_type)  # MC프로토콜 소켓
        self.mp_protocol_client.setaccessopt(commtype=comm_type, timer_sec=timeout)

    # 소멸자
    def __del__(self):
        # 소켓 열려있으면 닫기
        self.closeMCProtocol()

    # 프로세스 시작
    def runProcess(self):
        asyncio.run(self.socketProcess())

    # 소켓 프로세스
    async def socketProcess(self):
        init_mc_protocol_task = asyncio.create_task(self.initProcess())
        send_process_task = asyncio.create_task(self.sendProcess())
        comm_process_task = asyncio.create_task(self.commProcess())
        received_process_task = asyncio.create_task(self.recvProcess())

        # 동기 작업 시작
        await init_mc_protocol_task
        await send_process_task
        await comm_process_task
        await received_process_task

    # 서버 재시작
    def client_restart(self):
        self.send_state("재시작하기 위해 종료합니다.", state_type='info')
        self.closeMCProtocol()  # 클라이언트 닫기
        self.init_start_flag = False
        self.connect_fail = False

    # 초기화 프로세스
    async def initProcess(self):
        while not self.stop_event.is_set():
            if self.isDisable is False:
                if self.client_connect is False:
                    # 연결이 해제되었다면
                    if self.init_start_flag is False:
                        self.init_start_flag = True
                        self.initMCProtocol()
                    if self.socketConnect() is True:
                        # 접속 성공
                        self.client_connect = True
                        self.init_recv_flag = False
                        self.all_write()
                        self.write_time = datetime.datetime.now()
                        self.send_state(True, state_type='connect')  # 연결 여부 보내기
            await asyncio.sleep(1)

    # 보낼 데이터 프로세스
    async def sendProcess(self):
        while not self.stop_event.is_set():
            while len(self.send_queue) != 0:
                # 보낼 데이터가 들어있을 경우
                try:
                    send_data: any = self.send_queue.popleft()
                    if type(send_data) is bytes:
                        if send_data == bytes(0):
                            # 데이터가 0 바이트로 들어왔다면 재시작
                            self.send_state('재시작 명령이 들어와 재시작 합니다.', state_type='info')
                            self.client_restart()
                            continue
                        elif send_data == bytes(1):
                            # 데이터가 1 바이트로 들어왔다면 종료
                            self.closeMCProtocol()
                            return
                        elif send_data == bytes(2):
                            # 데이터가 2 바이트 들어오면 비활성화
                            self.isDisable = True
                            self.send_state('비활성화 명령이 들어왔습니다', state_type='info')
                            self.closeMCProtocol()
                            continue
                        elif send_data == bytes(3):
                            # 데이터가 3 바이트 들어오면 비활성화 해제
                            self.send_state('비활성화 해제 명령이 들어왔습니다', state_type='info')
                            self.isDisable = False
                            continue
                        else:
                            raise Exception('알 수 없는 데이터')
                    elif type(send_data) is dict:
                        # 튜플 형태로 왔다면 송신 데이터 갱신
                        self.sendUpdateProcess(send_data)
                    else:
                        # 알 수 없는 타입이라면 에러 발생
                        raise Exception('알 수 없는 데이터')
                except Exception as e:
                    self.send_state('예외가 발생했습니다. 예외 메시지: ' + str(e), state_type='error')

            now_time = datetime.datetime.now()
            time_diff = now_time - self.write_time
            if time_diff >= datetime.timedelta(seconds=5):
                self.all_write()
                self.write_time = now_time

            await asyncio.sleep(0.01)

    # 통신 프로세스
    async def commProcess(self):
        write_device_types: dict = self.device_types.get('write', {})
        write_word_device_types: dict = write_device_types.get('word', {})
        write_dword_device_types: dict = write_device_types.get('dword', {})

        while not self.stop_event.is_set():
            if self.isDisable is False:
                if self.client_connect is True and (datetime.datetime.now() - self.send_time) >= self.send_cycle:
                    try:
                        ##########################
                        #       송신 파트
                        ##########################
                        if len(self.send_update_data) != 0:
                            # 보낼 데이터가 존재한다면
                            send_update_word_data: dict = {}  # 보낼 Word 데이터
                            send_update_dword_data: dict = {}  # 보낼 DWord 데이터
                            log_send_update_word_data: dict = {}  # 보낼 Word 로그 데이터
                            log_send_update_dword_data: dict = {}  # 보낼 DWord 로그 데이터

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
                                        if send_count >= self.max_write_count:
                                            break
                                        else:
                                            send_count += 1
                                        _value: any = send_update_word_data.pop(_device)
                                        conversion_data = deviceDataConversion(_value,
                                                                               device_type=write_word_device_types.get(_device, 'short'),
                                                                               conversion_type='short')
                                        send_word_devices.append(_device)
                                        send_word_raw_datas.append(conversion_data)

                                        pre_data = self.pre_send_update_raw_word_data.get(_device, "")
                                        if pre_data != conversion_data:
                                            self.send_state(
                                                f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_word_data.get(_device, '')})",
                                                state_type='info')
                                            self.pre_send_update_raw_word_data[_device] = conversion_data
                                            self.pre_send_update_word_data[_device] = _value

                                    send_dword_devices: list = []
                                    send_dword_raw_datas: list = []
                                    for _device in list(send_update_dword_data.keys()):
                                        if send_count >= self.max_write_count:
                                            break
                                        else:
                                            send_count += 1
                                        _value: any = send_update_dword_data.pop(_device)
                                        conversion_data = deviceDataConversion(_value,
                                                                               device_type=write_dword_device_types.get(_device, 'short'),
                                                                               conversion_type='short')
                                        send_dword_devices.append(_device)
                                        send_dword_raw_datas.append(conversion_data)

                                        pre_data = self.pre_send_update_raw_dword_data.get(_device, "")
                                        if pre_data != conversion_data:
                                            self.send_state(
                                                f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_dword_data.get(_device, '')})",
                                                state_type='info')
                                            self.pre_send_update_raw_dword_data[_device] = conversion_data
                                            self.pre_send_update_dword_data[_device] = _value
                                    self.mp_protocol_client.randomwrite(send_word_devices, send_word_raw_datas,
                                                                        send_dword_devices, send_dword_raw_datas)
                                except Exception as e:
                                    print(traceback.format_exc())
                                    raise Exception('송신 도중 예외가 발생하여 재시작합니다. 예외 메시지: ' + str(e))

                        ##########################
                        #       수신 파트
                        ##########################
                        try:
                            for read_device in self.read_devices:
                                read_word_devices: list = read_device.get('word', [])
                                read_dword_devices: list = read_device.get('dword', [])

                                read_word_raw_datas, read_dword_raw_datas = self.mp_protocol_client.randomread(
                                    read_word_devices, read_dword_devices)
                                self.received_update_data.append({
                                    "type": "randomread",
                                    "data": (read_word_devices, read_word_raw_datas, read_dword_devices, read_dword_raw_datas)
                                })

                            for start_device, device_count in self.read_bit_device_info.items():
                                read_bit_raw_datas = self.mp_protocol_client.batchread_bitunits(start_device, device_count)
                                self.received_update_data.append({
                                    "type": "bit",
                                    "data": (start_device, read_bit_raw_datas)
                                })
                        except Exception as e:
                            raise Exception('수신 도중 예외가 발생하여 재시작합니다. 예외 메시지: ' + str(e))
                    except Exception as e:
                        print(traceback.format_exc())
                        self.send_state(str(e), state_type='error')
                        self.client_restart()
                        continue
                    finally:
                        self.send_time = datetime.datetime.now()
            await asyncio.sleep(0.1)

    # 받은 데이터 프로세스
    async def recvProcess(self):
        read_device_types: dict = self.device_types.get('read', {})
        read_word_device_types: dict = read_device_types.get('word', {})
        read_dword_device_types: dict = read_device_types.get('dword', {})

        all_read_time: datetime.datetime = datetime.datetime.now()  # 전체 읽은 시간

        while not self.stop_event.is_set():
            while len(self.received_update_data) != 0:
                try:
                    # =======================================
                    # 5초마다 강제 읽기
                    now_time = datetime.datetime.now()
                    all_read_flag = False
                    if now_time - all_read_time >= datetime.timedelta(seconds=5):
                        all_read_time = now_time
                        all_read_flag = True

                    if self.init_recv_flag is False:
                        # 최초 연결 시 강제 읽기
                        all_read_flag = True
                        self.init_recv_flag = True
                    # =======================================

                    read_data: dict = {}

                    recv_data_dict = self.received_update_data.popleft()
                    recv_type = recv_data_dict.get("type")
                    recv_data = recv_data_dict.get("data")

                    if recv_type == "randomread":
                        word_device_info: dict = self.read_device_info.get('word', {})
                        dword_device_info: dict = self.read_device_info.get('dword', {})

                        read_word_devices, read_word_raw_datas, read_dword_devices, read_dword_raw_datas = recv_data
                        ##########################
                        #       WORD 파트
                        ##########################
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
                                    self.send_state(f"[recv] [{_device}] {pre_data} -> {now_data} ({log_update_data})", state_type='info')

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
                                        # for _index, _data_info in data_info.items():
                                        #     read_data[_data_info] = conversion_data[_index]
                                    else:
                                        pre_data_info_data = self.pre_received_update_data.get(data_info)
                                        if pre_data_info_data != conversion_data or all_read_flag is True:
                                            read_data[data_info] = conversion_data
                                            log_update_data[data_info] = conversion_data
                                            self.pre_received_update_data[data_info] = conversion_data
                                        # read_data[data_info] = conversion_data

                                if pre_data != now_data:
                                    if pre_data is None:
                                        pre_data = ""
                                    self.send_state(f"[recv] [{_device}] {pre_data} -> {now_data} ({log_update_data})", state_type='info')

                    elif recv_type == "bit":
                        bit_device_info: dict = self.read_device_info.get('bit', {})
                        start_device, now_data = recv_data
                        bit_pre_data: list | str = self.pre_received_update_bit_data.get(start_device)
                        if bit_pre_data is None or bit_pre_data != now_data or all_read_flag is True:
                            # 이전 값과 비교해 상이한 경우
                            self.pre_received_update_bit_data[start_device] = now_data
                            conversion_data = list(map(bool, now_data))
                            data_info = bit_device_info.get(start_device)
                            log_update_data = {}
                            if data_info is not None:
                                for _index, _data_info in data_info.items():
                                    pre_data_info_data = self.pre_received_update_data.get(_data_info)
                                    if pre_data_info_data != conversion_data[_index] or all_read_flag is True:
                                        read_data[_data_info] = conversion_data[_index]
                                        log_update_data[_data_info] = conversion_data[_index]
                                        self.pre_received_update_data[_data_info] = conversion_data[_index]

                            if bit_pre_data != now_data:
                                if bit_pre_data is None:
                                    bit_pre_data = ""
                                self.send_state(f"[recv] [{start_device}] {bit_pre_data} -> {now_data} ({log_update_data})", state_type='info')

                    if len(read_data) != 0:
                        self.send_state(read_data, state_type='receive')
                except Exception:
                    print(traceback.format_exc())
            await asyncio.sleep(0.01)

    # 전체 쓰기
    def all_write(self):
        self.send_update_data.update(self.pre_send_update_data)

    # 업데이트할 데이터 처리
    def sendUpdateProcess(self, send_datas):
        for send_name, send_data in send_datas.items():
            pre_data: any = self.pre_send_update_data.get(send_name)
            if pre_data is None or pre_data != send_data:
                # 이전 값과 비교해 상이한 경우
                self.send_update_data[send_name] = send_data
                self.pre_send_update_data[send_name] = send_data

        # send_update_word_data: dict = {}
        # send_update_dword_data: dict = {}
        # write_device_types: dict = self.device_types.get('write', {})
        # word_device_types: dict = write_device_types.get('word', {})
        # dword_device_types: dict = write_device_types.get('dword', {})
        #
        # # WORD 파트
        # for _device, now_data in send_data.get('word', {}).items():
        #     pre_data: any = self.pre_send_update_word_data.get(_device)
        #     if pre_data is None or pre_data != now_data:
        #         # 이전 값과 비교해 상이한 경우 (5초마다 갱신)
        #         self.pre_send_update_word_data[_device] = now_data
        #         conversion_data = deviceDataConversion(now_data, device_type=word_device_types.get(_device, 'short'),
        #                                                conversion_type='short')
        #         send_update_word_data[_device] = conversion_data
        #
        #         if pre_data is None:
        #             pre_data = 0
        #         self.send_state(f"[send] [{_device}] {pre_data} -> {now_data} ({conversion_data})", state_type='info')
        #
        # # DWORD 파트
        # for _device, now_data in send_data.get('dword', {}).items():
        #     pre_data: any = self.pre_send_update_dword_data.get(_device)
        #     if pre_data is None or pre_data != now_data:
        #         # 이전 값과 비교해 상이한 경우
        #         self.pre_send_update_dword_data[_device] = now_data
        #         conversion_data = deviceDataConversion(now_data, device_type=dword_device_types.get(_device, 'int'),
        #                                                conversion_type='int')
        #         send_update_dword_data[_device] = conversion_data
        #
        #         if pre_data is None:
        #             pre_data = 0
        #         self.send_state(f"[send] [{_device}] {pre_data} -> {now_data} ({conversion_data})", state_type='info')
        #
        # # 보낼 데이터 갱신
        # self.send_update_word_data.update(send_update_word_data)
        # self.send_update_dword_data.update(send_update_dword_data)

    # 상태 데이터 보내기
    # type => 데이터 타입
    #     info => 소켓 메시지
    #     connect => 연결 여부
    #     error => 소켓 에러
    #     receive => 수신 데이터
    # time => 시간
    # socket_type => 소켓 타입 (예시: acs_client)
    # data => 데이터
    def send_state(self, data: any, state_type: str):
        state_data = {
            'type': state_type,
            'time': datetime.datetime.now(),
            'socket_type': self.socket_type,
            'data': data
        }
        self.received_queue.append(state_data)

    # 클라이언트 초기화
    def initMCProtocol(self):
        self.send_state("클라이언트를 시작합니다.", state_type='info')

    # 소켓 연결
    def socketConnect(self):
        try:
            if self.connect_fail is False:
                self.send_state(f"서버에 연결을 시도합니다... [{self.host}:{self.port}]", state_type='info')
            self.mp_protocol_client.connect(self.host, self.port)
            self.send_state("서버에 연결되었습니다.", state_type='info')
            return True
        except Exception as e:
            # 접속 실패 시 2초 후 다시 접속
            if self.connect_fail is False:
                self.send_state('서버에 연결 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e), state_type='error')
                self.connect_fail = True
        return False

    # 클라이언트 닫기
    def closeMCProtocol(self):
        try:
            if self.mp_protocol_client is not None:
                self.mp_protocol_client.close()
        except Exception:
            pass
        self.client_connect = False
        self.init_start_flag = False
        self.send_state(False, state_type='connect')  # 연결 여부 보내기
        self.send_state(f"통신 프로그램 종료", state_type='info')