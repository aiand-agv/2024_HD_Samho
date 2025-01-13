import asyncio
import logging
import time
import traceback
import multiprocessing as mp

from src.main_server.module.communication_module import change_signed_num
from src.main_server.module.logger import get_logger, LoggerPrint
from src.main_server.module.mc_protocol.mc_protocol_program import MCProtocolProgram
from src.main_server.module.modbus.modbus_module_program import ModbusModulePython
from src.main_server.module.move_avg_filter import move_avg_filter
from src.main_server.module.xgt_protocol import XgtProtocol


# XGT 프로토콜 실행
def run_xgt_protocol(program_name, xgt_protocol_param, device_types, device_data_info, send_queue, recv_queue, stop_event):
    xgt_protocol_logger = get_logger(program_name, stop_event=stop_event)
    xgt_protocol_program = XgtProtocol(program_name=program_name,
                                       xgt_protocol_param=xgt_protocol_param,
                                       device_types=device_types,
                                       device_data_info=device_data_info,
                                       send_queue=send_queue, recv_queue=recv_queue,
                                       logger=xgt_protocol_logger, stop_event=stop_event)
    try:
        asyncio.run(xgt_protocol_program.run_process())
    except Exception:
        xgt_protocol_logger.warning(f"{traceback.format_exc()}")
    finally:
        xgt_protocol_program.close()


# MC 프로토콜 실행
def run_mc_protocol(program_name, mc_protocol_param, device_types, device_data_info, send_queue, recv_queue, stop_event):
    mc_protocol_logger = get_logger(program_name, stop_event=stop_event)
    mc_protocol_program = MCProtocolProgram(program_name=program_name,
                                            mc_protocol_param=mc_protocol_param,
                                            device_types=device_types,
                                            device_data_info=device_data_info,
                                            send_queue=send_queue, recv_queue=recv_queue,
                                            logger=mc_protocol_logger, stop_event=stop_event)
    try:
        asyncio.run(mc_protocol_program.run_process())
    except Exception:
        mc_protocol_logger.warning(f"{traceback.format_exc()}")
    finally:
        mc_protocol_program.finallyCloseTCP()


# 모드버스 실행
def run_modbus(program_name, modbus_param, device_types, device_data_info, send_queue, recv_queue, stop_event):
    modbus_logger = get_logger(program_name, stop_event=stop_event)
    modbus_program = ModbusModulePython(program_name=program_name,
                                        modbus_param=modbus_param,
                                        data_types=device_types,
                                        data_info=device_data_info,
                                        send_queue=send_queue, recv_queue=recv_queue,
                                        logger=modbus_logger, stop_event=stop_event)
    try:
        asyncio.run(modbus_program.run_process())
    except Exception:
        modbus_logger.warning(f"{traceback.format_exc()}")
    finally:
        modbus_program.finallyCloseModbus()


