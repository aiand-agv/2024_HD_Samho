import struct

# 리스트 형태의 bool(bit)를 숫자로 변환
def bool_list_to_number(bool_list: list = [], num_type: str = "short", is_signed: bool = False):
    bit_len: int = 8
    format_type: str = "B"
    if num_type == "char":
        # 0 ~ 255 / -128 ~ 127
        bit_len *= 1
        format_type = ">b" if is_signed is True else "B"
    elif num_type == "short":
        # 0 ~ 65,535 / -32768 ~ 32767
        bit_len *= 2
        format_type = "h" if is_signed is True else "H"
    elif num_type == "int":
        # 0 ~ 4,294,967,295 / -2,147,483,648 ~ 2,147,483,647
        bit_len *= 4
        format_type = "i" if is_signed is True else "I"
    elif num_type == "float":
        # -3.4 x 10^38 ~ 3.4 x 10^38
        bit_len *= 4
        format_type = "f"
    elif num_type == "double":
        # -1.8 x 10^308 ~ 1.8 x 10^308
        bit_len *= 8
        format_type = "d"

    bit_list: list = [False] * bit_len
    bool_list_len: int = len(bool_list)
    if bool_list_len > bit_len:
        # 지정된 크기보다 클 경우 경우 뒤에 짜르기
        bool_list = bool_list[:bit_len]
    bit_list[0:bool_list_len] = bool_list

    return_int: bytes = bytes()
    for i in range(0, bit_len, 8):
        return_int += struct.pack("B", int(''.join(['1' if i is True else '0' for i in bit_list[i:i + 8][::-1]]), 2))
    return struct.unpack(format_type, return_int)[0]


def bool_list_to_bytes(bool_list: list = []) -> bytes:
    bit_list: list = [False] * 16
    bool_list_len: int = len(bool_list)
    if bool_list_len > 16:
        # 16개 보다 이상일 경우 뒤에 짜르기
        bool_list = bool_list[:16]
    bit_list[0:bool_list_len] = bool_list

    return_int: bytes = bytes()
    return_int += struct.pack("B", int(''.join(['1' if i is True else '0' for i in bit_list[0:8][::-1]]), 2))
    return_int += struct.pack("B", int(''.join(['1' if i is True else '0' for i in bit_list[8:16][::-1]]), 2))
    return return_int


# 디바이스 데이터 변환
# device_data : 디바이스 데이터
# device_type : 디바이스 데이터 타입
# conversion_type : 디바이스 데이터 타입을 변환할 데이터 타입
# device_signed : 디바이스 데이터 부호 여부
# conversion_signed : 변환 데이터의 부호 여부
def deviceDataConversion(device_data: any, device_type: str, conversion_type: str, device_signed=True,
                         conversion_signed=True) -> any:
    conversion_data = device_data
    if device_type in ['short', 'int']:
        if conversion_type == 'bool':
            # short/int -> bool
            conversion_data = int2Bool(device_data, device_type)
        elif conversion_type == 'float':
            # short/int -> float
            conversion_data = int2Float(device_data)
        elif conversion_type == 'string':
            conversion_data = int2Str(device_data)
        elif device_signed != conversion_signed:
            # 부호 변환
            conversion_data = intTransformSigned(device_data, device_type, device_signed)
    elif device_type == 'bool':
        if conversion_type in ['short', 'int']:
            # bool -> short/int
            conversion_data = bool_list_to_number(device_data, num_type=conversion_type, is_signed=conversion_signed)
        else:
            conversion_data = 0
    elif device_type == 'string':
        if conversion_type == 'short':
            # string -> short
            conversion_data = str2Int(device_data[:2])
        elif conversion_type == 'int':
            # string -> int
            conversion_data = str2Int(device_data[:4])
        else:
            conversion_data = 0
    return conversion_data


# 문자열 -> 정수형
def str2Int(data: str) -> int:
    conversion_data = 0
    for i in range(len(data)):
        try:
            ascii_code: int = ord(data[i])
            if ascii_code <= 255:
                conversion_data += ascii_code << (8 * i)
            else:
                conversion_data += 0
        except:
            conversion_data = 0
    return conversion_data


# 정수형 -> 문자열
def int2Str(data: int) -> str:
    if data & 0xff == 0 and data >> 8 == 0:
        return ''
    elif data & 0xff == 0 and data >> 8 == -128:
        return ''
    else:
        return chr(data & 0xff) + chr(data >> 8)


# 정수형 -> 실수형
def int2Float(data: int):
    return struct.unpack('f', struct.pack('i', data))[0]


