# -*- coding: utf-8 -*-
import multiprocessing as mp
import asyncio
import traceback
from sqlalchemy.orm import Session
from fastapi import Depends, Request
from fastapi.websockets import WebSocket
from fastapi.encoders import jsonable_encoder
from src.api_server.domain.auth.auth_core import login_hash_check
from src.database.curd import add_event, search_event
from src.database.database import get_db
from src.api_server.domain.acs_main.main_core import AgvData, AcsData, StatusMonitoringData, \
    get_status_monitoring_title, \
    SystemData, WorkListData
from src.api_server.domain.acs_main.main_parameter import menu_list, module_description, agv_module_name_description, \
    system_module_name_parameter
from src.main_server.module.cofigparser import get_configparser
from src.main_server.module.fastapi_module import APIRouterModule, get_id, get_response_check


class MainAPIRouter(APIRouterModule):
    def __init__(self, program_name, prefix="", logger=None, send_queue: mp.Queue = mp.Queue(), recv_queue: mp.Queue = mp.Queue(), stop_event = mp.Event()):
        self.send_queue: mp.Queue = send_queue
        self.recv_queue: mp.Queue = recv_queue
        self.stop_event: mp.Event = stop_event

        # AGV 데이터
        self.agv_data = AgvData()
        self.system_data = SystemData()
        self.status_monitoring_data = StatusMonitoringData()
        self.acs_data = AcsData()
        self.work_list_data = WorkListData()

        # 연결된 소켓
        self.acs_websocket = {}   # ACS 소켓
        self.status_websocket = {}  # 상태 소켓

        # 응답 확인
        self.response_check = {}
        super().__init__(program_name, prefix, logger)

    # route 설정
    def _set_routes(self):
        # 시작시 실행
        @self.router.on_event("startup")
        async def startup_event():
            # 받은 데이터 처리
            asyncio.create_task(self.recv_data_process())

        # Web에 상태 정보를 보내기 위한 웹 소켓
        @self.router.websocket("/acs_websocket")
        async def acs_websocket(websocket: WebSocket):
            await websocket.accept()

            client_ip = websocket.client.host
            self.logger.info(f"[acs_websocket] [{client_ip}] 연결 됨")

            websocket_id = get_id()
            self.acs_websocket[websocket_id] = websocket


            await websocket.send_json({"type": "agv_info", "data": jsonable_encoder(self.agv_data.get_agv_data())})
            await websocket.send_json({"type": "system_info", "data": jsonable_encoder(self.system_data.get_system_data())})
            await websocket.send_json({"type": "acs_info", "data": jsonable_encoder(self.acs_data.get_acs_data())})

            try:
                while True:
                    recv_data_dict: dict = await websocket.receive_json()
            except Exception as e:
                self.logger.info(f"[acs_websocket] [{client_ip}] 연결 해제 됨 ({e})")

            try:
                await websocket.close()
            except Exception:
                self.logger.warn(f"[{websocket_id}] [{client_ip}] {traceback.format_exc()}")
            try:
                del self.acs_websocket[websocket_id]
            except Exception:
                self.logger.warn(f"[{websocket_id}] [{client_ip}] {traceback.format_exc()}")
            self.logger.info(f"[acs_websocket] [{client_ip}] 연결 해제 완료")

        # 상태 모니터링 웹소켓
        @self.router.websocket("/status_websocket/{module_name}")
        async def status_websocket(websocket: WebSocket, module_name: str):
            await websocket.accept()

            client_ip = websocket.client.host
            self.logger.info(f"[status_websocket] [{client_ip}] 연결 됨")

            websocket_id = get_id()
            if self.status_websocket.get(module_name) is None:
                self.status_websocket[module_name] = {}
            self.status_websocket[module_name][websocket_id] = websocket

            await websocket.send_json({
                "type": "status_data",
                "title": get_status_monitoring_title(module_name),
                "data": jsonable_encoder(self.status_monitoring_data.get_status_monitoring_data(module_name))
            })

            try:
                while True:
                    recv_data_dict: dict = await websocket.receive_json()
            except Exception as e:
                self.logger.info(f"[status_websocket] [{client_ip}] 연결 해제 됨 ({e})")

            try:
                await websocket.close()
            except Exception:
                self.logger.warn(f"[{websocket_id}] [{client_ip}] {traceback.format_exc()}")
            try:
                del self.status_websocket[module_name][websocket_id]
            except Exception:
                self.logger.warn(f"[{websocket_id}] [{client_ip}] {traceback.format_exc()}")
            self.logger.info(f"[status_websocket] [{client_ip}] 연결 해제 완료")

        # 비상정지 설정
        @self.router.post("/emergency_stop")
        async def emergency_stop(request: Request, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                json_data = await request.json()

                self.send_queue.put({
                    "type": "set_emergency_stop",
                    "working_id": working_id,
                    "data": json_data
                })
                return_data = await get_response_check(self.response_check, working_id)
                return return_data
            else:
                return {"flag": False, "msg": "권한이 없습니다"}

        # 비상 모드 설정
        @self.router.post("/set_emg_mode")
        async def set_emg_mode(request: Request, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                json_data = await request.json()

                self.send_queue.put({
                    "type": "set_emg_mode",
                    "working_id": working_id,
                    "data": json_data
                })
                return_data = await get_response_check(self.response_check, working_id)
                return return_data
            else:
                return {"flag": False, "msg": "권한이 없습니다"}

        # ACS 비상정지 설정
        @self.router.post("/acs_emergency_stop")
        async def acs_emergency_stop(request: Request, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                json_data = await request.json()

                self.send_queue.put({
                    "type": "set_acs_emergency_stop",
                    "working_id": working_id,
                    "data": json_data
                })
                return_data = await get_response_check(self.response_check, working_id)
                self.acs_data.set_acs_emergency_stop(json_data.get("flag", False))
                return return_data
            else:
                return {"flag": False, "msg": "권한이 없습니다"}

        # 비활성화 설정
        @self.router.post("/set_disable")
        async def set_disable(request: Request, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                json_data = await request.json()

                self.send_queue.put({
                    "type": "set_disable",
                    "working_id": working_id,
                    "data": json_data
                })
                return_data = await get_response_check(self.response_check, working_id)
                return return_data
            else:
                return {"success": False, "msg": "권한이 없습니다"}

        # 자동 모드 설정
        @self.router.post("/set_auto_mode")
        async def set_auto_mode(request: Request, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                json_data = await request.json()

                self.send_queue.put({
                    "type": "set_auto_mode",
                    "working_id": working_id,
                    "data": json_data
                })
                return_data = await get_response_check(self.response_check, working_id)
                if return_data.get("success") is True:
                    self.agv_data.set_agv_auto_mode(json_data.get("module_name"), json_data.get("flag", False))
                return return_data
            else:
                return {"success": False, "msg": "권한이 없습니다"}

        # AGV 명령
        @self.router.post("/cmd_agv")
        async def cmd_agv(request: Request, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                json_data = await request.json()

                self.send_queue.put({
                    "type": "set_cmd_agv",
                    "working_id": working_id,
                    "data": json_data
                })
                return_data = await get_response_check(self.response_check, working_id)
                return return_data
            else:
                return {"flag": False, "msg": "권한이 없습니다"}

        # =====================================
        # 작업 관련
        # =====================================
        # 작업 리스트 가져오기
        @self.router.post("/get_work_list")
        async def get_work_list(request: Request, db: Session = Depends(get_db)):
            try:
                json_data = await request.json()
                module_name = json_data.get("module_name")
                is_agv: bool = self.agv_data.is_module_name_agv(module_name)
                is_working, work_list = self.work_list_data.get_work_list(db, module_name if is_agv is True else None)

                return {
                    "flag": True,
                    "data": {
                        "is_working": is_working,
                        "is_all_list": not is_agv,
                        "work_list": work_list
                    }
                }
            except Exception as e:
                print(traceback.format_exc())
                return {
                    "flag": False,
                    "msg": f"{e}"
                }

        # 날짜별 작업 리스트 가져오기
        @self.router.post("/get_search_work_list")
        async def get_search_work_list(request: Request, db: Session = Depends(get_db)):
            try:
                json_data = await request.json()
                module_name = json_data.get("module_name")
                search_date = json_data.get("search_date")
                is_agv: bool = self.agv_data.is_module_name_agv(module_name)
                is_working, work_list = self.work_list_data.get_work_list(db, module_name if is_agv is True else None, True, search_date)

                return {
                    "flag": True,
                    "data": {
                        "work_list": work_list
                    }
                }
            except Exception as e:
                print(traceback.format_exc())
                return {
                    "flag": False,
                    "msg": f"{e}"
                }

        # 명령 관리 (대기 명령 해제, 명령 정지, 재시작, 삭제)
        @self.router.post("/cmd/{cmd_type}")
        async def cmd_management(request: Request, cmd_type: str, login_flag: bool = Depends(login_hash_check)):
            if login_flag is True:
                working_id = get_id()
                request_item = await request.json()

                self.send_queue.put({
                    "type": cmd_type,
                    "working_id": working_id,
                    "data": request_item
                })
                return_data = await get_response_check(self.response_check, working_id)
                await asyncio.sleep(0.1)
                return return_data
            else:
                return {"flag": False, "msg": "권한이 없습니다"}

        # 이벤트 보기
        @self.router.post("/read_event")
        async def read_event(request: Request, db: Session = Depends(get_db)):
            try:
                request_item = await request.json()
                event_list_data = search_event(db, request_item["event_date"])
                if event_list_data:
                    return {"success": True, "data": event_list_data}
                else:
                    raise Exception()
            except Exception:
                return {"success": False, "msg": "데이터가 없습니다"}

    # 받은 데이터 처리
    async def recv_data_process(self):
        while not self.stop_event.is_set():
            while self.recv_queue.qsize() != 0:
                try:
                    recv_data_dict: dict = self.recv_queue.get()
                    recv_type: str = recv_data_dict.get("type")
                    recv_data: any = recv_data_dict.get("data")
                    if recv_type == "integrate_data":
                        # 통합 데이터라면
                        await self.update_integrate_data(recv_data)
                    elif recv_type == "response":
                        # 응답 데이터라면
                        print(recv_type, recv_data)
                        working_id = recv_data.get("working_id")
                        if self.response_check.get(working_id) is not None:
                            self.response_check[working_id]["result"] = recv_data
                    elif recv_type == 'event':
                        # 이벤트라면
                        await self.set_event(recv_data)
                except Exception:
                    self.logger.warn(f"[recv_data_process] 데이터 처리 도중 예외가 발생하였습니다. {traceback.format_exc()}")
            try:
                self.work_list_data.get_update_data()
            except Exception:
                self.logger.warn(f"[recv_data_process] 작업 리스트 처리 도중 예외가 발생하였습니다. {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # 이벤트 설정
    async def set_event(self, recv_data):
        db = next(get_db())
        module_name = recv_data.get("module_name", "알 수 없음")
        agv_name = agv_module_name_description.get(module_name)
        system_name = system_module_name_parameter.get(module_name)
        if agv_name is not None:
            module_name = agv_name
        elif system_name is not None:
            module_name = system_name
        recv_data["module_name"] = module_name
        add_event(db, recv_data)

        send_alarm = {
            "type": recv_data.get('error_type', 'default'),
            "text": f"{module_name} {recv_data.get('alarm', '알람')}"
        }
        error_msg = recv_data.get("msg", "")
        if error_msg != "":
            send_alarm["detail"] = {
                "title": module_name,
                "content": send_alarm["text"],
                "errMsg": error_msg
            }

        for client in list(self.acs_websocket.values()):
            try:
                await client.send_json({
                    "type": "alarm",
                    "data": send_alarm
                })
            except Exception:
                self.logger.info(f"[이벤트] 데이터 전송 실패: {traceback.format_exc()}")
        db.close()

    # 통합 데이터 업데이트
    async def update_integrate_data(self, recv_data):
        # AGV 상태 갱신
        for module_name, module_data in recv_data.items():
            # 통합 데이터 갱신
            if module_name[:3] == "agv":
                self.agv_data.update_agv_data(module_name, module_data)
            else:
                self.system_data.update_system_data(module_name, module_data)

            # 모니터링 데이터 보내기
            send_status_monitoring_data = self.status_monitoring_data.update_status_monitoring_data(module_name, module_data)
            status_websockets: dict | None = self.status_websocket.get(module_name)
            if len(send_status_monitoring_data["data"]) != 0 and status_websockets is not None:
                if send_status_monitoring_data["new_status_flag"] is True:
                    # 새로운 상태 정보가 있다면
                    type_value = "status_data"
                    data_value = self.status_monitoring_data.get_status_monitoring_data(module_name)
                else:
                    # 새로운 정보가 없다면
                    type_value = "status_data_update"
                    data_value = send_status_monitoring_data["data"]
                for client in list(status_websockets.values()):
                    try:
                        await client.send_json({
                            "type": type_value,
                            "data": jsonable_encoder(data_value)
                        })
                    except Exception:
                        self.logger.info(f"[상태 모니터링] 데이터 전송 실패: {traceback.format_exc()}")

        # AGV 업데이트 데이터 웹소켓으로 보내기
        agv_update_data: dict | None = self.agv_data.get_update_agv_data()
        if agv_update_data is not None and len(agv_update_data) != 0:
            for client in list(self.acs_websocket.values()):
                try:
                    await client.send_json({
                        "type": "agv_info_update",
                        "data": jsonable_encoder(agv_update_data)
                    })
                except Exception:
                    self.logger.info(f"[AGV 모니터링] 데이터 전송 실패: {traceback.format_exc()}")

        # 시스템 업데이트 데이터 웹소켓으로 보내기
        system_update_data: dict | None = self.system_data.get_update_system_data()
        if system_update_data is not None and len(system_update_data) != 0:
            for client in list(self.acs_websocket.values()):
                try:
                    await client.send_json({
                        "type": "system_info_update",
                        "data": jsonable_encoder(system_update_data)
                    })
                except Exception:
                    self.logger.info(f"[시스템 모니터링] 데이터 전송 실패: {traceback.format_exc()}")

        # ACS 업데이트 데이터 웹소켓으로 보내기
        acs_update_data: dict | None = self.acs_data.get_update_acs_data()
        if acs_update_data is not None and len(acs_update_data) != 0:
            for client in list(self.acs_websocket.values()):
                try:
                    await client.send_json({
                        "type": "acs_info_update",
                        "data": jsonable_encoder(self.acs_data.get_acs_data())
                    })
                except Exception:
                    self.logger.info(f"[ACS 모니터링] 데이터 전송 실패: {traceback.format_exc()}")