# 데이터 통신 프로세스
class CommunicationProcessFrame:
    def __init__(self, logger: logging.Logger | None,
                 send_data_queue: mp.Queue, recv_data_queue: mp.Queue,
                 ls_plc_address_param: dict, ls_plc_device_types: dict, ls_plc_device_data_info: dict,
                 melsec_plc_address_param: dict, melsec_plc_device_types: dict, melsec_plc_device_data_info: dict,
                 modbus_address_param: dict, modbus_data_types: dict, modbus_data_info: dict,
                 data_filter: dict, stop_event: mp.Event):
        self.send_data_queue: mp.Queue = send_data_queue  # 보낼 데이터 큐
        self.recv_data_queue: mp.Queue = recv_data_queue  # 받은 데이터 큐
        self.stop_event: mp.Event = stop_event

        self.ls_plc_address_param = ls_plc_address_param
        self.ls_plc_device_types = ls_plc_device_types
        self.ls_plc_device_data_info = ls_plc_device_data_info

        self.melsec_plc_address_param = melsec_plc_address_param
        self.melsec_plc_device_types = melsec_plc_device_types
        self.melsec_plc_device_data_info = melsec_plc_device_data_info

        self.modbus_address_param = modbus_address_param
        self.modbus_data_types = modbus_data_types
        self.modbus_data_info = modbus_data_info

        self.data_filter = data_filter

        self.task_list: list = []  # 비동기 통신 리스트
        self.comm_data_dict = {}
        if logger is None:
            self.logger = LoggerPrint("communication_process")
        else:
            self.logger = logger
        asyncio.run(self.run_process())

    def __del__(self):
        self.close()

    def close(self):
        self.logger.info(f'프로그램을 종료합니다.')
        for module_name, module_data in self.comm_data_dict.items():
            self.logger.info(f'[{module_name}] 프로그램 종료 요청을 합니다.')
            module_data["send_queue"].put({"type": "exit"})
        for module_name, module_data in self.comm_data_dict.items():
            try:
                if module_data["process"].is_alive():
                    module_data["process"].join(timeout=1)
                    module_data["process"].kill()
            except:
                pass
        self.logger.info(f'프로그램을 종료 완료')

    # 프로세스 시작
    async def run_process(self):
        # LS 산전 PLC init
        for ls_plc_name, ls_plc_address_param_data in self.ls_plc_address_param.items():
            device_types: dict = self.ls_plc_device_types.get(ls_plc_name)
            device_data_info: dict = self.ls_plc_device_data_info.get(ls_plc_name)
            send_queue = mp.Queue()
            recv_queue = mp.Queue()
            self.comm_data_dict[ls_plc_name] = {
                "process": mp.Process(target=run_xgt_protocol,
                                      args=(ls_plc_name, ls_plc_address_param_data, device_types, device_data_info,
                                            send_queue, recv_queue, self.stop_event),
                                      name=ls_plc_name),
                "send_queue": send_queue,
                "recv_queue": recv_queue,
            }
            self.comm_data_dict[ls_plc_name]["process"].start()
            self.task_list.append(asyncio.create_task(self.recv_data_process(ls_plc_name)))

        # MELSEC PLC init
        for melsec_plc_name, melsec_plc_address_param_data in self.melsec_plc_address_param.items():
            device_types: dict = self.melsec_plc_device_types.get(melsec_plc_name)
            device_data_info: dict = self.melsec_plc_device_data_info.get(melsec_plc_name)
            send_queue = mp.Queue()
            recv_queue = mp.Queue()
            self.comm_data_dict[melsec_plc_name] = {
                "process": mp.Process(target=run_mc_protocol,
                                      args=(
                                      melsec_plc_name, melsec_plc_address_param_data, device_types, device_data_info,
                                      send_queue, recv_queue, self.stop_event),
                                      name=melsec_plc_name),
                "send_queue": send_queue,
                "recv_queue": recv_queue
            }
            self.comm_data_dict[melsec_plc_name]["process"].start()
            self.task_list.append(asyncio.create_task(self.recv_data_process(melsec_plc_name)))

        # Modbus init
        for modbus_name, modbus_address_param_data in self.modbus_address_param.items():
            device_types: dict = self.modbus_data_types.get(modbus_name)
            device_data_info: dict = self.modbus_data_info.get(modbus_name)
            send_queue = mp.Queue()
            recv_queue = mp.Queue()
            self.comm_data_dict[modbus_name] = {
                "process": mp.Process(target=run_modbus,
                                      args=(
                                      modbus_name, modbus_address_param_data, device_types, device_data_info,
                                      send_queue, recv_queue, self.stop_event),
                                      name=modbus_name),
                "send_queue": send_queue,
                "recv_queue": recv_queue
            }
            self.comm_data_dict[modbus_name]["process"].start()
            self.task_list.append(asyncio.create_task(self.recv_data_process(modbus_name)))

        self.custom_add_communication()

        # 보낼 데이터 처리
        self.task_list.append(asyncio.create_task(self.send_data_process()))

        for task_item in self.task_list:
            await task_item

    ###############################################
    # 보낼 데이터 처리
    ###############################################
    async def send_data_process(self):
        """
        self.send_data_queue 타입 정의
        {
            "type": 타입 (데이터 보내기[send] | 프로그램 종료[exit])
            "module_name": 모듈 이름
            "data": {
                "데이터 이름": 데이터
            }
        }
        :return:
        """

        while not self.stop_event.is_set():
            while self.send_data_queue.qsize() != 0:
                # 보낼 데이터가 존재한다면
                try:
                    send_data_dict: dict = self.send_data_queue.get()
                    self.logger.info(f"[send_data_process] {send_data_dict}")

                    send_type: str = send_data_dict.get("type")
                    module_name: str = send_data_dict.get("module_name")
                    send_data: dict = send_data_dict.get("data")

                    if send_type == "send":
                        # 데이터가 보낼 데이터라면
                        self.comm_data_dict[module_name]["send_queue"].put({
                            "type": "send",
                            "data": send_data
                        })

                        # 받은 데이터 보내기
                        self.recv_data_queue.put({
                            "type": "send_data",
                            "module_name": module_name,
                            "data": send_data
                        })
                    elif send_type == "exit":
                        # 데이터가 종료라면 프로그램 종료
                        self.close()
                        return
                    elif send_type == "disable":
                        # 비활성화 해제/설정
                        flag: bool = send_data.get("flag", False)
                        self.comm_data_dict[module_name]["send_queue"].put({
                            "type": "disable",
                            "data": flag
                        })
                        self.recv_data_queue.put({
                            "type": "send_data",
                            "module_name": module_name,
                            "data": {
                                "disable": flag
                            }
                        })
                    elif send_type == "reconnect":
                        # 재연결 요청
                        self.comm_data_dict[module_name]["send_queue"].put({
                            "type": "reconnect"
                        })
                except Exception:
                    self.logger.warning(f"[send_data_process] 데이터 송신 처리 도중 예외가 발생하였습니다. 예외 메시지: {traceback.format_exc()}")
            await asyncio.sleep(0.01)

    ###############################################
    # 수신 데이터 처리 프로세스
    ###############################################
    async def recv_data_process(self, module_name):
        # 수신 데이터 큐
        recv_queue = self.comm_data_dict[module_name]["recv_queue"]

        # 이동 평균 필터 적용
        move_avg_filter_data = self.data_filter.get(module_name, {}).get("move_avg_filter", {})
        move_avg_filter_data_list = {}

        # 부호 제거
        unsigned_datas = self.data_filter.get(module_name, {}).get("unsigned", {})

        # 신호 반전
        reversed_sgn_datas = self.data_filter.get(module_name, {}).get("reversed_sgn", {})

        while not self.stop_event.is_set():
            recv_device_data = {}

            while recv_queue.qsize() != 0:
                recv_queue_data: dict = recv_queue.get()
                self.logger.info(f"[recv_data_process] [{module_name}] {recv_queue_data}")

                recv_type: str = recv_queue_data.get("type")
                recv_datas: any = recv_queue_data.get("data")

                if recv_type == "connect":
                    # 연결 정보일 경우
                    self.recv_data_queue.put({
                        "type": "connect",
                        "module_name": module_name,
                        "data": recv_datas
                    })
                elif recv_type == "receive":
                    for recv_name, recv_data in recv_datas.items():
                        ############################################################
                        # 부호 변환
                        ############################################################
                        unsigned_data = unsigned_datas.get(recv_name)
                        if unsigned_data is not None:
                            recv_data = change_signed_num(recv_data)
                            recv_datas[recv_name] = recv_data

                        ############################################################
                        # 신호 반전
                        ############################################################
                        reversed_sgn_data = reversed_sgn_datas.get(recv_name)
                        if reversed_sgn_data is not None:
                            recv_datas[recv_name] = not recv_data

                        ############################################################
                        # 이동 평균 필터 적용
                        ############################################################
                        move_avg_filter_count = move_avg_filter_data.get(recv_name)
                        if move_avg_filter_count is not None:
                            # 이동 평균 필터 적용해야할 데이터라면
                            move_avg_filter_list = move_avg_filter_data_list.get(recv_name)
                            if move_avg_filter_list is None:
                                move_avg_filter_list = [recv_data] * move_avg_filter_count
                            avg_data, avg_list = move_avg_filter(move_avg_filter_list, recv_data)
                            move_avg_filter_data_list[recv_name] = avg_list
                            recv_data = round(avg_data)
                            recv_datas[recv_name] = recv_data
                    recv_device_data.update(recv_datas)

            # 보낼 데이터가 존재한다면 데이터 통합 프로세스에게 보내기
            if len(recv_device_data) != 0:
                self.recv_data_queue.put({
                    "type": "recv_data",
                    "module_name": module_name,
                    "data": recv_device_data
                })
            await asyncio.sleep(0.01)

    def custom_add_communication(self):
        pass
