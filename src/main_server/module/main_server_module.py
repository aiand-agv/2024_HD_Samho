import copy
import multiprocessing as mp
import asyncio
import traceback
import gc
import datetime
import time

from logging import Logger
from src.main_server.module.logger import saveLogZip, LoggerPrint
from src.main_server.module.watchdogs_process import WatchdogsProcess


# 메인 서버 프로세스
class MainServerProcessFrame:
    def __init__(self, program_name: str, api_send_queue_queue: mp.Queue, api_recv_queue_queue: mp.Queue,
                 comm_send_data_queue: mp.Queue, comm_recv_data_queue: mp.Queue,
                 watchdogs_process_parameter: dict, logger: Logger | None, stop_event: mp.Event):
        # 로그
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger

        # PLC 데이터 큐
        self.comm_data_queue: dict = {
            "send": comm_send_data_queue,   # 보낼 데이터 큐
            "recv": comm_recv_data_queue   # 받은 데이터 큐
        }
        # API 통신 데이터 큐
        self.api_queue: dict = {
            "send": api_send_queue_queue,   # API 기준 보낸 데이터 큐
            "recv": api_recv_queue_queue    # API 기준 받는 데이터 큐
        }
        self.send_integrate_queue: dict = {
            "api_recv": api_recv_queue_queue
        }

        self.stop_event: mp.Event = stop_event

        # 연결 여부 데이터
        self.connect_data = {}

        # 비활성화 데이터
        self.disable_data = {}

        # 통합 데이터
        self.integrate_data = {}

        # 웹서버에 보낼 통합 데이터
        self.send_integrate_data = {}

        # 와치독스 파라미터
        self.watchdogs_data = WatchdogsProcess(watchdogs_process_parameter)

    # API 데이터 처리
    async def api_data_process(self):
        while not self.stop_event.is_set():
            while self.api_queue["send"].qsize() != 0:
                try:
                    request_data: dict = self.api_queue["send"].get()
                    await self.api_request_process(request_data)
                except Exception:
                    self.logger.warning(f"[api_send_data_process] 예외 발생: {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # 3 핸드 쉐이킹 확인
    def three_hand_shaking(self, module_name, send_data: dict = {},
                           on_flag_list: list = [], check_flag_list: list = [], get_data_list: list = []):
        return_data = {
            "success_flag": False,
            "msg": "응답이 없습니다"
        }

        send_data.update({on_flag: True for on_flag in on_flag_list})
        self.comm_data_queue["send"].put({
            "type": "send",
            "module_name": module_name,
            "data": send_data
        })

        # 시작 시간
        start_time = datetime.datetime.now()
        while not self.stop_event.is_set():
            # 응답이 왔는지 확인
            return_check = []
            module_datas = self.integrate_data.get(module_name, {})
            for check_flag in check_flag_list:
                return_check.append(module_datas.get(check_flag, False))
            if all(return_check) is True:
                # 응답이 왔으면 넘기기
                return_data["success_flag"] = True
                if len(get_data_list) != 0:
                    response_data = {data_name: module_datas.get(data_name, False) for data_name in get_data_list}
                    return_data["data"] = response_data
                break
            now_time = datetime.datetime.now()
            if now_time - start_time >= datetime.timedelta(seconds=4):
                # 4초 동안 응답이 없으면 자동 OFF
                break
            time.sleep(0.1)

        # 응답이 왔으면 OFF
        self.comm_data_queue["send"].put({
            "type": "send",
            "module_name": module_name,
            "data": {on_flag: False for on_flag in on_flag_list}
        })
        return return_data

    # 응답 확인
    def response_checking(self, module_name, request_type: str = "", send_request_data: dict = {}, response_type: str = ""):
        return_data = {
            "success_flag": False
        }

        self.comm_data_queue["send"].put({
            "type": "send",
            "module_name": module_name,
            "data": {
                request_type: send_request_data
            }
        })

        # 시작 시간
        start_time = datetime.datetime.now()
        while not self.stop_event.is_set():
            # 응답이 왔는지 확인
            response_data: dict | None = self.integrate_data.get(module_name, {}).get(response_type)
            if response_data is not None:
                # 응답이 왔으면
                recv_time = response_data.get("recv_time")
                if recv_time is not None:
                    if start_time <= recv_time:
                        # 응답 시간이 시작 시간보다 클 경우 응답 OK
                        return_data["success_flag"] = True
                        return_data["data"] = response_data
                        break
            now_time = datetime.datetime.now()
            if now_time - start_time >= datetime.timedelta(seconds=4):
                # 4초 동안 응답이 없으면 자동 OFF
                break
            time.sleep(0.1)
        if return_data["success_flag"] is False:
            return_data["msg"] = "응답이 없습니다"
        return return_data

    # 통신 데이터 처리 프로세스
    async def comm_data_process(self):
        while not self.stop_event.is_set():
            while self.comm_data_queue["recv"].qsize() != 0:
                try:
                    recv_data_dict: dict = self.comm_data_queue["recv"].get()
                    self.logger.info(f"[comm_data_process] {recv_data_dict}")
                    recv_type: str = recv_data_dict.get("type")             # 데이터 타입
                    module_name: str = recv_data_dict.get("module_name")    # 모듈 이름 - master_plc 등
                    recv_data: any = recv_data_dict.get("data")             # 받은 데이터

                    pre_integrate_data = self.integrate_data.get(module_name)
                    if pre_integrate_data is None:
                        # 해당 모듈(예: master_plc)의 데이터가 존재하지않다면 새로 생성
                        self.integrate_data[module_name] = {}

                    if self.send_integrate_data.get(module_name) is None:
                        # 해당 모듈 (예: master_plc)의 데이터가 존재하지않다면 새로 생성
                        self.send_integrate_data[module_name] = {}

                    if self.connect_data.get(module_name) is None:
                        self.connect_data[module_name] = {
                            "recv_connect_flag": False,
                            "count": 0,
                            "connect_flag": False
                        }
                    if recv_type == "exit":
                        return
                    elif recv_type == "connect":
                        # 데이터 타입이 연결이라면
                        if recv_data is True:
                            # 연결이 되었다면 연결 여부 True
                            connect_data = {"connect": recv_data}
                            self.integrate_data[module_name].update(connect_data)
                            self.send_integrate_data[module_name].update(connect_data)
                            self.connect_data[module_name]["connect_flag"] = recv_data
                        self.connect_data[module_name]["recv_connect_flag"] = recv_data
                        self.connect_data[module_name]["count"] = 0

                        if recv_data is True:
                            # 연결이 되었다면 수신 와치독스 초기화
                            watchdogs_data = self.watchdogs_data.get_watchdogs_data(module_name, "recv")
                            if watchdogs_data is not None:
                                watchdogs_data["time"] = datetime.datetime.now()

                    elif recv_type == "recv_data":
                        # 데이터 타입이 받은 데이터라면
                        watchdogs_data = self.watchdogs_data.get_watchdogs_data(module_name, "recv")
                        if watchdogs_data is not None:
                            # 와치독스 처리
                            watchdogs_key = watchdogs_data["key"]
                            watchdogs_value = recv_data.get(watchdogs_key)
                            if watchdogs_value is not None:
                                watchdogs_data["value"] = watchdogs_value
                                watchdogs_data["time"] = datetime.datetime.now()

                        await self.recv_integrate_data_process(module_name, recv_data)
                        if type(recv_data) == dict:
                            for key, value in recv_data.items():
                                if type(value) == dict:
                                    if self.integrate_data[module_name].get(key) is None:
                                        self.integrate_data[module_name][key] = {}
                                    if self.send_integrate_data[module_name].get(key) is None:
                                        self.send_integrate_data[module_name][key] = {}
                                    self.integrate_data[module_name][key].update(value)
                                    self.send_integrate_data[module_name][key].update(value)
                                else:
                                    self.integrate_data[module_name][key] = value
                                    self.send_integrate_data[module_name][key] = value
                        else:
                            self.integrate_data[module_name].update(recv_data)
                            self.send_integrate_data[module_name].update(recv_data)
                    elif recv_type == "send_data":
                        # 데이터 타입이 보냈던 데이터라면
                        self.integrate_data[module_name].update(recv_data)
                        self.send_integrate_data[module_name].update(recv_data)
                    elif recv_type == "ping_data":
                        # 데이터 타입이 핑 데이터라면
                        self.integrate_data[module_name].update(recv_data)
                        self.send_integrate_data[module_name].update(recv_data)
                except Exception:
                    print(traceback.format_exc())
            await asyncio.sleep(0.01)

    # 메인 처리
    async def main_process(self):
        pre_second = -1
        pre_hour = -1
        pre_day = 0
        while not self.stop_event.is_set():
            try:
                now_time = datetime.datetime.now()
                second_flag: bool = False
                hour_flag: bool = False
                day_flag: bool = False

                # ================================
                # 가비지 컬렉션
                # ================================
                now_second: int = now_time.second
                if pre_second != now_second:
                    # 1초마다 AGV 갱신 요청
                    second_flag = True
                    if pre_hour != now_time.hour:
                        # 정각이 되었다면
                        hour_flag = True
                        gc.collect()   # 가비지 컬렉션 실행
                        pre_hour = now_time.hour
                    # 초 갱신
                    pre_second = now_second

                # =================================
                # 로그 저장
                # =================================
                try:
                    if now_time.day != pre_day:
                        day_flag = True
                        self.logger.info("[LOG] 로그 저장")
                        saveLogZip()
                        pre_day = now_time.day
                except Exception:
                    self.logger.info(f"[LOG] 로그 실패: {traceback.format_exc()}")

                # ================================
                # 연결 여부 처리
                # ================================
                if second_flag is True:
                    for module_name, module_data in self.connect_data.items():
                        connect_flag: bool = module_data["connect_flag"]
                        recv_connect_flag: bool = module_data["recv_connect_flag"]
                        if connect_flag is True:
                            ####################################
                            # 연결 여부 처리
                            ####################################
                            if recv_connect_flag is False:
                                # 연결되어있는데 수신 연결 여부가 해제되었다면 카운트 진행
                                connect_count: int = module_data["count"]
                                if connect_count > 5:
                                    pass
                                else:
                                    if connect_count == 5:
                                        # 5초 되었으면 연결 해제 표시
                                        connect_data = {"connect": False}
                                        self.connect_data[module_name]["connect_flag"] = False
                                        self.integrate_data[module_name].update(connect_data)
                                        if self.send_integrate_data.get(module_name) is None:
                                            # 해당 모듈 (예: master_plc)의 데이터가 존재하지않다면 새로 생성
                                            self.send_integrate_data[module_name] = {}
                                        self.send_integrate_data[module_name].update(connect_data)
                                    self.connect_data[module_name]["count"] += 1

                            # 와치독스 보내기
                            send_watchdogs_data = self.watchdogs_data.get_watchdogs_data(module_name, "send")
                            if send_watchdogs_data is not None:
                                self.comm_data_queue["send"].put({
                                    "type": "send",
                                    "module_name": module_name,
                                    "data": {
                                        send_watchdogs_data["key"]: send_watchdogs_data["value"]
                                    }
                                })
                                send_watchdogs_data["value"] = not send_watchdogs_data["value"]

                            # 와치독스 확인
                            recv_watchdogs_data = self.watchdogs_data.get_watchdogs_data(module_name, "recv")
                            if recv_watchdogs_data is not None:
                                # 받는게 있다면 시간 확인 후 5초 이내 바뀐게 없다면 재연결 시도
                                now_time = datetime.datetime.now()
                                if now_time - recv_watchdogs_data["time"] >= datetime.timedelta(seconds=5):
                                    recv_watchdogs_data["time"] = now_time
                                    self.comm_data_queue["send"].put({
                                        "type": "reconnect",
                                        "module_name": module_name,
                                        "data": True
                                    })

                if len(self.send_integrate_data) != 0 or True:
                    # 보낼 데이터가 있을 경우
                    send_integrate_data = copy.deepcopy(self.send_integrate_data)
                    for queue_data in self.send_integrate_queue.values():
                        queue_data.put({
                            "type": "integrate_data",
                            "data": send_integrate_data
                        })
                    await self.user_send_integrate_data_process(send_integrate_data)
                    self.send_integrate_data.clear()

                # =================================
                # 사용자 데이터 처리
                # =================================
                await self.user_main_process(second_flag, hour_flag, day_flag)
            except:
                print(traceback.format_exc())
            await asyncio.sleep(0.1)

    def send_event(self, module_name, event_type, alarm, msg=""):
        cmd_data: dict = {
            "type": "event",
            "data": {
                "module_name": module_name,
                "error_type": event_type,
                "alarm": alarm,
                "msg": msg,
                "date": datetime.datetime.now()
            }
        }
        self.api_queue["recv"].put(cmd_data)

    # ================================
    # 추상 함수
    # ================================
    # API 요청 처리
    async def api_request_process(self, request_data: dict):
        # recv_type: str = request_data.get("type")  # 데이터 타입
        # recv_data: any = request_data.get("data")  # 데이터
        #
        # if recv_type == "example":
        #     # 생산 작업 명령이라면
        #     ThreadWithException(self.api_request_example, recv_data).start()
        #     self.logger.info(f"[api_send_data_process] 예제 ({recv_data})")
        pass

    # API 요청 예제
    def api_request_example(self, args):
        # recv_data = args[0]
        # working_id = recv_data.get("working_id")
        #
        # return_data = self.three_hand_shaking(working_id, "moxa_e1212", {}, [], [], [])
        # response_data = {
        #     "type": "response",
        #     "data": {
        #         "working_id": working_id,
        #         "flag": return_data.get("success_flag"),
        #         "msg": return_data.get("msg"),
        #         "data": return_data.get("data"),
        #     }
        # }
        # self.api_queue["recv"].put(response_data)
        pass

    # 수신 통합 데이터 처리
    async def recv_integrate_data_process(self, module_name, recv_data):
        pass

    # 유저 메인 처리
    async def user_main_process(self, second_flag, hour_flag, day_flag):
        pass

    # 사용자 통합 데이터 전송 처리
    async def user_send_integrate_data_process(self, send_integrate_data):
        pass