# -*- coding: utf-8 -*-
import logging
import traceback
import multiprocessing as mp
import datetime
import asyncio
import time

from abc import *  # 추상 클래스 사용
from collections import deque
from logging import Logger
from src.main_server.module.logger import LoggerPrint
from src.main_server.module.tcp_socket.tcp_socket import socket_server_start, socket_client_start
from src.main_server.module.thread_with_exception import ThreadWithException


class TcpSocketModule:
    # 생성자
    def __init__(self, socket_name: str, ip_address: str, port: int, socket_timeout: int = None,
                 receive_timeout: int = 0, server_flag: bool = False, buffer_bytes_flag: bool = False,
                 bind_ip: str = None, logger: Logger = None):
        # Set Variable
        if logger is None:
            self.logger = LoggerPrint(socket_name)
        else:
            self.logger = logger

        # TCP 소켓 통신 관련 변수
        self.socket_name = socket_name
        self.socket_timeout = socket_timeout
        self.receive_timeout = receive_timeout
        self.ip_address = ip_address
        self.port = port
        self.server_flag = server_flag
        self.socket_send_queue = mp.Queue()
        self.socket_received_queue = mp.Queue()
        self.bind_ip = bind_ip
        self.tcp_socket_processing: mp.Process

        # 상태 관련 변수
        self.buffer_bytes_flag = buffer_bytes_flag
        self.data_buffer = bytes() if buffer_bytes_flag is True else deque()  # 수신 데이터 버퍼
        self.received_time = datetime.datetime.now()  # 데이터 수신 시간
        self.received_connect = False  # 데이터 수신 여부
        self.connect_flag = False  # 연결 정보
        self.pre_second = 0  # 이전 초

        # 소켓 시작
        self.startSocket()

    # 소멸자
    def __del__(self):
        self.finallyCloseTCP()

    # 소켓 시작
    def startSocket(self):
        socket_start = socket_server_start if self.server_flag is True else socket_client_start
        self.tcp_socket_processing = mp.Process(target=socket_start, name=self.socket_name, args=(
            self.ip_address, self.port, self.socket_name, self.socket_received_queue, self.socket_send_queue,
            self.socket_timeout, self.bind_ip))
        self.tcp_socket_processing.start()

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
    def socketDataProcess(self):
        while self.socket_received_queue.qsize() > 0:
            # 수신 데이터가 있을 경우
            received_data: dict = self.socket_received_queue.get()
            socket_data: any = received_data['data']
            data_type: str = received_data['type']
            socket_type: str = received_data['socket_type']
            try:
                if data_type == 'error':
                    # 타입이 에러 타입이라면
                    raise Exception(socket_data)
                elif data_type == 'receive':
                    # 타입이 수신 데이터라면
                    if self.buffer_bytes_flag is True:
                        self.data_buffer += socket_data
                    else:
                        self.data_buffer.append(socket_data)
                    self.received_time = datetime.datetime.now()
                    self.received_connect = True
                elif data_type == 'info':
                    # 타입이 정보 알림일 경우
                    self.logger.info(socket_data)
                elif data_type == 'connect':
                    # 타입이 연결 정보일 경우
                    self.connect_flag = socket_data
                    if socket_data is True:
                        self.received_time = datetime.datetime.now()
                        self.received_connect = False
                        if self.buffer_bytes_flag is True:
                            self.data_buffer = bytes()
                        else:
                            self.data_buffer.clear()
                else:
                    raise Exception("소켓 데이터의 타입을 알 수 없습니다.")
            except Exception as e:
                # 예외 발생 시
                self.logger.warning(f'Socket Data Error: {traceback.format_exc()}')

        try:
            if self.connect_flag is True:
                # 연결 되어있을 경우
                if self.receive_timeout != 0:
                    # 수신 타임아웃이 0이 아니라면
                    time_diff = datetime.datetime.now() - self.received_time
                    if time_diff >= datetime.timedelta(seconds=self.receive_timeout):
                        # 수신이 설정한 시간보다 안된 경우 강제 재접속
                        self.logger.warning(f"[{self.socket_name}] failed to receive data")
                        self.closeTCP()
        except Exception as e:
            self.logger.warning(f'[{self.socket_name}] Exception: {e}\n{traceback.format_exc()}')

    # TCP 소켓 닫기
    def closeTCP(self):
        self.connect_flag = False
        self.socket_send_queue.put(bytes(0))

    # 최종 TCP 소켓 닫기
    def finallyCloseTCP(self):
        self.logger.info(f'프로그램 종료 요청')
        self.socket_send_queue.put(bytes(1))
        self.tcp_socket_processing.join(timeout=1)
        if self.tcp_socket_processing.is_alive() is True:
            self.tcp_socket_processing.kill()
        self.logger.info(f'프로그램 종료 완료')


