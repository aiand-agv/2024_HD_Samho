# -*- coding: utf-8 -*-
import serial
# https://pyserial.readthedocs.io/en/latest/pyserial.html


class SerialModule:
    # 생성자
    def __init__(self, port='/dev/ttyUSB0', baud=19200, parity=serial.PARITY_NONE, timeout=0.0):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.parity = parity

        # Serial 관련 변수
        self.serial_module: serial.Serial

        # 상태 관련 변수
        self.serial_connect: bool = False             # 연결 여부

    # 소멸자
    def __del__(self):
        self.closeSerial()

    ########################################
    #     시리얼 통신 설정 관련 함수 선언
    ########################################
    # 시리얼 통신 설정
    def setupSerial(self):
        try:
            print(f'Serial Openning...')
            self.serial_module = serial.Serial()
            self.serial_module.port = self.port
            self.serial_module.baudrate = self.baud
            self.serial_module.parity = self.parity
            self.serial_module.timeout = self.timeout
            self.serial_module.open()
        except serial.SerialException as e:
            self.closeSerial()
            raise Exception(e)
        else:
            self.serial_connect = True

    # 시리얼 닫기
    def closeSerial(self):
        self.serial_connect = False
        try:
            self.serial_module.close()
        except Exception:
            pass

    ########################################
    #    데이터 쓰기/읽기 관련 함수 선언
    ########################################
    # 시리얼 데이터 가져오기
    def getSerialData(self, bytes_size: int = 1024) -> bytes:
        return self.serial_module.read(bytes_size)

    # 시리얼 데이터 보내기
    def sendSerialData(self, send_data_byte: bytes):
        self.serial_module.write(send_data_byte)
