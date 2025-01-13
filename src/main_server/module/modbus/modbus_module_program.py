# -*- coding: utf-8 -*-
import asyncio
import datetime
import logging
import traceback
import multiprocessing as mp

from pymodbus import ModbusException
from src.main_server.module.communication_module import deviceDataConversion
from src.main_server.module.logger import get_logger, LoggerPrint
from src.main_server.module.modbus.modbus_module import ModbusModule


class ModbusModulePython:
    # 생성자
    def __init__(self, program_name: str = 'modbus',
                 modbus_param: dict = {}, data_types: dict = {}, data_info: dict = {},
                 send_queue: mp.Queue = mp.Queue(), recv_queue: mp.Queue = mp.Queue(),
                 logger: logging.Logger = None, stop_event = mp.Event()):
        # Set Variable
        self.module_name: str = program_name   # 모듈 이름(프로그램 이름)
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger
        self.stop_event: mp.Event = stop_event
        self.send_queue: mp.Queue = send_queue
        self.recv_queue: mp.Queue = recv_queue
        self.logger = get_logger(program_name)
        self._init_variable(modbus_param)
        self._init_input_output(data_types, data_info)

    # 소멸자
    def __del__(self):
        self.finallyCloseModbus()

    def _init_variable(self, modbus_param):
        # Serial 관련 변수
        self.ip_address: str = modbus_param.get('ip_address', "192.168.127.254")  # IP 주소
        self.port: int = modbus_param.get('port', 502)   # 포트 번호
        self.timeout: float = modbus_param.get('timeout', 1.0)   # 타임 아웃
        self.modbus_module: ModbusModule = ModbusModule(self.ip_address, self.port, self.timeout)  # 모드버스 클라이언트

        # 상태 관련 변수
        self.close_count: int = 0  # 재 연결 카운트
        self.connect_flag = None
        self.isDisable = False  # 비활성화 여부
        self.init_log_flag = False   # 1회 로그 여부

    #####################################
    #      모드버스 데이터 가져오기
    #####################################
    def _init_input_output(self, data_types, data_info):
        ##########################################################
        # 쓰기 디바이스 타입 정의
        ##########################################################
        self.write_device_types: dict = data_types.get('write', {})
        self.send_update_data: dict = {}  # 보낼 데이터
        self.pre_send_update_data: dict = {}  # 이전 보낸 데이터

        self.pre_send_update_device_data: dict = {}  # 이전 보낸 데이터
        self.pre_send_update_device_raw_data: dict = {}  # 이전 보낸 원본 데이터

        self.write_device_name: dict = {}
        for device, device_info in data_info.get('write', {}).items():
            self.write_device_name[device_info] = device
        self.all_write_time: datetime.datetime = datetime.datetime.now()   # 전체 쓴 시간

        ##########################################################
        # 읽기 디바이스 타입 정의
        ##########################################################
        self.read_device_types: dict = data_types.get('read', {})
        self.pre_received_update_data: dict = {}   # 이전 받은 데이터

        self.read_devices: dict = {"coils": [], "registers": []}
        read_device_list: dict = {"coils": [], "registers": []}

        for device, device_type in self.read_device_types.items():
            addr_type = "coils" if device_type == "bool" else "registers"
            if len(read_device_list[addr_type]) == 0 or read_device_list[addr_type][-1] + 1 == device:
                # 리스트에 주소들이 없거나 이전 주소 +1이 현재 주소랑 동일 한 경우 리스트 추가
                pass
            else:
                # 현재 주소랑 다르다면 리스트 삽입 및 리스트 초기화
                self.read_devices[addr_type].append(read_device_list[addr_type])
                read_device_list[addr_type].clear()
            read_device_list[addr_type].append(device)

        for addr_type, device_list in read_device_list.items():
            if len(device_list) != 0:
                # 넣을 주소가 남아있다면 삽입
                self.read_devices[addr_type].append(device_list)

        self.read_device_name: dict = {}
        for device, device_info in data_info.get('read', {}).items():
            self.read_device_name[device] = device_info

        self.all_read_time: datetime.datetime = datetime.datetime.now()  # 전체 읽은 시간

    ########################################
    #       통신 설정 관련 함수 선언
    ########################################
    # Modbus 통신 설정
    async def setup_modbus(self):
        try:
            if self.init_log_flag is False:  # 로그 1회
                self.logger.info(f'[{self.module_name}] Modbus Openning...')
            self.modbus_module.setupModbus()
        except Exception as e:
            if self.init_log_flag is False:  # 로그 1회
                self.logger.warning(f'[{self.module_name}] Modbus connection failure:{e}')
                self.init_log_flag = True
            await asyncio.sleep(1)
        else:
            self.init_log_flag = False
            self.logger.info(f'[{self.module_name}] Successfully opened modbus')
            self.set_success_modbus()

    # Modbus 닫기
    def closeModbus(self):
        try:
            self.logger.warning(f'[{self.module_name}] Close Modbus')
            self.modbus_module.closeModbus()
        except Exception:
            pass

    # 전체 초기화
    def all_clear(self):
        if self.modbus_module.modbus_connect is True:
            # 연결 되어있을 경우 전체 초기화
            for send_name, send_data in self.pre_send_update_data.items():
                self.send_update_data[send_name] = False if type(send_data) == bool else 0
            self.input_output_process()

    # 최종 모드 버스 닫기
    def finallyCloseModbus(self):
        self.all_clear()
        self.modbus_module.closeModbus()
        self.logger.info(f'[{self.module_name}] 프로그램 종료합니다.')

    ########################################
    #           함수 선언
    ########################################
    # 프로세스 실행
    async def run_process(self):
        modbus_process_task = asyncio.create_task(self.modbus_process())
        send_process_task = asyncio.create_task(self.send_process())

        # 동기 작업 시작
        await modbus_process_task
        await send_process_task

    # 모드버스 프로세스
    async def modbus_process(self):
        while not self.stop_event.is_set():
            if self.isDisable is False:
                try:
                    if self.modbus_module.modbus_connect is True:
                        # 연결 되어있을 경우
                        self.input_output_process()
                    else:
                        # 연결이 되어있지 않은 경우 Modbus 연결
                        await self.setup_modbus()
                except ModbusException as e:
                    self.logger.warning(f'[{self.module_name}] modbus::ModbusException:{e}')
                    self.closeModbus()
                except Exception as e:
                    self.logger.warning(f'[{self.module_name}] Exception: {e}\n{traceback.format_exc()}')
            self.sendState()
            await asyncio.sleep(0.1)

    async def send_process(self):
        while not self.stop_event.is_set():
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
                            self.isDisable = True
                            self.logger.info(f'[{self.module_name}] 비활성화 설정 명령이 들어왔습니다')
                            self.modbus_module.closeModbus()
                        else:
                            self.isDisable = False
                            self.logger.info(f'[{self.module_name}] 비활성화 해제 명령이 들어왔습니다')
                    elif data_type == "reconnect":
                        self.logger.info(f'[{self.module_name}] 재연결 명령이 들어왔습니다')
                        self.modbus_module.closeModbus()
                    elif data_type == "exit":
                        self.finallyCloseModbus()
                except Exception as e:
                    self.logger.warning(f'[{self.module_name}] Exception: {e}\n{traceback.format_exc()}')
            await asyncio.sleep(0.1)

    # 보낼 데이터 프로세스
    def send_update_process(self, send_datas):
        for send_name, send_data in send_datas.items():
            pre_data: any = self.pre_send_update_data.get(send_name)
            if pre_data is None or pre_data != send_data:
                # 이전 값과 비교해 상이한 경우
                self.send_update_data[send_name] = send_data
                self.pre_send_update_data[send_name] = send_data

    # Modbus 연결 성공 시 설정
    def set_success_modbus(self):
        # 최초 갱신
        self.all_write_time = datetime.datetime.now() - datetime.timedelta(seconds=5)

    # Input Output 프로세스
    def input_output_process(self):
        try:
            ##########################
            #       송신 파트
            ##########################
            # =======================================
            # 5초마다 강제 쓰기
            now_time = datetime.datetime.now()
            if now_time - self.all_write_time >= datetime.timedelta(seconds=5):
                self.all_write_time = now_time
                self.send_update_data.update(self.pre_send_update_data)
            # =======================================

            if len(self.send_update_data) != 0:
                # 보낼 데이터가 존재한다면
                send_update_data: dict = {}  # 보낼 데이터
                log_send_update_data: dict = {}  # 보낼 로그 데이터

                for data_name in list(self.send_update_data.keys()):
                    data_value = self.send_update_data.pop(data_name)
                    write_data_name = self.write_device_name.get(data_name)
                    if write_data_name is not None:
                        send_update_data[write_data_name] = data_value

                        # 로그 기록
                        if log_send_update_data.get(write_data_name) is None:
                            log_send_update_data[write_data_name] = {}
                        log_send_update_data[write_data_name][data_name] = data_value

                while len(send_update_data) != 0:
                    try:
                        # 보낼 데이터가 있을 경우
                        coils_devices: list = []
                        coils_raw_datas: list = []

                        register_devices: list = []
                        register_raw_datas: list = []

                        for _device in list(send_update_data.keys()):
                            _value: any = send_update_data.pop(_device)
                            _device_type: str = self.write_device_types.get(_device, 'short')
                            if _device_type == "bool":
                                conversion_data = _value
                            else:
                                conversion_data = deviceDataConversion(_value,
                                                                       device_type=self.write_device_types.get(_device, 'short'),
                                                                       conversion_type='short')

                            pre_data = self.pre_send_update_device_raw_data.get(_device, "")
                            if pre_data != conversion_data:
                                self.logger.info(
                                    f"[send] [{_device}] {pre_data} -> {conversion_data} ({log_send_update_data.get(_device, '')})")
                                self.pre_send_update_device_raw_data[_device] = conversion_data
                                self.pre_send_update_device_data[_device] = _value

                            if _device_type == "bool":
                                # Boolean 형태라면 Coils 쓰기
                                if len(coils_devices) == 0 or coils_devices[-1] + 1 == _device:
                                    # 리스트에 주소들이 없거나 이전 주소 +1이 현재 주소랑 동일 한 경우 리스트 추가
                                    pass
                                else:
                                    # 현재 주소랑 다르다면 데이터 전송 및 리스트 초기화
                                    self.modbus_module.writeCoils(coils_devices[0], coils_raw_datas)
                                    coils_devices.clear()
                                    coils_raw_datas.clear()
                                coils_devices.append(_device)
                                coils_raw_datas.append(conversion_data)
                            else:
                                # 나머지 Registers 쓰기
                                if len(register_devices) == 0 or register_devices[-1] + 1 == _device:
                                    # 리스트에 주소들이 없거나 이전 주소 +1이 현재 주소랑 동일 한 경우 리스트 추가
                                    pass
                                else:
                                    # 현재 주소랑 다르다면 데이터 전송 및 리스트 초기화
                                    self.modbus_module.writeRegisters(register_devices[0], register_raw_datas)
                                    register_devices.clear()
                                    register_raw_datas.clear()
                                register_devices.append(_device)
                                register_raw_datas.append(conversion_data)

                        if len(coils_devices) != 0:
                            # 보낼 데이터가 남아있다면 전송
                            self.modbus_module.writeCoils(coils_devices[0], coils_raw_datas)
                        if len(register_devices) != 0:
                            # 보낼 데이터가 남아있다면 전송
                            self.modbus_module.writeRegisters(register_devices[0], register_raw_datas)

                    except Exception as e:
                        raise Exception('송신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e))

            ##########################
            #       수신 파트
            ##########################
            try:
                # =======================================
                # 5초마다 강제 읽기
                now_time = datetime.datetime.now()
                all_read_flag = False
                if now_time - self.all_read_time >= datetime.timedelta(seconds=5):
                    self.all_read_time = now_time
                    all_read_flag = True
                # =======================================

                read_data: dict = {}
                for addr_type, read_device_list in self.read_devices.items():
                    for read_devices in read_device_list:
                        if addr_type == "coils":
                            read_raw_data: list = self.modbus_module.readDiscreteInputs(read_devices[0], len(read_devices))
                        else:
                            read_raw_data: list = self.modbus_module.readHoldingRegisters(read_devices[0], len(read_devices))

                        for i in range(len(read_devices)):
                            _device: str = read_devices[i]
                            pre_data: int = self.pre_received_update_data.get(_device)
                            now_data: int = read_raw_data[i]

                            if pre_data is None or pre_data != now_data or all_read_flag is True:
                                # 이전 값과 비교해 상이한 경우
                                self.pre_received_update_data[_device] = now_data
                                if addr_type == "coils":
                                    conversion_data = now_data
                                else:
                                    conversion_data = deviceDataConversion(now_data, device_type='short',
                                                                           conversion_type=self.read_device_types.get(_device,
                                                                                                                      'short'))

                                read_data_name = self.read_device_name.get(_device)
                                log_update_data = {}
                                if read_data_name is not None:
                                    pre_read_data_name_data = self.pre_received_update_data.get(read_data_name)
                                    if pre_read_data_name_data != conversion_data or all_read_flag is True:
                                        read_data[read_data_name] = conversion_data
                                        log_update_data[read_data_name] = conversion_data
                                        self.pre_received_update_data[read_data_name] = conversion_data

                                if pre_data != now_data:
                                    if pre_data is None:
                                        pre_data = ""
                                    self.logger.info(f"[recv] [{_device}] {pre_data} -> {now_data} ({log_update_data})")

                if len(read_data) != 0:
                    # 데이터가 있을 경우 데이터 전송
                    self.recv_queue.put({
                        "type": "receive",
                        "data": read_data
                    })
            except Exception as e:
                raise Exception('수신 도중 예외가 발생하였습니다. 예외 메시지: ' + str(traceback.format_exc()))
            self.send_time = datetime.datetime.now()
        except Exception as e:
            self.logger.warning(f"Input Output 프로세스 에러: {traceback.format_exc()}")
            self.closeModbus()

    def sendState(self):
        # 연결 상태 보내기
        now_connect_flag = self.modbus_module.modbus_connect
        if self.connect_flag != now_connect_flag:
            self.recv_queue.put({
                "type": "connect",
                "data": now_connect_flag
            })
            self.connect_flag = now_connect_flag
