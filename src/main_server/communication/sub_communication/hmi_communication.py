import logging
import multiprocessing as mp
import traceback
import datetime
import orjson

from src.main_server.module.collection_of_functions import json_default
from src.main_server.module.communication_module import setSpareData, calculate_checksum, getIntData, setIntData
from src.main_server.module.tcp_socket.tcp_socket_module import TcpSocketFrame


# HMI 통신
class HmiCommunication(TcpSocketFrame):
    def __init__(self, program_name: str, parameter: dict,
                       send_queue: mp.Queue, recv_queue: mp.Queue,
                       logger: logging.Logger | None, stop_event: mp.Event):
        parameter['buffer_bytes_flag'] = True
        self.hmi_number = parameter.get("hmi_number")
        self.header_code = parameter.get("header_code")
        super().__init__(program_name, parameter, send_queue, recv_queue, logger, stop_event)

    # 전체 송신 데이터 처리 (5초마다 전체 데이터 송신)
    def all_send_data_process(self):
        pass

    # 보낼 데이터 처리
    def send_data_process(self, send_data):
        send_time: str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        send_data_dict: dict = {
            'send': 'ACS',
            'number': self.hmi_number,
            'time': send_time,
            'data': send_data
        }
        try:
            data_json: bytes = orjson.dumps(send_data_dict, default=json_default)
            send_data_byte: bytes = bytes()

            header_len = len(self.header_code)
            send_data_byte += setSpareData(self.header_code.encode('utf-8'), header_len)
            send_data_byte += setIntData(len(data_json), 2)
            send_data_byte += data_json
            send_data_byte += bytes([calculate_checksum(data_json)])
            self.socket_module.socket_send_queue.put(send_data_byte)
            self.logger.info(f'[SEND] 송신 시간: {send_time} | 보낼 데이터: {send_data}')
        except Exception:
            self.logger.warning(f'[SEND] 송신 처리 도중 예외가 발생하였습니다. 송신 시간: {send_time} | 보낼 데이터: {send_data} | 예외 메시지: {traceback.format_exc()}')

    # 받은 데이터 처리 1
    def recv_data_process(self, recv_data):
        while len(recv_data) >= 10:
            try:
                if recv_data[:8] == setSpareData(self.header_code.encode('utf-8'), 8):
                    # 헤더 코드와 맞을 경우
                    data_length: int = getIntData(recv_data[8:10])
                    if len(recv_data) >= data_length + 11:
                        data: bytes = recv_data[10:data_length+10]
                        checksum: int = recv_data[data_length+10]
                        recv_data = recv_data[data_length+11:]
                        clac_checksum = calculate_checksum(data)
                        if clac_checksum == checksum:
                            # 체크섬 비교 후 맞다면
                            data_dict = orjson.loads(data)
                            self.received_data_process(data_dict)
                        else:
                            # 체크섬 비교 후 맞지않다면 에러 발생
                            raise Exception(f'체크섬이 맞지 않습니다. 수신 체크섬: {checksum} 확인 체크섬: {clac_checksum}')
                    else:
                        # 길이가 맞지않다면 끝내기
                        break
                else:
                    # 헤더 코드와 맞지 않을 경우 끝내기
                    raise Exception(f'헤더 코드가 맞지 않습니다. 수신 헤더: {self.data_buffer[:8]}')
            except Exception as e:
                recv_data = bytes()
                self.logger.warning(f'Error: {traceback.format_exc()}')
                break
        self.socket_module.data_buffer = recv_data

    # 받은 데이터 처리 2
    def received_data_process(self, data_dict: dict):
        now_time: datetime.datetime = datetime.datetime.now()
        received_time: str = now_time.strftime('%Y-%m-%d %H:%M:%S')
        send_time: str = data_dict.get('time')
        send_type: str = data_dict.get('send')
        number: str = data_dict.get('number')
        data: dict = data_dict.get('data')

        if send_type != 'HMI' or number != self.hmi_number:
            # 보낸 주체와 번호가 맞지 않다면 끝내기
            self.logger.warning(f'Error: 송신 주체가 맞지 않습니다.')
        else:
            data["recv_time"] = now_time
            self.recv_queue.put({
                "type": "receive",
                "data": data
            })
        self.logger.info(f'[RECV] 수신 시간: {received_time} | 상대 송신 시간: {send_time} | 받은 데이터: {data}')
