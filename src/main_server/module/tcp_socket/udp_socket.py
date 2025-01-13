import datetime
import socket
import time
import threading
import multiprocessing as mp
import asyncio

from abc import *  # 추상 클래스 사용


# 소켓 클래스 틀
class UdpSocketFrame(metaclass=ABCMeta):
    # 생성자
    # host : 서버 주소
    # port : 서버 포트
    # socket_type : 소켓 타입 (예시: acs_client)
    # received_queue : 받은 데이터를 저장하는 큐
    # send_queue : 서버에 전송할 데이터 큐
    def __init__(self, host: str, port: int, socket_type: str, received_queue: mp.Queue, send_queue: mp.Queue,
                 timeout=None):
        self.host: str = host  # 서버 주소
        self.port: int = port  # 포트 번호
        self.socket_type: str = socket_type  # 소켓 타입 (예시: acs_client)
        self.received_queue: mp.Queue = received_queue  # 수신 데이터 큐
        self.send_queue: mp.Queue = send_queue  # 송신 데이터 큐
        self.timeout = timeout

        self.server_socket: socket = None  # 서버 소켓
        self.client_socket: socket = None  # 연결된 클라이언트 소켓

        self.socket_start = True  # 소켓 시작 여부 (False 일 경우 종료)
        self.init_start_flag = False  # 초기화 시작 여부
        self.client_connect = False  # 소켓 클라이언트 연결 여부
        self.disable_flag = False  # 비활성화 여부
        self.connect_fail = False  # 연결 실패 여부 (로그 1회 용)

        threading.Thread(target=self.received_process).start()
        asyncio.run(self.socketProcess())

    # 소멸자
    def __del__(self):
        # 소켓 열려있으면 닫기
        self.close_socket()

    # 소켓 프로세스
    async def socketProcess(self):
        init_socket_task = asyncio.create_task(self.init_process())
        send_process_task = asyncio.create_task(self.send_process())

        # 동기 작업 시작
        await init_socket_task
        await send_process_task

    # 소켓 초기화 (추상 메소드)
    @abstractmethod
    def init_socket(self):
        pass

    # 소켓 닫기 (추상 메소드)
    @abstractmethod
    def close_socket(self):
        pass

    # 소켓 연결 (추상 메소드)
    @abstractmethod
    def socketConnect(self):
        pass

    # 서버 재시작
    def client_restart(self):
        self.send_state("재시작하기 위해 종료합니다.", state_type='info')
        self.close_socket()  # 클라이언트 닫기
        self.init_start_flag = False
        self.connect_fail = False

    # 초기화 프로세스
    async def init_process(self):
        while self.socket_start is True:
            if self.client_connect is False and self.disable_flag is False:
                # 연결이 해제되었다면
                if self.init_start_flag is False:
                    self.init_start_flag = True
                    self.init_socket()
                    self.client_connect = True
                    self.send_state(True, state_type='connect')  # 연결 여부 보내기
                # if self.socketConnect() is True:
                #     # 접속 성공
                #
            await asyncio.sleep(1)

    # 수신 프로세스
    # 만약에 빈 데이터가 50개 들어오면 끊겼다고 판단하고 서버 재접속 시도
    # 예외 발생 시 서버가 끊겼다고 판단하고 서버 재접속 시도
    def received_process(self):
        not_data_count: int = 0
        while self.socket_start is True:
            if self.client_connect is True:
                # 클라이언트가 열려있다면
                try:
                    # 서버 수신 데이터 처리
                    received_data: bytes = self.client_socket.recvfrom(1024)
                    if not received_data:
                        # 빈 데이터 (빈데이터가 50개 들어오면 닫혔다고 판단)
                        if not_data_count >= 50:
                            not_data_count = 0
                            raise Exception("빈 데이터가 연속으로 들어옴")
                        not_data_count += 1
                    else:
                        self.send_state(received_data, state_type='receive')
                except Exception as e:
                    pass
                    # if self.socket_start is True and self.client_connect is True:
                    #     self.send_state('데이터 수신 도중 예외가 발생하여 재시작합니다. 예외 메시지: ' + str(e), state_type='error')
                    #     self.client_restart()
            time.sleep(0.01)

    # 송신 프로세스
    # send_queue에 데이터가 있을 경우 해당 데이터를 송신함
    async def send_process(self):
        while self.socket_start is True:
            # 서버 수신 데이터 처리
            while self.send_queue.qsize() > 0:
                # 보낼 데이터가 들어있을 경우
                try:
                    send_data: bytes = self.send_queue.get()
                    if send_data == bytes(0):
                        # 데이터가 0 바이트로 들어왔다면 재시작
                        self.send_state('재시작 명령이 들어와 재시작 합니다.', state_type='info')
                        self.client_restart()
                        continue
                    elif send_data == bytes(1):
                        # 데이터가 1 바이트로 들어왔다면 종료
                        self.socket_start = False
                        self.close_socket()
                        return
                    elif send_data == bytes(2):
                        # 데이터가 2 바이트로 들어왔다면 비활성화, 활성화 설정
                        self.disable_flag = not self.disable_flag
                        self.close_socket()
                        self.send_state(f"{'비활성화 설정' if self.disable_flag is True else '비활성화 해제'}합니다.", state_type='info')
                        continue
                    else:
                        if self.client_connect is True:
                            # 클라이언트가 열려있다면 데이터 보내기
                            self.client_socket.sendto(send_data, self.host)
                            await asyncio.sleep(0.01)
                except Exception as e:
                    self.send_state('예외가 발생했습니다. 예외 메시지: ' + str(e), state_type='error')
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.01)

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
        self.received_queue.put(state_data)


