# -*- coding: utf-8 -*-
# https://pymodbus.readthedocs.io/en/latest/
# 읽기 쓰기 참조: https://pymodbus.readthedocs.io/en/latest/source/library/client.html#modbus-calls
from pymodbus.exceptions import ModbusException
from pymodbus.client import ModbusTcpClient as ModbusClient


class ModbusModule:
    # 생성자
    def __init__(self, ip_address='192.168.127.254', port=502, timeout=1.0):
        self.modbus_module: ModbusClient = None  # 모드버스 클라이언트
        self.ip_address: str = ip_address
        self.port: int = port
        self.timeout: float = timeout
        self.modbus_connect: bool = False  # 모드버스 접속 여부

    # 소멸자
    def __del__(self):
        self.closeModbus()

    ########################################
    #      모드버스 설정 관련 함수 선언
    ########################################
    # 모드 버스 닫기
    def closeModbus(self):
        self.modbus_connect = False
        try:
            self.modbus_module.close()
        except Exception:
            pass

    # 모드버스 통신 설정
    def setupModbus(self):
        try:
            self.modbus_module = ModbusClient(self.ip_address, port=self.port, timeout=1.0)
            if self.modbus_module.connect() is False:
                self.modbus_connect = False
                raise Exception()
        except ModbusException as e:
            self.closeModbus()
            raise Exception(e)
        except Exception as e:
            self.modbus_connect = False
            raise Exception(e)
        else:
            self.modbus_connect = True

    ########################################
    #       데이터 쓰기 관련 함수 선언
    ########################################
    # Write Coil (1개씩 쓰기)
    def writeCoil(self, address: int = 0, value: bool = False):
        # Digital Output 데이터 쓰기
        write_result = self.modbus_module.write_coil(address, value, slave=0x1)

        # 에러라면 Exception 발생
        if write_result.isError():
            raise Exception(write_result)

    # Write Coils (여러개 쓰기)
    def writeCoils(self, start_address: int = 0, value_list: list = [False]):
        # Digital Output 데이터 쓰기
        write_result = self.modbus_module.write_coils(start_address, value_list, slave=0x1)

        # 에러라면 Exception 발생
        if write_result.isError():
            raise Exception(write_result)

    # Write Register (1개씩 쓰기)
    def writeRegister(self, address: int = 0, value: int = 0):
        # Analog Output 데이터 쓰기
        write_result = self.modbus_module.write_register(address, value, slave=0x1)

        # 에러라면 Exception 발생
        if write_result.isError():
            raise Exception(write_result)

    # Write Registers (여러개 쓰기)
    def writeRegisters(self, start_address: int = 0, value_list: list = [0]):
        # Analog Output 데이터 쓰기
        write_result = self.modbus_module.write_registers(start_address, value_list, slave=0x1)

        # 에러라면 Exception 발생
        if write_result.isError():
            raise Exception(write_result)

    ########################################
    #       데이터 읽기 관련 함수 선언
    ########################################
    # Read Coils (Code: 0x01)
    def readCoils(self, start_address: int = 0, count: int = 1) -> list:
        # Digital Input 데이터 가져오기
        read_result = self.modbus_module.read_coils(start_address, count, slave=0x1)
        # 에러라면 Exception 발생
        if read_result.isError():
            raise Exception(read_result)

        return read_result.bits

    # Read Discrete Inputs (Code: 0x02)
    def readDiscreteInputs(self, start_address: int = 0, count: int = 1) -> list:
        # Digital Input 데이터 가져오기
        read_result = self.modbus_module.read_discrete_inputs(start_address, count, slave=0x1)
        # 에러라면 Exception 발생
        if read_result.isError():
            raise Exception(read_result)

        return read_result.bits

    # Read Holding Registers (Code: 0x03)
    def readHoldingRegisters(self, start_address: int = 0, count: int = 1) -> list:
        # Analog Input 데이터 가져오기
        read_result = self.modbus_module.read_holding_registers(start_address, count, slave=0x1)
        # 에러라면 Exception 발생
        if read_result.isError():
            raise Exception(read_result)

        return read_result.registers

    # Read Input Registers (Code: 0x04)
    def readInputRegisters(self, start_address: int = 0, count: int = 1) -> list:
        # Analog Input 데이터 가져오기
        read_result = self.modbus_module.read_input_registers(start_address, count, slave=0x1)
        # 에러라면 Exception 발생
        if read_result.isError():
            raise Exception(read_result)

        return read_result.registers
