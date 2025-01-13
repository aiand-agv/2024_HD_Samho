import asyncio
import multiprocessing as mp
import traceback

from src.main_server.communication.acs_communication_parameter import other_address_param, agv_address_param
from src.main_server.communication.sub_communication.agv_communication import AgvCommunication
from src.main_server.communication.sub_communication.hmi_communication import HmiCommunication
from src.main_server.module.communication_process_module import CommunicationProcessFrame
from src.main_server.module.logger import get_logger


# HMI 통신 실행
def run_hmi_communication(program_name, parameter, send_queue, recv_queue, stop_event):
    custom_logger = get_logger(program_name, stop_event=stop_event, console_flag=False)
    custom_program = HmiCommunication(program_name=program_name,
                                      parameter=parameter,
                                      send_queue=send_queue, recv_queue=recv_queue,
                                      logger=custom_logger, stop_event=stop_event)
    try:
        asyncio.run(custom_program.run_process())
    except Exception:
        custom_logger.warning(f"{traceback.format_exc()}")
    finally:
        custom_program.close()


# AGV 통신 실행
def run_agv_communication(program_name, parameter, send_queue, recv_queue, stop_event):
    custom_logger = get_logger(program_name, stop_event=stop_event, console_flag=False)
    custom_program = AgvCommunication(program_name=program_name,
                                      parameter=parameter,
                                      send_queue=send_queue, recv_queue=recv_queue,
                                      logger=custom_logger, stop_event=stop_event)
    try:
        asyncio.run(custom_program.run_process())
    except Exception:
        custom_logger.warning(f"{traceback.format_exc()}")
    finally:
        custom_program.close()


class CommunicationProcess(CommunicationProcessFrame):
    # 사용자 정의 통신 추가
    def custom_add_communication(self):
        for hmi_name, hmi_address_param_data in other_address_param.items():
            send_queue = mp.Queue()
            recv_queue = mp.Queue()
            self.comm_data_dict[hmi_name] = {
                "process": mp.Process(target=run_hmi_communication,
                                      args=(
                                      hmi_name, hmi_address_param_data,
                                      send_queue, recv_queue, self.stop_event),
                                      name=hmi_name),
                "send_queue": send_queue,
                "recv_queue": recv_queue
            }
            self.comm_data_dict[hmi_name]["process"].start()
            self.task_list.append(asyncio.create_task(self.recv_data_process(hmi_name)))

        for agv_name, agv_address_param_data in agv_address_param.items():
            send_queue = mp.Queue()
            recv_queue = mp.Queue()
            self.comm_data_dict[agv_name] = {
                "process": mp.Process(target=run_agv_communication,
                                      args=(
                                      agv_name, agv_address_param_data,
                                      send_queue, recv_queue, self.stop_event),
                                      name=agv_name),
                "send_queue": send_queue,
                "recv_queue": recv_queue
            }
            self.comm_data_dict[agv_name]["process"].start()
            self.task_list.append(asyncio.create_task(self.recv_data_process(agv_name)))


def start_communication_process(send_data_queue: mp.Queue, recv_data_queue: mp.Queue,
                                ls_plc_address_param: dict, ls_plc_device_types: dict, ls_plc_device_data_info: dict,
                                melsec_plc_address_param: dict, melsec_plc_device_types: dict, melsec_plc_device_data_info: dict,
                                modbus_address_param: dict, modbus_data_types: dict, modbus_data_info: dict,
                                data_filter: dict, stop_event: mp.Event):
    comm_logger = get_logger("communication_process", stop_event=stop_event, console_flag=False)
    try:
        CommunicationProcess(comm_logger, send_data_queue, recv_data_queue,
                             ls_plc_address_param, ls_plc_device_types, ls_plc_device_data_info,
                             melsec_plc_address_param, melsec_plc_device_types,
                             melsec_plc_device_data_info,
                             modbus_address_param, modbus_data_types, modbus_data_info,
                             data_filter, stop_event)
    except Exception as e:
        comm_logger.warning(f"예외 발생 {traceback.format_exc()}")
        if stop_event.is_set() is False:
            stop_event.set()