# 소켓 클라이언트 클래스
class SocketClient(UdpSocketFrame):

    # 클라이언트 초기화
    def init_socket(self):
        self.send_state("클라이언트를 시작합니다.", state_type='info')
        self.client_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.client_socket.settimeout(self.timeout)  # 타임 아웃 설정

    # 소켓 연결
    def socketConnect(self):
        try:
            if self.connect_fail is False:
                self.send_state("서버에 연결을 시도합니다...", state_type='info')
            self.client_socket.connect((self.host, self.port))
            self.send_state("서버에 연결되었습니다.", state_type='info')
            return True
        except Exception as e:
            # 접속 실패 시 2초 후 다시 접속
            if self.connect_fail is False:
                self.send_state('서버에 연결 도중 예외가 발생하였습니다. 예외 메시지: ' + str(e), state_type='error')
                self.connect_fail = True  # 로그 1회
        return False

    # 클라이언트 닫기
    def close_socket(self):
        if self.client_socket is not None:
            self.client_socket.close()
        self.client_connect = False
        self.send_state(False, state_type='connect')  # 연결 여부 보내기


# 소켓 서버 클래스
class SocketServer(UdpSocketFrame):
    # 서버 초기화
    def init_socket(self):
        self.send_state("서버를 시작합니다.", state_type='info')

    # 소켓 연결
    def socketConnect(self):
        try:
            if self.connect_fail is False:
                self.send_state("서버를 설정합니다...", state_type='info')
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.settimeout(self.timeout)  # 타임 아웃 설정
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.server_socket.bind((self.host, self.port))

            # 서버가 클라이언트의 접속 허용
            self.server_socket.listen()

            # accept 함수에서 대기하다가 클라이언트가 접속하면 새로운 소켓을 리턴합니다.
            self.client_socket, connect_addr = self.server_socket.accept()
            self.send_state("클라이언트가 접속 했습니다. 클라이언트 주소 :" + str(connect_addr), state_type='info')
            return True
        except Exception as e:
            if self.connect_fail is False:
                self.send_state("서버 설정 도중 예외가 발생했습니다. 예외 메시지: " + str(e), state_type='error')
                self.connect_fail = True   # 로그 1회
        return False

    # 소켓 닫기
    def close_socket(self):
        if self.client_socket is not None:
            self.client_socket.close()
        if self.server_socket is not None:
            self.server_socket.close()
        self.client_connect = False
        self.send_state(False, state_type='connect')  # 연결 여부 보내기


def udp_socket_server_start(host: str, port: int, socket_type: str, received_queue: mp.Queue, send_queue: mp.Queue,
                            timeout=None):
    print("소켓 서버 실행")
    SocketServer(host, port, socket_type, received_queue, send_queue, timeout)


def udp_socket_client_start(host: str, port: int, socket_type: str, received_queue: mp.Queue, send_queue: mp.Queue,
                            timeout=None):
    print("소켓 클라이언트 실행")
    SocketClient(host, port, socket_type, received_queue, send_queue, timeout)
