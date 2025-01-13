# -*- coding: utf-8 -*-
import datetime
import traceback
import serial
import atexit

from src.main_server.module.logger import get_logger, LoggerPrint
from src.main_server.module.serial.serial_module import SerialModule
from logging import Logger


class SerialModuleProgram:
    # 생성자
    def __init__(self, program_name='serial', port: str = '/dev/ttyUSB0', baud: int = 19200, parity: str = "NONE",
                 serial_timeout: float | int = 0.0, receive_timeout: int = 0, logger: Logger = None):
        # Set Variable
        self.module_name: str = program_name
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger

        # Serial 관련 변수
        self.serial_module: SerialModule
        self.port: str = port
        self.baud: int = baud
        self.parity: str = parity
        self.serial_timeout: float = serial_timeout
        self.receive_timeout: int = receive_timeout
        self.data_buffer: bytes = bytes()   # 수신 데이터 버퍼

        # 상태 관련 변수
        self.close_count: int = 0  # 재 연결 카운트
        self.received_time: datetime.datetime = datetime.datetime.now()
        self.received_connect: bool = False  # 데이터 연결 여부
        self.connect_flag: bool = False  # 연결 정보

        self.initBasic()  # 기본 설정

        # 종료 시 선언
        atexit.register(self.finallyCloseSerial)

    # 소멸자
    def __del__(self):
        self.finallyCloseSerial()

    ########################################
    #       기본 설정 관련 함수 선언
    ########################################
    # 기본 설정
    def initBasic(self):
        parity = serial.PARITY_NONE
        if self.parity.upper() == 'EVEN':
            parity = serial.PARITY_EVEN
        elif self.parity.upper() == 'ODD':
            parity = serial.PARITY_ODD
        elif self.parity.upper() == 'MARK':
            parity = serial.PARITY_MARK
        elif self.parity.upper() == 'SPACE':
            parity = serial.PARITY_SPACE
        self.serial_module = SerialModule(self.port, self.baud, parity, self.serial_timeout)

    ########################################
    #       통신 설정 관련 함수 선언
    ########################################
    # 시리얼 통신 설정
    def setupSerial(self):
        self.logger.info(f'Serial Openning...')
        try:
            self.serial_module.setupSerial()
        except Exception as e:
            self.logger.warning(f'Serial connection failure:{e}')
        else:
            self.logger.info(f'Successfully opened serial port')
            self.data_buffer = bytes()
            self.received_connect = False
            self.received_time = datetime.datetime.now()

    # 시리얼 닫기
    def closeSerial(self):
        try:
            self.serial_module.closeSerial()
        except Exception:
            pass

    # 최종 시리얼 닫기
    def finallyCloseSerial(self):
        self.closeSerial()

    ########################################
    #           처리 관련 함수 선언
    ########################################
    # 타이머 콜백
    def timerCallback(self):
        try:
            if self.serial_module.serial_connect is True:
                # 데이터 가져오기
                self.data_buffer += self.serial_module.getSerialData()
                if self.receive_timeout != 0:
                    time_diff = datetime.datetime.now() - self.received_time
                    if time_diff >= datetime.timedelta(seconds=self.receive_timeout):
                        # 수신이 지정된 시간보다 안된 경우 강제 재접속
                        self.logger.warning(f'Failed to receive data')
                        self.closeSerial()
            else:
                # 연결이 되어있지 않은 경우 시리얼 연결
                self.setupSerial()
        except serial.SerialException as e:
            self.logger.warning(f'serial::IOException:{e}')
            self.closeSerial()
        except Exception as e:
            self.logger.warning(f'Exception: {e}\n{traceback.format_exc()}')