# TCP 소켓 프레임
class TcpSocketFrame(metaclass=ABCMeta):
    def __init__(self, program_name: str, parameter: dict,
                 send_queue: mp.Queue, recv_queue: mp.Queue,
                 logger: logging.Logger | None, stop_event: mp.Event):
        # 변수 선언
        self.stop_event: mp.Event = stop_event  # 프로그램 종료 여부
        self.data_buffer: bytes = bytes()
        self.data_index: int = 0
        self.task_list: list = []

        self.send_queue: mp.Queue = send_queue
        self.recv_queue: mp.Queue = recv_queue
        self.stop_event = stop_event

        ip_address = parameter.get("ip_address")
        port = parameter.get("port")
        bind_ip = parameter.get("bind_ip")
        server_flag = parameter.get("server_flag")
        socket_timeout = parameter.get("socket_timeout", None)
        receive_timeout = parameter.get("receive_timeout", 0)
        buffer_bytes_flag = parameter.get("buffer_bytes_flag", False)

        # 시리얼 통신 및 로거 설정
        self.socket_name: str = program_name
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger

        # 상태 관련 변수
        self.connect_flag: bool = None  # 연결 정보
        self.send_time: datetime.datetime = datetime.datetime.now()  # 보낸 시간
        self.write_time: datetime.datetime = datetime.datetime.now()  # 쓴 시간

        self.socket_module = TcpSocketModule(
            socket_name=program_name, ip_address=ip_address, port=port,
            socket_timeout=socket_timeout, receive_timeout=receive_timeout,
            buffer_bytes_flag=buffer_bytes_flag,
            server_flag=server_flag, bind_ip=bind_ip, logger=logger)

        # 수신 프로세스 실행
        self.socket_data_process_thread = ThreadWithException(self.socket_data_process)
        self.socket_data_process_thread.start()

    # 소멸자
    def __del__(self):
        self.close()

    def close(self):
        self.socket_module.finallyCloseTCP()
        self.socket_data_process_thread.raise_exception()
        self.logger.info("프로그램 종료")

    # 프로세스 시작
    async def run_process(self):
        # 보낼 데이터 처리
        self.task_list.append(asyncio.create_task(self.recv_process()))
        self.task_list.append(asyncio.create_task(self.send_process()))

        for task_item in self.task_list:
            await task_item

    def socket_data_process(self):
        while not self.stop_event.is_set():
            self.socket_module.socketDataProcess()
            time.sleep(0.01)

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
                            if self.socket_module.connect_flag is True:
                                data_dict: dict = send_dict.get("data")
                                self.send_data_process(data_dict)
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
                        self.logger.warning(f'Exception: {e}\n{traceback.format_exc()}')

                now_time = datetime.datetime.now()
                time_diff = now_time - self.write_time
                if time_diff >= datetime.timedelta(seconds=5):
                    self.all_send_data_process()
                    self.write_time = now_time
                self.send_connect_state()
            except Exception as e:
                self.logger.warning(f'송신 처리 도중 예외 발생: {e}\n{traceback.format_exc()}')
            await asyncio.sleep(0.01)

    # 수신 데이터 처리 프로세스
    async def recv_process(self):
        while self.stop_event.is_set() is False:
            # 프로그램 종료할때까지 동작
            while len(self.socket_module.data_buffer) != 0:
                try:
                    if self.socket_module.buffer_bytes_flag is True:
                        recv_data: bytes = self.socket_module.data_buffer
                    else:
                        recv_data: any = self.socket_module.data_buffer.popleft()
                    self.recv_data_process(recv_data)
                except Exception:
                    self.logger.warning(f"수신 처리 도중 예외 발생: {traceback.format_exc()}")
                await asyncio.sleep(0.001)
            await asyncio.sleep(0.01)

    # 연결 상태 보내기
    def send_connect_state(self):
        # 연결 상태 보내기
        now_connect_flag: bool = True if (self.socket_module.connect_flag is True and
                                          self.socket_module.received_connect is True) else False
        if self.connect_flag != now_connect_flag:
            self.recv_queue.put({
                "type": "connect",
                "data": now_connect_flag
            })
            self.connect_flag = now_connect_flag

    # 전체 송신 데이터 처리 (5초마다 전체 데이터 송신)
    @abstractmethod
    def all_send_data_process(self):
        pass

    # 보낼 데이터 처리
    @abstractmethod
    def send_data_process(self, send_data):
        pass

    # 받은 데이터 처리
    @abstractmethod
    def recv_data_process(self, recv_data):
        pass