# -*- coding: utf-8 -*-
import asyncio
import datetime
import logging
import traceback
import multiprocessing as mp

from src.main_server.module.logger import get_logger, LoggerPrint
from src.main_server.module.mc_protocol.mc_protocol import MCProtocol


class MCProtocolProgram:
    # 생성자
    def __init__(self, program_name: str = 'mc_protocol',
                 mc_protocol_param: dict = {}, device_types: dict = {}, device_data_info: dict = {},
                 send_queue: mp.Queue = mp.Queue(), recv_queue: mp.Queue = mp.Queue(),
                 logger: logging.Logger = None, stop_event = mp.Event()):
        # Set Variable
        self.module_name: str = program_name
        self.stop_event: mp.Event = stop_event
        self.send_queue: mp.Queue = send_queue
        self.recv_queue: mp.Queue = recv_queue
        self.module_name: str = program_name   # 모듈 이름(프로그램 이름)
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger
        self.__init_variable(mc_protocol_param, device_types, device_data_info)

    # 소멸자
    def __del__(self):
        self.finallyCloseTCP()

    def __init_variable(self, mc_protocol_param, device_types, device_data_info):
        self.connect_flag: bool = None   # 연결 정보

        # TCP 소켓 통신 관련 변수
        self.ip_address: str = mc_protocol_param.get('ip_address', "localhost")   # IP 주소
        self.port: int = mc_protocol_param.get('port', 4000)   # 포트 번호
        self.socket_timeout: int = mc_protocol_param.get('socket_timeout', 5)  # -1 = None = blocking mode | 0 이상 = non-blocking mode
        self.receive_timeout: int = mc_protocol_param.get('receive_timeout', 0)
        self.plc_type: str = mc_protocol_param.get('plc_type', 'Q')  # PLC 타입
        self.comm_type: str = mc_protocol_param.get('comm_type', 'binary')  # 통신 타입
        self.cycle_time: float = mc_protocol_param.get('cycle_time', 0.1)  # 통신 주기

        # 상태 관련 변수
        self.received_time: datetime.datetime = datetime.datetime.now()  # 데이터 수신 시간
        self.received_connect: bool = False  # 데이터 수신 여부
        self.pre_second: int = 0  # 이전 초

        if self.socket_timeout == -1:
            self.socket_timeout = None

        # MC 프로토콜 설정
        self.mc_protocol = MCProtocol(host=self.ip_address, port=self.port, socket_type=self.module_name,
                                      timeout=self.socket_timeout,
                                      plc_type=self.plc_type, comm_type=self.comm_type, cycle_time=self.cycle_time,
                                      device_types=device_types,
                                      device_data_info=device_data_info,
                                      stop_event=self.stop_event)

    ########################################
    #       기본 설정 관련 함수 선언
    ########################################
    async def run_process(self):
        recv_process_task = asyncio.create_task(self.recv_process())
        send_process_task = asyncio.create_task(self.send_process())

        # 동기 작업 시작
        await self.mc_protocol.socketProcess()
        await recv_process_task
        await send_process_task

    async def send_process(self):
        while not self.stop_event.is_set():
            while self.send_queue.qsize() != 0:
                # 보낼 데이터가 들어있을 경우
                try:
                    send_dict: dict = self.send_queue.get()
                    data_type: str = send_dict.get("type")
                    if data_type == "send":
                        data_dict: dict = send_dict.get("data")
                        self.mc_protocol.send_queue.append(data_dict)
                    elif data_type == "disable":
                        if send_dict.get("data") is True:
                            self.mc_protocol.send_queue.append(bytes(2))
                        else:
                            self.mc_protocol.send_queue.append(bytes(3))
                    elif data_type == "reconnect":
                        self.mc_protocol.send_queue.append(bytes(0))
                    elif data_type == "exit":
                        self.finallyCloseTCP()
                        break
                except Exception as e:
                    self.logger.warning(f'[{self.module_name}] Exception: {e}\n{traceback.format_exc()}')

            try:
                if self.mc_protocol.client_connect is True:
                    # 연결 되어있을 경우
                    if self.receive_timeout != 0:
                        # 수신 타임아웃이 0이 아니라면
                        time_diff = datetime.datetime.now() - self.received_time
                        if time_diff >= datetime.timedelta(seconds=self.receive_timeout):
                            # 수신이 설정한 시간보다 안된 경우 강제 재접속
                            self.logger.warning(f"[{self.module_name}] failed to receive data")
                            self.closeTCP()
                self.send_connect_state()  # 상태 보내기
            except Exception as e:
                self.logger.warning(f'[{self.module_name}] Exception: {e}\n{traceback.format_exc()}')
            await asyncio.sleep(0.01)

    ########################################
    #       통신 설정 관련 함수 선언
    ########################################
    # 소켓 데이터 처리 함수
    # type => 데이터 타입
    #     info => 소켓 메시지
    #     connect => 연결 여부
    #     error => 소켓 에러
    #     receive => 수신 데이터
    # time => 시간
    # socket_type => 소켓 타입 (예시: acs_client)
    # data => 데이터
    async def recv_process(self):
        while not self.stop_event.is_set():
            while len(self.mc_protocol.received_queue) != 0:
                # 수신 데이터가 있을 경우
                received_data: dict = self.mc_protocol.received_queue.popleft()
                socket_data: any = received_data['data']
                data_type: str = received_data['type']
                socket_type: str = received_data['socket_type']

                try:
                    if data_type == 'error':
                        # 타입이 에러 타입이라면
                        raise Exception(socket_data)
                    elif data_type == 'receive':
                        # 타입이 수신 데이터라면
                        self.recv_queue.put({
                            "type": "receive",
                            "data": socket_data
                        })
                        self.received_connect = True
                        self.received_time = datetime.datetime.now()
                    elif data_type == 'info':
                        # 타입이 정보 알림일 경우
                        self.logger.info(f'[{self.module_name}] {socket_data}')
                    elif data_type == 'connect':
                        # 타입이 연결 정보일 경우
                        if socket_data is True:
                            self.received_time = datetime.datetime.now()
                            self.received_connect = False
                    else:
                        raise Exception("소켓 데이터의 타입을 알 수 없습니다.")
                except Exception as e:
                    # 예외 발생 시
                    self.logger.warning(f"[{self.module_name}] Socket Data Error: {e}")
            await asyncio.sleep(0.01)

    # TCP 소켓 닫기
    def closeTCP(self):
        self.mc_protocol.send_queue.append(bytes(0))

    # 최종 TCP 소켓 닫기
    def finallyCloseTCP(self):
        self.logger.info(f'[{self.module_name}] 프로그램 종료 요청')
        self.mc_protocol.send_queue.append(bytes(1))
        self.logger.info(f'[{self.module_name}] 프로그램 종료')

    # 상태 보내기
    def send_connect_state(self):
        # 연결 상태 보내기
        now_connect_flag: bool = True if self.mc_protocol.client_connect is True and self.received_connect is True else False
        if self.connect_flag != now_connect_flag:
            self.recv_queue.put({
                "type": "connect",
                "data": now_connect_flag
            })
            self.connect_flag = now_connect_flag