# 숫자형 -> Boolean 형
def int2Bool(data: int, data_type: str) -> list[bool]:
    data_type_hex = 0xffff if data_type == 'short' else 0xffffffff
    bool_list = [True if i == '1' else False for i in bin(data & data_type_hex)[2:][::-1]]
    bool_list_len = len(bool_list)
    if data_type == 'short' and bool_list_len < 16:
        bool_list += [False] * (16 - bool_list_len)
    elif data_type == 'int' and bool_list_len < 32:
        bool_list += [False] * (32 - bool_list_len)
    return bool_list


# int형 부호 변환
def intTransformSigned(data: int, data_type: str, is_signed: bool) -> int:
    data_type = (0xffff, 0x8000) if data_type == 'short' else (0xffffffff, 0x80000000)
    if is_signed is True:
        # 부호가 있을 경우
        return data & data_type[0]
    else:
        # 부호가 없을 경우
        data = data & data_type[0]
        return data | (-(data & data_type[1]))


def bytes_to_number(data_item: bytes) -> int:
    data_format = "b"
    length = len(data_item)
    if length == 2:
        data_format = "<h"
    elif length == 4:
        data_format = "<i"
    return struct.unpack(data_format, data_item)[0]


def number_to_bytes(data_item: int, length: int) -> bytes:
    data_format = "b"
    if length == 2:
        data_format = "<h"
    elif length == 4:
        data_format = "<i"
    return bytes(struct.pack(data_format, data_item))


# ====================================================
#                  소켓 수신 처리 부분
# ====================================================
# char 데이터 타입 가져오기
def getCharData(data_item: bytes) -> str:
    return data_item.decode()


# float 데이터 타입 가져오기
def getFloatData(data_item: bytes) -> float:
    return round(struct.unpack('f', data_item)[0], 4)


# bit 데이터 타입 가져오기
def getBitData(data_item: bytes) -> list:
    return [False if bin(ord(data_item) & (1 << i)) == '0b0' else True for i in range(0, 8)]


# int 데이터 타입 가져오기
def getIntData(data_item: bytes) -> int:
    return struct.unpack("B" if len(data_item) == 1 else ">H", data_item)[0]


# Num 타입 가져오기 (문자형 숫자)
def getNumData(data_item: bytes) -> int:
    return int(data_item)


# Bool 타입 가져오기 (문자형 Bool)
def getBoolData(data_item: bytes) -> bool:
    return True if getCharData(data_item) == "1" else False


# Word 데이터 가져오기 (2바이트 bit) [MC 프로토콜]
def getWordData(data_item: int) -> list:
    # bytes 로 바꾸기
    int_data: bytes = setIntData(data_item, 2)

    bit_data: list = []
    for i in int_data:
        bit_data += getBitData(setIntData(i))

    return bit_data


# ====================================================
#                  소켓 송신 처리 부분
# ====================================================
# 빈 공간 채우기
def setSpareData(byte_data: bytes, length: int) -> bytes:
    len_data = len(byte_data)
    if len_data >= length:
        # 데이터 길이가 총 길이보다 크거나 같으면
        byte_data = byte_data[:length]
    else:
        # 그렇지 않다면
        byte_data += bytes(length - len_data)
    return byte_data


# char 데이터 타입 설정
def setCharData(data_item: any, length: int) -> bytes:
    return bytes(str(data_item).ljust(length, '0')[:length].encode())


# float 데이터 타입 설정
def setFloatData(data_item: float) -> bytes:
    return bytes(struct.pack('f', data_item))


# bit 데이터 타입 설정
def setBitData(data_item: list, length: int) -> bytes:
    return setIntData(int(''.join(['1' if i is True else '0' for i in data_item[::-1]]).rjust(8, '0')[:8], 2), length)


# int 데이터 타입 설정
def setIntData(data_item: int, length: int = 1) -> bytes:
    return bytes(struct.pack("B" if length == 1 else ">H", data_item))


# Num 타입 설정 (문자형 숫자)
def setNumData(data_item: int, length: int) -> bytes:
    return setCharData(format(data_item, f'0{length}'), length)


# Bool 타입 설정 (문자형 Bool)
def setBoolData(data_item: bool, length: int = 1):
    return setCharData("1" if data_item is True else "0", length)


# Word 타입 설정 (2바이트 bit) [MC 프로토콜]
def setWordData(data_item: list) -> int:
    return int(''.join(['1' if i is True else '0' for i in data_item[::-1]]).rjust(16, '0')[:16], 2)


# 0 ~ 65,535 <-> -32,768 ~ 32,768에 맞게 변환 시켜주는 함수
# -1 => 65535
# 65535 => -1
def change_signed_num(num):
    if num & 0x8000:  # 최상위 비트가 1인지 확인하여 음수 판별
        signed_num = -((num ^ 0xffff) + 1)
    else:
        signed_num = num
    return signed_num


# 체크섬 계산
def calculate_checksum(data: bytes):
    checksum = 0
    for byte in data:
        checksum = (checksum + byte) & 0xFF
    return checksum
