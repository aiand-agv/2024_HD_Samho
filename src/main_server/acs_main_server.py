import multiprocessing as mp
import asyncio
import traceback
import gc
import datetime
import time
from http.client import responses

from logging import Logger

from src.command_server.command_server import start_command_server
from src.database.curd import get_all_composition_list
from src.database.database import get_db
from src.main_server.communication.acs_communication_parameter import ls_plc_address_param, ls_plc_device_types, \
    ls_plc_device_data_info, melsec_plc_address_param, melsec_plc_device_types, melsec_plc_device_data_info, \
    modbus_address_param, modbus_data_types, modbus_data_info, data_filter
from src.main_server.communication.acs_communication_process import start_communication_process
from src.main_server.acs_main_server_parameter import watchdogs_process_parameter, ping_process_parameter
from src.main_server.module.fastapi_module import get_id
from src.main_server.module.logger import get_logger
from src.main_server.module.main_server_module import MainServerProcessFrame
from src.main_server.module.ping_process import start_ping_process
from src.main_server.module.thread_with_exception import ThreadWithException
from src.api_server.domain.acs_main.main_parameter import agv_module_name_description


# 메인 서버 프로세스
class MainServerProcess(MainServerProcessFrame):
    def __init__(self, program_name: str, api_send_queue_queue: mp.Queue, api_recv_queue_queue: mp.Queue,
                 comm_send_data_queue: mp.Queue, comm_recv_data_queue: mp.Queue,
                 cmd_send_data_queue: mp.Queue, cmd_recv_data_queue: mp.Queue,
                 watchdogs_process_param: dict, logger: Logger | None, stop_event: mp.Event):
        super().__init__(program_name, api_send_queue_queue, api_recv_queue_queue,
                         comm_send_data_queue, comm_recv_data_queue, watchdogs_process_param, logger, stop_event)
        self.cmd_queue = {
            "recv": cmd_recv_data_queue,
            "send": cmd_send_data_queue
        }
        self.send_integrate_queue["cmd_recv"] = cmd_recv_data_queue
        self.agv_working_sgn_data = {}
        self.response_cmd = {}  # CMD 응답 데이터

        self.agv_list = set(agv_module_name_description.keys())

        self.all_send_count: int = 0
        self.acs_emergency_stop: bool = False  # ACS 비상정지
        self.emg_stop: dict = {}               # 개별 ACS 비상 정지

    async def api_request_process(self, request_data_dict: dict):
        request_type: str = request_data_dict.get("type")  # 데이터 타입
        working_id: int = request_data_dict.get("working_id")
        request_data: any = request_data_dict.get("data")  # 데이터

        if request_type == "set_emergency_stop":
            # 비상 정지 요청
            ThreadWithException(self.request_emergency_stop, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] 비상 정지 요청 ({request_data})")
        elif request_type == "set_emg_mode":
            # 비상 정지 요청
            ThreadWithException(self.request_emergency_stop, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] 비상 모드 요청 ({request_data})")
        elif request_type == "set_acs_emergency_stop":
            # 비상 정지 요청
            ThreadWithException(self.request_emergency_stop, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] ACS 비상 정지 요청 ({request_data})")
        elif request_type == "set_disable":
            # 비활성화 설정
            ThreadWithException(self.request_disable, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] ACS 비활성화 요청 ({request_data})")
        elif request_type == "set_auto_mode":
            # 자동모드 설정
            ThreadWithException(self.request_auto_mode, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] AGV 자동 모드 설정 요청 ({request_data})")
        elif request_type == "set_cmd_agv":
            ThreadWithException(self.request_cmd_agv, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] AGV 명령 요청 ({request_data})")
        elif request_type == "cmd_delete":
            ThreadWithException(self.request_cmd_management, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] 명령 삭제 요청 ({request_data})")
        elif request_type == "wait_clear":
            ThreadWithException(self.request_cmd_management, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] 대기 명령 해제 요청 ({request_data})")
        elif request_type == "cmd_stop":
            ThreadWithException(self.request_cmd_management, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] 명령 정지 해제 요청 ({request_data})")
        elif request_type == "cmd_restart":
            ThreadWithException(self.request_cmd_management, request_type, working_id, request_data).start()
            self.logger.info(f"[api_send_data_process] 명령 재시작 요청 ({request_data})")

    # 대기 명령 해제 요청
    def request_cmd_management(self, args):
        request_type: str = args[0]
        working_id: int = args[1]
        request_data: dict = args[2]

        response_data = {
            "type": "response",
            "data": {
                "working_id": working_id,
                "flag": False
            }
        }

        module_name: str = request_data.get('module_name')
        module_data: dict | None = self.integrate_data.get(module_name)
        if module_data is not None:
            request_data["working_id"] = working_id
            self.cmd_queue["recv"].put({
                "type": request_type,
                "data": request_data
            })
            response_dict = self.response_cmd_checking(working_id, request_type)
            if response_dict.get("success_flag") is True:
                cmd_response_data: dict | None = response_dict.get("data")
                if cmd_response_data is not None:
                    response_data["data"]["flag"] = cmd_response_data.get("flag", False)
                    response_data["data"]["msg"] = cmd_response_data.get("msg", "" if response_data["data"]["flag"] is True else "알 수 없음")
                else:
                    response_data["data"]["msg"] = "응답 데이터가 없습니다"
            else:
                response_data["data"]["flag"] = False
                response_data["data"]["msg"] = response_dict.get("msg", "알 수 없음")
        else:
            response_data["data"]["msg"] = "해당 AGV는 존재하지 않습니다"
        self.api_queue["recv"].put(response_data)

        try:
            del self.response_cmd[request_type][working_id]
        except Exception:
            pass

    # 비상 정지 요청
    def request_emergency_stop(self, args):
        request_type: str = args[0]
        working_id: int = args[1]
        request_data: dict = args[2]
        module_name = request_data.get("module_name")
        emergency_flag = request_data.get("flag")

        response_data = {
            "type": "response",
            "data": {
                "working_id": working_id,
                "flag": False
            }
        }
        if request_type == "set_acs_emergency_stop":
            for module_name_item in self.agv_list:
                self.comm_data_queue["send"].put({
                    "type": "send",
                    "module_name": module_name_item,
                    "data": {
                        "emg_stop": emergency_flag
                    }
                })
            response_data["data"]["flag"] = True
            self.acs_emergency_stop = emergency_flag
        elif request_type == "set_emg_mode":
            module_data: dict | None = self.integrate_data.get(module_name)
            if module_data is not None:
                if module_data.get("connect", False) is True:
                    self.comm_data_queue["send"].put({
                        "type": "send",
                        "module_name": module_name,
                        "data": {
                            "emg_mode": emergency_flag
                        }
                    })
                    response_data["data"]["flag"] = True
                else:
                    response_data["data"]["msg"] = "현재 연결이 되어있지 않습니다."
            else:
                response_data["data"]["msg"] = "해당 모듈이 존재하지 않습니다."
        else:
            # set_emergency_stop
            module_data: dict | None = self.integrate_data.get(module_name)
            if module_data is not None:
                if module_data.get("connect", False) is True:
                    self.comm_data_queue["send"].put({
                        "type": "send",
                        "module_name": module_name,
                        "data": {
                            "emg_stop": emergency_flag
                        }
                    })
                    response_data["data"]["flag"] = True
                else:
                    response_data["data"]["msg"] = "현재 연결이 되어있지 않습니다."
            else:
                response_data["data"]["msg"] = "해당 모듈이 존재하지 않습니다."
            self.emg_stop[module_name] = emergency_flag
        self.api_queue["recv"].put(response_data)

    # 비활성화 요청
    def request_disable(self, args):
        request_type: str = args[0]
        working_id: int = args[1]
        request_data: dict = args[2]
        module_name = request_data.get("module_name")
        disable_flag = request_data.get("flag")

        response_data = {
            "type": "response",
            "data": {
                "working_id": working_id,
                "flag": False
            }
        }
        module_data: dict | None = self.integrate_data.get(module_name)
        if module_data is not None:
            self.comm_data_queue["send"].put({
                "type": "disable",
                "module_name": module_name,
                "data": {
                    "flag": disable_flag
                }
            })
            response_data["data"]["flag"] = True
        else:
            response_data["data"]["msg"] = "해당 모듈이 존재하지 않습니다."
        self.api_queue["recv"].put(response_data)

    # 자동모드 요청
    def request_auto_mode(self, args):
        request_type: str = args[0]
        working_id: int = args[1]
        request_data: dict = args[2]
        module_name = request_data.get("module_name")
        auto_mode_flag = request_data.get("flag")

        response_data = {
            "type": "response",
            "data": {
                "working_id": working_id,
                "flag": False
            }
        }
        module_data: dict | None = self.integrate_data.get(module_name)
        if module_data is not None:
            response_data["data"]["flag"] = True
            self.cmd_queue["recv"].put({
                "type": "set_auto_mode",
                "data": {
                    "module_name": module_name,
                    "flag":auto_mode_flag
                }
            })
        else:
            response_data["data"]["msg"] = "해당 모듈이 존재하지 않습니다."
        self.api_queue["recv"].put(response_data)

    # 호출 요청
    def request_call(self, args):
        request_type: str = args[0]
        working_id: int = args[1]
        request_data: dict = args[2]

        send_data: dict = {
            "type": request_type,
            "data": request_data
        }
        return_data = self.response_checking("acs_communication", "emg_stop", send_data, "hmi_response")
        response_data = {
            "type": "response",
            "data": {
                "working_id": working_id,
                "flag": return_data.get("success_flag"),
                "msg": return_data.get("msg")
            }
        }
        if return_data.get("success_flag") is True and return_data.get("data") is not None:
            response_data["data"]["flag"] = return_data["data"].get("flag", False)
            response_data["data"]["msg"] = return_data["data"].get("msg", False)
        self.api_queue["recv"].put(response_data)

    # 응답 확인
    def response_cmd_checking(self, working_id: int = 0, response_type: str = ""):
        return_data = {
            "success_flag": False,
            "msg": "응답이 없습니다"
        }

        # 시작 시간
        start_time = datetime.datetime.now()
        while not self.stop_event.is_set():
            # 응답이 왔는지 확인
            response_data: dict | None = self.response_cmd.get(response_type)
            print(response_data)
            if response_data is not None:
                # 응답이 있음
                if response_data.get(working_id) is not None:
                    return_data["success_flag"] = True
                    return_data["data"] = response_data[working_id]
            now_time = datetime.datetime.now()
            if now_time - start_time >= datetime.timedelta(seconds=2):
                # 2초 동안 응답이 없으면 자동 OFF
                break
            time.sleep(0.1)
        return return_data

    # AGV 명령 요청
    def request_cmd_agv(self, args):
        request_type: str = args[0]
        working_id: int = args[1]
        request_data: dict = args[2]
        module_name = request_data.get("module_name")
        loading = request_data.get("loading")
        unloading = request_data.get("unloading")
        arrival = request_data.get("arrival")

        module_name = "agv_1"
        loading = "agv_1_4"
        unloading = "agv_1_8"
        arrival = "agv_1_10"

        hmi_response = self.request_cmd_agv_process(module_name, loading, unloading, arrival)
        response_data = {
            "type": "response",
            "data": {
                "working_id": working_id
            }
        }
        response_data["data"]["flag"] = hmi_response["flag"]
        response_data["data"]["msg"] = hmi_response["msg"]
        self.api_queue["recv"].put(response_data)

    # AGV 명령 처리
    def request_cmd_agv_process(self, agv_module_name, loading_position, unloading_position, arrival_position):
        success_flag = False
        working_id = get_id()
        self.send_add_cmd(working_id, agv_module_name, loading_position, unloading_position, arrival_position, False, True)
        response_dict = self.response_cmd_checking(working_id, "add_cmd")

        if response_dict.get("success_flag") is True:
            cmd_response_data: dict | None = response_dict.get("data")
            if cmd_response_data is not None:
                success_flag = cmd_response_data.get("flag", False)
                msg = cmd_response_data.get("msg", "없음")
            else:
                msg = "응답 데이터가 없습니다"
        else:
            msg = response_dict.get("msg", "알 수 없음")
        return {
            "flag": success_flag,
            "msg": msg
        }

    # 수신 통합 데이터 처리
    async def recv_integrate_data_process(self, module_name, recv_data):
        if module_name in self.agv_list:
            agv_state_data = recv_data.get("agv_state")
            if agv_state_data is not None:
                acs_emg_stop = agv_state_data.get("acs_emg_stop")
                if acs_emg_stop is not None:
                    if self.acs_emergency_stop is not acs_emg_stop:
                        # ACS 비상정지 On인데 안걸려있다면 재전송
                        send_acs_emg_stop = self.acs_emergency_stop
                        cmd_acs_emg_stop = self.emg_stop.get(module_name, False)
                        if self.acs_emergency_stop is False:
                            if cmd_acs_emg_stop is not acs_emg_stop:
                                send_acs_emg_stop = cmd_acs_emg_stop
                            else:
                                return
                        self.comm_data_queue["send"].put({
                            "type": "send",
                            "module_name": module_name,
                            "data": {
                                "emg_stop": send_acs_emg_stop
                            }
                        })

    # 유저 메인 처리
    async def user_main_process(self, second_flag, hour_flag, day_flag):
        all_send_flag: bool = False
        if second_flag is True:
            self.all_send_count += 1

            if self.all_send_count >= 5:
                self.all_send_count = 0
                all_send_flag = True

        # 작업 데이터 5초마다 전송
        if all_send_flag is True:
            for agv_module_name, agv_module_data in self.agv_working_sgn_data.items():
                for module_name, module_data in agv_module_data.items():
                    if len(module_data) != 0:
                        self.comm_data_queue["send"].put({
                            "type": "send",
                            "module_name": module_name,
                            "data": module_data
                        })


    # CMD 데이터 처리
    async def cmd_data_process(self):
        while not self.stop_event.is_set():
            while self.cmd_queue["send"].qsize() != 0:
                try:
                    cmd_queue_data: dict = self.cmd_queue["send"].get()
                    cmd_type: str = cmd_queue_data['type']
                    cmd_module_name: str = cmd_queue_data.get("module_name")
                    cmd_data: any = cmd_queue_data.get('data')

                    if cmd_type == 'send':
                        # 보내는 데이터라면
                        self.comm_data_queue["send"].put(cmd_queue_data)
                    elif cmd_type == 'working_sgn_data':
                        # 신호 데이터라면
                        self.send_cmd_working_data(cmd_data, cmd_module_name, clear_flag=False)
                    # elif cmd_type == 'working_sgn_data_clear':
                    #     # 신호 데이터 초기화라면
                    #     self.send_cmd_working_data(cmd_data, cmd_module_name, clear_flag=True)
                    elif cmd_type == 'working_sgn_data_all_clear':
                        # 신호 데이터 초기화라면
                        self.send_cmd_working_data(cmd_data, cmd_module_name, all_clear=True)
                    elif cmd_type == 'response_cmd':
                        # 작업 관련 응답이라면
                        self.set_cmd_response(cmd_data)
                    elif cmd_type == 'event':
                        # 이벤트라면
                        self.api_queue["recv"].put(cmd_queue_data)
                except Exception:
                    self.logger.warning(f"[cmd_data_process] 예외 발생: {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # 명령 응답 설정
    def set_cmd_response(self, cmd_data):
        response_type = cmd_data.get("type")
        working_id = cmd_data.get("working_id")
        data = cmd_data.get("data", "")
        if response_type is not None and working_id is not None:
            if self.response_cmd.get(response_type) is None:
                self.response_cmd[response_type] = {}
            self.response_cmd[response_type][working_id] = data

    # 다른 AGV 작업 신호 확인
    def other_cmd_working_data_check(self, agv_module_name, module_name, data_name):
        for _agv_module_name, _agv_module_data in self.agv_working_sgn_data.items():
            if _agv_module_name == agv_module_name:
                continue
            if _agv_module_data.get(module_name, {}).get(data_name) is None:
                return False
            else:
                return True

    # CMD 신호 데이터 보내기 (clear_flag 기능 제거: 241208 테스트 후 정리 예정)
    def send_cmd_working_data(self, cmd_data: dict, agv_module_name: str, clear_flag: bool = False, all_clear: bool = False):
        if self.agv_working_sgn_data.get(agv_module_name) is None:
            self.agv_working_sgn_data[agv_module_name] = {}

        if all_clear is True:
            cmd_data = self.agv_working_sgn_data[agv_module_name]
        for module_name, module_data in cmd_data.items():
            if self.agv_working_sgn_data[agv_module_name].get(module_name) is None:
                self.agv_working_sgn_data[agv_module_name][module_name] = {}

            if all_clear is True or clear_flag is True:
                for data_name, data_value in module_data.items():
                    if self.other_cmd_working_data_check(agv_module_name, module_name, data_name) is False:
                        # 다른 AGV 작업 신호가 없을 경우 초기화
                        module_data[data_name] = False if type(data_value) == bool else 0
                    del self.agv_working_sgn_data[agv_module_name][module_name][data_name]
            else:
                self.agv_working_sgn_data[agv_module_name][module_name].update(module_data)

            if module_name == "acs":
                self.cmd_queue["recv"].put({
                    "type": "integrate_data",
                    "data": {
                        "acs": module_data
                    }
                })
            else:
                self.comm_data_queue["send"].put({
                    "type": "send",
                    "module_name": module_name,
                    "data": module_data
                })

    # 명령 추가 보내기
    def send_add_cmd(self, working_id, agv_module_name, loading_position, unloading_position, arrival_position, auto_flag, force_flag=False):
        work_idx = 1

        self.cmd_queue["recv"].put({
            "type": "add_cmd",
            "data": {
                "working_id": working_id,
                "module_name": agv_module_name,
                "work_idx": work_idx,
                "auto_flag": auto_flag,
                "unloading_position": loading_position,
                "loading_position": unloading_position,
                "arrival_position": arrival_position,
                "force_flag": force_flag   # 강제 여부 (동일 작업 무시)
            }
        })

# 메인 프로세스 동작
async def run_main_process(api_send_queue_queue: mp.Queue, api_recv_queue_queue: mp.Queue,
                           comm_send_data_queue: mp.Queue, comm_recv_data_queue: mp.Queue,
                           cmd_send_data_queue: mp.Queue, cmd_recv_data_queue: mp.Queue,
                           watchdogs_process_param: dict, main_logger: Logger | None, stop_event: mp.Event):
    data_integration_process = MainServerProcess("main_server",
                                                 api_send_queue_queue, api_recv_queue_queue,
                                                 comm_send_data_queue, comm_recv_data_queue,
                                                 cmd_send_data_queue, cmd_recv_data_queue,
                                                 watchdogs_process_param, main_logger, stop_event)
    task_list = [
        asyncio.create_task(data_integration_process.api_data_process()),
        asyncio.create_task(data_integration_process.comm_data_process()),
        asyncio.create_task(data_integration_process.main_process()),
        asyncio.create_task(data_integration_process.cmd_data_process())
    ]
    for task_item in task_list:
        await task_item


# 메인 서버 시작
def start_main_server(api_send_queue, api_recv_queue, stop_event):
    main_logger = get_logger("main_server", stop_event=stop_event, console_flag=False)

    comm_send_data_queue: mp.Queue = mp.Queue()
    comm_recv_data_queue: mp.Queue = mp.Queue()
    comm_data_process = mp.Process(target=start_communication_process,
                                   args=(comm_send_data_queue, comm_recv_data_queue,
                                         ls_plc_address_param, ls_plc_device_types, ls_plc_device_data_info,
                                         melsec_plc_address_param, melsec_plc_device_types, melsec_plc_device_data_info,
                                         modbus_address_param, modbus_data_types, modbus_data_info,
                                         data_filter, stop_event),
                                   name="communication_process")
    comm_data_process.start()

    ping_process = mp.Process(target=start_ping_process,
                              args=(ping_process_parameter, comm_recv_data_queue, stop_event),
                              name="ping_process")
    ping_process.start()

    cmd_send_data_queue: mp.Queue = mp.Queue()
    cmd_recv_data_queue: mp.Queue = mp.Queue()
    cmd_process = mp.Process(target=start_command_server,
                              args=(cmd_send_data_queue, cmd_recv_data_queue, stop_event),
                              name="command_server")
    cmd_process.start()

    try:
        asyncio.run(run_main_process(api_send_queue, api_recv_queue, comm_send_data_queue, comm_recv_data_queue,
                                     cmd_send_data_queue, cmd_recv_data_queue,
                                     watchdogs_process_parameter, main_logger, stop_event))
    except Exception as e:
        main_logger.warning(f"예외 발생 {traceback.format_exc()}")
        if stop_event.is_set() is False:
            stop_event.set()
        send_kill_data = {
            "type": "exit"
        }
        comm_send_data_queue.put(send_kill_data)
        comm_recv_data_queue.put(send_kill_data)
        cmd_send_data_queue.put(send_kill_data)
        cmd_recv_data_queue.put(send_kill_data)

    # ==========================
    # 프로세스 종료
    # ==========================
    if comm_data_process.is_alive():
        comm_data_process.join(1)
        comm_data_process.kill()
    if ping_process.is_alive():
        ping_process.join(1)
        ping_process.kill()
    if cmd_process.is_alive():
        cmd_process.join(1)
        cmd_process.kill()