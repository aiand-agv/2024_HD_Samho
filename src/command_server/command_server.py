import asyncio
import copy
import multiprocessing as mp
import traceback
import datetime
import orjson

from sqlalchemy.exc import OperationalError

from src.api_server.domain.acs_main.main_parameter import agv_module_name_description
from src.main_server.module.collection_of_functions import json_default, flatten_dict
from src.main_server.module.lifelong_planning_a_star import Graph, Node
from logging import Logger
from sqlalchemy.orm import Session
from src.database.curd import set_agv_work_error, get_cmd_error_description, set_agv_work_complete, get_agv_work_list, \
    add_agv_work, get_work_info, get_agv_home_position, get_work_composition_list, \
    get_waypoint_driving, get_waypoint_driving_edge, update_agv_work, get_waypoint_common, \
    get_all_waypoint_driving, search_overlap_work, set_agv_work_start_time, \
    database_update, get_database_update, get_interlock_signal
from src.database.database import get_db
from src.database.models import AgvWorkList, WorkCompositionList, WaypointDriving, WaypointDrivingEdge, WaypointCommon, \
    WorkInfoList
from src.main_server.module.cofigparser import get_configparser
from src.main_server.module.logger import get_logger, LoggerPrint


class CommandServer:
    def __init__(self, cmd_send_data_queue: mp.Queue, cmd_recv_data_queue: mp.Queue,
                 cmd_logger: Logger | None, stop_event: mp.Event):
        self.cmd_send_data_queue: mp.Queue = cmd_send_data_queue
        self.cmd_recv_data_queue: mp.Queue = cmd_recv_data_queue
        if cmd_logger is None:
            self.logger = LoggerPrint("command_server")
        else:
            self.logger = cmd_logger
        self.stop_event: mp.Event = stop_event

        self._init_variable()

    # 변수 설정
    def _init_variable(self):
        self.error_description_list: dict = {}
        self.bat_acceptable: float = 0.0
        self.work_info_list: dict = {}
        self.work_composition_list: dict = {}     # DB work_composition_list
        self.waypoint_graph = Graph()
        self.db: Session = next(get_db())
        # ===============================
        # AGV 데이터 설정
        # ===============================
        self.agv_data: dict = {}
        self.agv_status: dict = {}
        self.agv_cmd_info: dict = {}
        self.path_data: dict = {}
        self.collision_data: dict = {}
        self.agv_home: dict = {}
        self.pre_second: int = -1
        self.now_time = datetime.datetime.now()
        for agv_module_name in agv_module_name_description.keys():
            self.agv_status[agv_module_name] = {
                'connect': False,  # 연결 여부
                'disable': False,  # 비활성화 여부
                'x_axis': float('inf'),  # X 좌표
                'y_axis': float('inf'),  # Y 좌표
                'angle': 0.0,  # 각도
                'bat_soc': 0.0,  # 배터리 퍼센트
                'now_layer': 0,  # 현재 레이어
                'auto_mode': True,  # 자동 모드
                'manual_mode': False,  # 메뉴얼 모드 여부
                'bat_ignore': False,  # 배터리 무시 여부
                'charge_flag': False,  # 충전 여부
                'cmd_emg_stop': False,  # agv 명령 비상 정지 여부
            }
            self.agv_data[agv_module_name] = {
                'acs_cmd_flag': False,  # ACS 명령 수행 여부
                'agv_cmd_flag': False,  # AGV 명령 수행 여부
                'wait_flag': False,  # 대기 여부
                'interlock_check_flag': False,  # 인터락 확인 여부
                'reach_flag': False,  # 도달 여부
                'work_restart': False,  # 작업 재시작 명령 여부
                'work_start_time': self.now_time,
                'work_composition_info': [],  # 작업 구성 정보 (에: [1(언로딩 이동), 2(언로딩 작업), 3(로딩 이동), 4(로딩 작업), 5(복귀)])
                'work_composition_list': [],  # 작업 구성 리스트 (목적지 리스트)
                'cmd_path_list': [],            # AGV 경로 구성 리스트
                'cmd_agv_collision_list': [],   # AGV 충돌 확인 웨이포인트 리스트
                'cmd_composition_list': [],  # 명령 구성 리스트 (인터록, 명령)
                'agv_work_data': None,
                'work_process': 0,  # 현재 수행 작업 번호
                'cmd_process': 0,  # 현재 수행 명령 번호
                'init_flag': False,  # 초기화 여부
                'pre_working_sgn_flag': False,  # 인터락 확인 이전 신호 보내기 여부
                'work_flag': False,  # 명령 작업 수행 여부 (AGV 명령(웨이포인트) 수신 수행 여부)
                'wait_reason': [],  # 명령 대기 이유
                'cmd_emergency': False,  # 명령 비상 정지 여부
                'interlock_ignore': False,  # 현재 명령 수행 중 인터록 무시
                'cmd_error_flag': False,  # 현재 에러 값
                'pre_error_flag': False,  # 이전 에러 값
                'error_code': 0,  # 에러 코드
                'work_restart_flag': False,  # 작업 재시작 여부
                'work_restart_count': False,  # 작업 재시작 카운트
                'auto_flag': False,  # 자동 여부
                'wait_position_flag': False,  # 대기 장소 여부
                'bat_log_flag': False,  # 배터리 부족 로그 여부
                'charge_return_flag': False,  # 충전 복귀 여부
                'fast_start_flag': False,  # 빠른 시작 여부
                'temp_nodes': {},  # 임시 노드
                'work_name': "",  # 작업 이름
                'work_position': ""  # 작업 위치
            }
            self.agv_cmd_info[agv_module_name] = {
                'cmd_flag': False,  # 명령 수행 여부
                'cmd_start': False,  # 명령 수행 시작 여부
                'cmd_error': False,  # 명령 에러 여부
                'cmd_error_type': 0,  # 명령 에러 타입
                'cmd_reach_flag': False,  # 명령 도달 여부
                'cmd_work_no': 0,  # 작업 번호 (도착지 번호)
                'cmd_number': 0,  # 명령 번호 (웨이포인트[노드] 번호)
                'cmd_work_name': "",  # 명령 작업 이름
                'cmd_work_position': "",  # 명령 작업 위치
                'cmd_wait_flag': False,  # 명령 작업 대기 여부
                'cmd_wait_reason': [],  # 명령 대기 이유
                'precise_mode': False,  # 정밀 모드 여부
            }

            # 경로 데이터
            self.path_data[agv_module_name] = []

            # 충돌 방지 데이터
            self.collision_data[agv_module_name] = {}

        # =======================
        # 통합 데이터 설정
        # =======================
        self.integrate_data: dict = {}

    # 충돌 방지 프로세스
    async def collision_process(self):
        while not self.stop_event.is_set():
            try:
                self.set_exist_collision()
            except Exception:
                self.logger.warning(f"[충돌 방지 프로세스] 예외가 발생하였습니다. 예외 메시지: {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # AGV 충돌 확인 구역 가져오기
    def get_agv_collision_check(self, module_name, work_process, cmd_process, next_check_flag):
        # 현재 위치의 인접 노드/간선
        cmd_path_list: list = self.agv_data[module_name]['cmd_path_list']
        cmd_agv_collision_list: list = self.agv_data[module_name]['cmd_agv_collision_list']

        # =====================================
        # AGV 장애물 확인 지점 찾기
        # =====================================
        check_work_process_idx = len(cmd_path_list) - 1
        check_cmd_process_idx = len(cmd_path_list[check_work_process_idx]) - 1
        for agv_collision in cmd_agv_collision_list:
            # AGV 장애물 확인 지점 찾기
            if work_process < agv_collision[0]:
                # 해당 확인 지점으로 설정
                check_work_process_idx = agv_collision[0]
                check_cmd_process_idx = agv_collision[1]
                break
            elif work_process == agv_collision[0] and cmd_process <= agv_collision[1]:
                # 해당 확인 지점으로 설정
                if cmd_process == agv_collision[1] and next_check_flag is True:
                    # 인터록이 확인되었다면 다음 확인 지점으로 설정
                    continue
                check_work_process_idx = agv_collision[0]
                check_cmd_process_idx = agv_collision[1]
                break
        return check_work_process_idx, check_cmd_process_idx

    # 충돌 구역 존재 여부 파악
    def set_exist_collision(self):
        for module_name in self.agv_status.keys():
            x_axis: float = self.agv_status[module_name]['x_axis']
            y_axis: float = self.agv_status[module_name]['y_axis']
            disable_flag = self.agv_status[module_name].get("disable", False)

            if disable_flag is False:
                # 비활성화가 아니라면 충돌 구역 존재 설정
                work_process = self.agv_data[module_name]['work_process']
                cmd_process = self.agv_data[module_name]['cmd_process']

                # 현재 위치의 인접 노드/간선
                collision_nodes: set = self.waypoint_graph.find_closest_graph(x_axis, y_axis)
                cmd_path_list: list = self.agv_data[module_name]['cmd_path_list']

                if work_process != 0:
                    # =====================================
                    # AGV 장애물 확인 지점 찾기
                    # =====================================
                    interlock_check_flag: bool = self.agv_data[module_name]['interlock_check_flag']
                    check_work_process_idx, check_cmd_process_idx = self.get_agv_collision_check(module_name,
                                                                                                 work_process,
                                                                                                 cmd_process,
                                                                                                 interlock_check_flag)

                    # =====================================
                    # AGV 장애물 노드 설정
                    # =====================================
                    pre_node_idx: int = cmd_path_list[work_process][cmd_process]
                    for work_process_idx in range(work_process, check_work_process_idx + 1):
                        # 현재 work_process부터 확인 idx까지 돌리기
                        if work_process == work_process_idx:
                            start_idx = cmd_process
                        else:
                            start_idx = 0

                        if work_process_idx == check_work_process_idx:
                            # 현재 work_process가 확인 idx까지 왔다면
                            check_idx = check_cmd_process_idx
                        else:
                            check_idx = len(cmd_path_list[work_process_idx]) - 1

                        for cmd_process_idx in range(start_idx, check_idx + 1):
                            target_node_idx: int = cmd_path_list[work_process_idx][cmd_process_idx]
                            if work_process == check_work_process_idx and cmd_process_idx == start_idx:
                                # 이전 idx 지나쳤는지 확인
                                try:
                                    now_position = (x_axis, y_axis)
                                    pre_node = (self.waypoint_graph.nodes[pre_node_idx].x, self.waypoint_graph.nodes[pre_node_idx].y)
                                    if self.waypoint_graph.is_within_expanded_bounds(now_position, pre_node, None, {}) is True:
                                        # 해당 노드를 지나치지 않았다면
                                        collision_nodes.add(pre_node_idx)
                                except Exception:
                                    # 에러 발생했다면 해당 노드 포함
                                    collision_nodes.add(pre_node_idx)
                            collision_nodes.add(target_node_idx)

                            if pre_node_idx != target_node_idx:
                                # 이전 노드와 목표 노드와 동일하지 않을 경우 간선으로 포함
                                collision_nodes.add((pre_node_idx, target_node_idx))
                                collision_nodes.add((target_node_idx, pre_node_idx))
                            pre_node_idx = cmd_path_list[work_process_idx][cmd_process_idx]

                # =====================================
                # 장애물 count 갱신
                # =====================================
                for collision_node in collision_nodes:
                    self.collision_data[module_name][collision_node] = 0

            # =====================================
            # 장애물 삭제 (count가 50이상 되면 삭제)
            # =====================================
            if self.agv_data[module_name]['cmd_error_flag'] is False:
                # 에러가 발생 하지 않을 경우 초기화 진행
                remove_list: list = []

                for collision_key, collision_count in self.collision_data[module_name].items():
                    # 충돌 구역 초기화
                    if collision_count >= 50:
                        # 5초 동안 유지 되지않았다면 False
                        remove_list.append(collision_key)
                    else:
                        # 5초 이하일 경우
                        self.collision_data[module_name][collision_key] += 1
                        emg_stop_flag = self.agv_status[module_name].get('emg_stop', True)
                        if emg_stop_flag is True and disable_flag is False:
                            # 비상 정지일 경우 0으로 초기화
                            self.collision_data[module_name][collision_key] = 0

                # 장애물 노드(간선) 삭제
                for collision_key in remove_list:
                    del self.collision_data[module_name][collision_key]

    # 장애물 노드인지 파악
    def is_collision_node(self, module_name, collision_key):
        return_flag: bool = False
        for collision_module_name, collision_data in self.collision_data.items():
            if collision_module_name == module_name:
                continue
            if collision_data.get(collision_key) is not None:
                # 해당 노드 idx 또는 간선이 존재한다면 장애물 노드로 판단
                return_flag = True
                break
        return return_flag

    # =================================================
    #                     갱신 함수
    # =================================================
    async def update_process(self):
        pre_second = -1
        while not self.stop_event.is_set():
            try:
                self.now_time = datetime.datetime.now()
                now_second: int = self.now_time.second
                if pre_second != now_second:
                    force_update_flag = get_database_update(self.db, "command_server")
                    if now_second % 30 == 0 or pre_second == -1 or force_update_flag is True:
                        # 30초 마다 갱신
                        database_update(self.db, "command_server")
                        if now_second == 0 or pre_second == -1:
                            # 1분마다 갱신
                            self.update_waypoint_graph()
                            # self.waypoint_graph.visualize_graph()
                        self.update_home_position()  # 홈 위치 갱신
                        self.update_error_description()  # 오류 설명 갱신
                        self.update_work_info_list()  # 작업 정보 리스트 갱신
                        self.update_work_composition_list()  # 작업 구성 리스트 갱신
                        self.update_interlock_signal()   # 인터록 & 작업 신호 갱신

                        # 배터리 허용치 갱신
                        self.bat_acceptable = float(get_configparser("option", "bat_acceptable", "30.0"))

                    # DB 세션 갱신
                    pre_second = now_second
            except OperationalError:
                self.logger.warning(f"[갱신 프로세스] DB 연결 문제가 발생하였습니다. DB 재 연결합니다. 예외 메시지: {traceback.format_exc()}")
                try:
                    self.db.close()
                except Exception:
                    self.logger.warning(f"[갱신 프로세스] DB 연결 도중 예외가 발생하였습니다. 예외 메시지: {traceback.format_exc()}")
                finally:
                    self.db = next(get_db())
                    pre_second = -1
            except Exception:
                self.logger.warning(f"[갱신 프로세스] 예외가 발생하였습니다. 예외 메시지: {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # 홈 위치 갱신
    def update_home_position(self):
        agv_home_data: dict = {}
        for module_name in self.agv_status.keys():
            agv_home_data[module_name] = {}
            agv_home_position_list = get_agv_home_position(self.db, module_name)

            for agv_home_position_data in agv_home_position_list:
                agv_home_waypoint_no = agv_home_position_data.waypoint_no
                agv_home_node: None | Node = self.waypoint_graph.nodes.get(agv_home_waypoint_no)
                if agv_home_node is not None:
                    agv_home_data[module_name][agv_home_node.description] = {
                        'x_axis': agv_home_node.x,
                        'y_axis': agv_home_node.y,
                        'charge_flag': agv_home_position_data.charge_flag,
                        'description': agv_home_position_data.description,
                        'waypoint_no': agv_home_position_data.waypoint_no,
                    }
        self.agv_home = agv_home_data

    # 오류 설명 갱신
    def update_error_description(self):
        error_list_data: dict = {}
        error_description_list: list = get_cmd_error_description(self.db)
        for error_description in error_description_list:
            error_list_data[error_description.idx] = error_description.description
        self.error_description_list = error_list_data

    # 작업 정보 리스트 갱신
    def update_work_info_list(self):
        work_info_data: dict[int, WorkInfoList] = {}
        work_info_list: list[WorkInfoList] = get_work_info(self.db)
        for work_info in work_info_list:
            _work_info = copy.deepcopy(work_info)
            work_info_data[_work_info.idx] = _work_info
            work_info_data[_work_info.idx].work_composition = orjson.loads(_work_info.work_composition)
            work_info_data[_work_info.idx].start_idx = orjson.loads(_work_info.start_idx)
            work_info_data[_work_info.idx].unloading_idx = orjson.loads(_work_info.unloading_idx)
            work_info_data[_work_info.idx].loading_idx = orjson.loads(_work_info.loading_idx)
            work_info_data[_work_info.idx].arrival_idx = orjson.loads(_work_info.arrival_idx)
        self.work_info_list = work_info_data

    # 작업 구성 리스트 갱신
    def update_work_composition_list(self):
        work_composition_list: list[WorkCompositionList] = get_work_composition_list(self.db)
        work_composition_dict: dict[int, WorkCompositionList] = {}
        for work_composition in work_composition_list:
            _work_composition = copy.deepcopy(work_composition)
            work_composition_dict[_work_composition.idx] = _work_composition
            if _work_composition.driving_flag is False:
                work_composition_dict[_work_composition.idx].command = orjson.loads(_work_composition.command)
        self.work_composition_list = work_composition_dict

    # 인터록 & 작업 신호 갱신
    def update_interlock_signal(self):
        interlock_signal_list: list = get_interlock_signal(self.db)

        interlock_signal_data_dict: dict = {}
        for data in interlock_signal_list:
            interlock_signal_data_dict[data.main_name][data.sub_name] = {
                'module_name': data.module_name,   # 모듈 이름
                'status_name': data.status_name,   # 상태 이름
                'description': data.description,    # 설명
                'value': None,                      # 값
                'time': None                        # 시간 (타이머 사용 위함)
            }
        self.interlock_signal_data = interlock_signal_data_dict

    # 웨이포인트 그래프 갱신
    def update_waypoint_graph(self):
        waypoint_data_list: list[WaypointDriving] = get_all_waypoint_driving(self.db)

        # 노드 구성
        for waypoint_data in waypoint_data_list:
            command_data: dict = orjson.loads(waypoint_data.command)
            x_axis: float | None = command_data.get("X")
            y_axis: float | None = command_data.get("Y")
            angle: float = command_data.get("A", 0.01)
            if x_axis is None or angle is None:
                # 좌표 값이 없을 경우 넘기기
                continue
            self.waypoint_graph.add_node(waypoint_data.idx, x_axis, y_axis, angle, command_data, waypoint_data.name, waypoint_data.description)

        # 간선 구성
        waypoint_driving_edge_list: list[WaypointDrivingEdge] = get_waypoint_driving_edge(self.db)
        for waypoint_driving_edge in waypoint_driving_edge_list:
            arrow: str = waypoint_driving_edge.arrow
            try:
                command_data: dict = orjson.loads(waypoint_driving_edge.command)
            except Exception:
                command_data: dict = {}
            try:
                range_data: dict = orjson.loads(waypoint_driving_edge.return_range)
            except Exception:
                range_data: dict = {}

            cost = float('inf') if waypoint_driving_edge.work_zone is True else 1   # 작업 공간이라면 경로 구성 최대한 막기 위한 비용 추가

            # → & ↔ 방향 설정
            if arrow != "←":
                start_waypoint = waypoint_driving_edge.waypoint_1_no
                destination_waypoint = waypoint_driving_edge.waypoint_2_no
                self.waypoint_graph.add_edge(start_waypoint, destination_waypoint, cost, command_data.get("→"),
                                             range_data, waypoint_driving_edge.work_zone)

            # ← & ↔ 방향 설정
            if arrow != "→":
                start_waypoint = waypoint_driving_edge.waypoint_2_no
                destination_waypoint = waypoint_driving_edge.waypoint_1_no
                self.waypoint_graph.add_edge(start_waypoint, destination_waypoint, cost, command_data.get("←"),
                                             range_data, waypoint_driving_edge.work_zone)

    # =================================================
    #                   명령 관련 함수
    # =================================================
    # 명령 프로세스
    async def run_cmd_process(self):
        while not self.stop_event.is_set():
            try:
                self.main_cmd_process()
                if self.pre_second != self.now_time.second:
                    self.pre_second = self.now_time.second
            except Exception:
                self.logger.warning(f"[명령 프로세스] 예외가 발생하였습니다. 예외 메시지: {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # 메인 명령 처리 함수
    def main_cmd_process(self):
        for module_name in self.agv_status.keys():
            # AGV 개수 반복
            if self.agv_status[module_name]['connect'] is False:
                # 서버 연결이 안되어있을 경우
                continue
            if self.agv_status[module_name]['manual_mode'] is True:
                # 메뉴얼 모드 일 경우
                if self.agv_data[module_name]['acs_cmd_flag'] is True:
                    # ACS 명령 수행 중일 경우 에러 발생
                    work_list_data: AgvWorkList = self.agv_data[module_name]['agv_work_data']
                    agv_work_list_idx: int = work_list_data.idx
                    self.set_cmd_error(module_name, agv_work_list_idx, 7)  # 수동 조작으로 인한 일시 정지
                continue
            else:
                # 메뉴얼 모드가 아닌 경우
                if self.agv_data[module_name]['acs_cmd_flag'] is True:
                    # ACS 가 명령 수행 중일 경우
                    if self.now_time > self.agv_data[module_name]['work_start_time'] + datetime.timedelta(seconds=5) \
                            and (self.agv_data[module_name]['agv_cmd_flag'] is False or
                                 self.agv_data[module_name]['work_flag'] is False) \
                            and self.agv_data[module_name]['wait_flag'] is False \
                            and self.agv_data[module_name]['reach_flag'] is False:
                        # 현재 시간이 명령 시작 시간 + 5초보다 클 경우 에러 발생 (AGV 명령 수행 중이거나 대기 일 경우 명령 진행)
                        work_list_data: AgvWorkList = self.agv_data[module_name]['agv_work_data']
                        agv_work_list_idx: int = work_list_data.idx
                        if self.now_time > self.agv_data[module_name]['work_start_time'] + datetime.timedelta(seconds=10):
                            # 현재 시간이 명령 시간 보다 10초 이상 지난 경우 (AGV가 꺼졌다 켜진걸로 판단)
                            self.set_cmd_error(module_name, agv_work_list_idx, 12)  # AGV 명령 수신 불가로 인한 일시 정지
                        elif self.agv_data[module_name]['work_restart_count'] >= 3:
                            # 3회 이상 전송했는데도 명령을 받지 못한 경우 에러 발생
                            self.set_cmd_error(module_name, agv_work_list_idx, 12)  # AGV 명령 수신 불가로 인한 일시 정지
                        else:
                            # 명령 재전송
                            work_idx: int = work_list_data.work_idx
                            work_process: int = self.agv_data[module_name]['work_process']
                            cmd_process: int = self.agv_data[module_name]['cmd_process']

                            self.agv_data[module_name]['work_restart_flag'] = True
                            self.agv_data[module_name]['work_restart_count'] += 1

                            log_msg: str = f"AGV가 명령을 수신하지 못해 명령을 재 전송합니다. " \
                                           f"항목 번호: {agv_work_list_idx}, " \
                                           f"작업 번호: {work_idx}, " \
                                           f"현재 진행 작업 번호: {work_process}, " \
                                           f"현재 진행 명령 번호: {cmd_process}, " \
                                           f"재전송 횟수: {self.agv_data[module_name]['work_restart_count']}"
                            self.logger.info(f"[명령 재 전송] [{module_name}] {log_msg}")
                            self.send_event(module_name, "warring", f"{agv_work_list_idx} 항목 작업 재 전송 ({self.agv_data[module_name]['work_restart_count']}/3)")

                            self.agv_data[module_name]['init_flag'] = False
                            self.agv_data[module_name]['pre_working_sgn_flag'] = False
                            self.agv_data[module_name]['interlock_check_flag'] = False
                            self.agv_data[module_name]['work_start_time'] = datetime.datetime.now()
                    else:
                        self.cmd_reach_process(module_name)
                else:
                    # ACS 명령 수행 중이지 않을 경우
                    if self.agv_data[module_name]['agv_cmd_flag'] is True:
                        # AGV 가 명령 수행 중일 경우 명령 정지
                        self.set_cmd_pause(module_name)
                    else:
                        # AGV 가 명령 수행 중이지 않을 경우 작업 시작
                        self.work_start(module_name)

    # 작업 시작
    # ======================================
    # 우전지앤에프 작업 시 agv_home_position 이용 작업 가능 구간 추가 필요
    # ======================================
    def work_start(self, module_name: str):
        # 작업 목록 가져오기
        work_list: list = get_agv_work_list(self.db, module_name)

        # 집 여부
        agv_x_axis: float = self.agv_status[module_name]['x_axis']
        agv_y_axis: float = self.agv_status[module_name]['y_axis']

        home_flag_data: dict = {
            "position": "",
            "home_flag": False,
            "description": "",
            "waypoint": 0,
            "charge_flag": False
        }
        for position_name, position in self.agv_home.get(module_name, {}).items():
            x_axis: float = position['x_axis']
            y_axis: float = position['y_axis']
            home_flag: bool = True if (x_axis - 0.25 < agv_x_axis < x_axis + 0.25 and
                                       y_axis - 0.25 < agv_y_axis < y_axis + 0.25) else False
            if home_flag is True:
                home_flag_data.update({
                    "position": position_name,
                    "home_flag": home_flag,
                    "description": position["description"],
                    "waypoint": position["waypoint_no"],
                    "charge_flag": position["charge_flag"]
                })
                break

        if len(work_list) > 0:
            # 작업이 1개 이상 있을 경우
            work_index: int = 0
            for i in range(len(work_list)):
                if work_list[i].error_flag is True:
                    # 진행 사항과 에러가 있을 경우 우선 순위 설정
                    work_index = i
                    break
            now_work_data: AgvWorkList = work_list[work_index]   # 현재 작업 데이터
            idx = now_work_data.idx  # 작업 seq 번호
            work_idx = now_work_data.work_idx  # 작업 번호
            work_process = now_work_data.work_process  # 작업 진행 번호
            cmd_process = now_work_data.cmd_process  # 명령 진행 번호
            error_flag = now_work_data.error_flag  # 에러 여부
            auto_flag = now_work_data.auto_flag
            self.agv_data[module_name]['auto_flag'] = auto_flag  # 자동 여부

            work_info: WorkInfoList | None = self.work_info_list.get(work_idx)
            if work_info is not None:
                if error_flag == 0:
                    # 첫번째 작업이 에러가 발생하지 않은 경우
                    if auto_flag is True and self.agv_status[module_name]['auto_mode'] is False:
                        # 자동 명령인데 자동 모드가 아닌 경우 에러 발생
                        err_msg: str = f"자동모드가 아니라 자동 명령은 수행 불가합니다. 에러코드: 4 (자동모드 X) " \
                                       f"항목 번호: {idx}"
                        self.logger.info(f"[명령 시작] [{module_name}] {err_msg}")
                        self.set_cmd_error(module_name, idx, 11)  # 자동 모드가 아님
                    else:
                        if work_process == 0:
                            # 작업 수행 번호가 0인 경우
                            arrival_position = None
                            try:
                                work_composition_list: list = orjson.loads(now_work_data.work_composition_list)
                                arrival_position = work_composition_list[-1]
                            except Exception:
                                pass

                            if arrival_position is not None:
                                if home_flag_data["home_flag"] is True:
                                    # AGV 가 시작 위치에 있을 경우
                                    if work_info.home_return_flag is True and arrival_position == home_flag_data["position"]:
                                        # 시작 위치 복귀라면
                                        err_msg: str = f"현재 시작 위치({home_flag_data['description']})에 있는데 다음 작업이 해당 위치로 복귀하는 작업 입니다. " \
                                                       f"해당 작업을 생략 합니다."
                                        self.logger.info(f"[명령 시작] [{module_name}] {err_msg}")
                                        set_agv_work_complete(self.db, idx, complete_flag=1)
                                    elif self.agv_status[module_name]['bat_soc'] >= self.bat_acceptable or \
                                            self.agv_status[module_name]['bat_ignore'] is True:
                                        # 배터리 전압이 허용치보다 높을 경우 명령 시작
                                        self.agv_data[module_name]['bat_log_flag'] = False
                                        self.cmd_start(module_name, now_work_data, start_waypoint=home_flag_data["waypoint"])
                                    elif self.agv_data[module_name]['bat_log_flag'] is False:
                                        # 배터리 전압이 허용치보다 낮을 경우 로그 표시
                                        self.logger.info(f"[명령 시작] [{module_name}] 배터리가 부족합니다. 충전 될 때까지 대기합니다.")
                                        self.send_event(module_name, "warring",f"{idx} 항목 작업 대기 (AGV 배터리 부족)")
                                        self.agv_data[module_name]['bat_log_flag'] = True
                                    else:
                                        # 배터리 전압이 허용치보다 낮을 경우 허용치보다 높을때까지 계속 충전
                                        pass
                                # elif any(work_start_list) is True:
                                #     # 해당 위치 및 해당 작업이 맞을 경우 시작
                                #     self.cmdStart(agv_server, seq, work_no, id_list, 0)
                                else:
                                    # AGV 가 시작 위치에 있지 않은 경우
                                    set_agv_work_start_time(self.db, idx)  # 시작 시간 설정
                                    if work_info.all_position_flag is True:
                                        # 위치 상관없는 명령이라면
                                        self.cmd_start(module_name, now_work_data)
                                    else:
                                        # 충전소로 가는것이 아니라면
                                        err_msg: str = f"현재 AGV가 시작 할 수 없는 위치로, 작업을 수행할 수 없습니다. " \
                                                       f"에러코드: 10 (시작 위치 X), " \
                                                       f"항목 번호: {idx}"
                                        self.logger.info(f"[명령 시작] [{module_name}] {err_msg}")
                                        self.set_cmd_error(module_name, idx, 10)  # 시작 위치가 아님
                            else:
                                err_msg: str = f"작업 구성 리스트를 가져올 수 없습니다. 에러코드: 15 (작업 지정 실패) " \
                                               f"항목 번호: {idx}"
                                self.logger.info(f"[명령 시작] [{module_name}] {err_msg}")
                                self.set_cmd_error(module_name, idx, 15)  # 작업 지정 실패
                        else:
                            # 에러가 발생하지않았는데 명령이 0이 아닌 경우 에러 발생
                            self.set_cmd_error(module_name, idx, 13)  # AGV & ACS 동기화 실패로 인한 일시 정지
                else:
                    # 첫번째 작업이 에러가 발생한 경우
                    if self.agv_data[module_name]['cmd_error_flag'] is False:
                        # 이전에 에러가 난게 아니라면 작업 명령 데이터 갱신
                        self.agv_data[module_name]['work_process'] = work_process
                        self.agv_data[module_name]['cmd_process'] = cmd_process
                        self.agv_data[module_name]['cmd_path_list'] = orjson.loads(now_work_data.cmd_path_list)
                        self.agv_data[module_name]['cmd_agv_collision_list'] = orjson.loads(now_work_data.cmd_agv_collision_list)
                        self.agv_data[module_name]['agv_work_data'] = now_work_data
                        self.agv_data[module_name]['cmd_error_flag'] = True

                        self.set_cmd_error(module_name, idx, now_work_data.error_code)
                    if self.agv_data[module_name]['work_restart'] is True:
                        # 작업 재시작 명령이 참일 경우 작업 재시작
                        log_msg: str = f"해당 작업을 재 시작합니다." \
                                       f"항목 번호: {idx}"
                        self.logger.info(f"[명령 시작] [{module_name}] {log_msg}")
                        self.cmd_start(module_name, now_work_data, restart_flag=True)
                        self.send_event(module_name, "success", f"{idx} 항목 작업 재 시작")
            else:
                if self.agv_data[module_name]['cmd_error_flag'] is False:
                    err_msg: str = f"작업 정보가 없어 웨이포인트 지정 실패하였습니다." \
                                   f"에러코드: 3 (웨이포인트 지정 실패), " \
                                   f"항목 번호: {idx}" \
                                   f"작업 번호: {work_idx}"
                    self.logger.info(f"[명령 시작] [{module_name}] {err_msg}")
                    self.set_cmd_error(module_name, idx, 15)  # 웨이포인트 지정 실패
        else:
            self.agv_data[module_name]['cmd_error_flag'] = False

        if self.pre_second != self.now_time.second:
            # 1초 지나고 홈인데 충전이 안되고 있을 경우
            if self.agv_data[module_name]['acs_cmd_flag'] is False:
                if self.agv_status[module_name]['charge_flag'] is False and home_flag_data["charge_flag"] is True:
                    # 홈 위치이고, 충전 여부가 False 이고 명령 수행 중이지 않을 경우 충전 요청
                    self.send_set_charge(module_name, True)  # 충전 설정 보내기
                elif self.agv_status[module_name]['charge_flag'] is True and home_flag_data["charge_flag"] is False:
                    # 홈위치가 아닌데 충전 상태인 경우 충전 해제 신호 보내기
                    self.send_set_charge(module_name, False)  # 충전 해제 설정 보내기

                if self.agv_cmd_info[module_name]["cmd_work_position"] != home_flag_data["description"]:
                    self.agv_data[module_name]["work_name"] = ""
                    self.agv_data[module_name]["work_position"] = home_flag_data["position"]
                    self.send_agv_cmd(module_name, False)

    # 명령 시작
    def cmd_start(self, module_name: str, agv_work_data: AgvWorkList, start_waypoint: int = 0,
                  fast_start_flag: bool = False, restart_flag: bool = False):
        # ==========================
        # 작업 확인
        # ==========================
        work_info: WorkInfoList | None = self.work_info_list.get(agv_work_data.work_idx)
        if work_info is None:
            if fast_start_flag is False:
                # 빠른 시작이 아닌 경우
                log_msg: str = f"작업을 시작 할 수 없습니다. (작업 정보 리스트가 없습니다.) " \
                               f"에러코드: 15 (작업 지정 실패), " \
                               f"항목 번호: {agv_work_data.idx}, " \
                               f"시작할 작업 번호: {agv_work_data.work_idx}, "
                self.logger.info(f"[명령 시작] [{module_name}] {log_msg}")
                self.set_cmd_error(module_name, agv_work_data.idx, 15)  # 작업 지정 실패
            return False

        # ===========================
        # 작업 구성 확인 및 빠른 가능 구역 찾기
        # ===========================
        work_process: int = agv_work_data.work_process
        cmd_process: int = agv_work_data.cmd_process
        fast_start_process: int = -1
        work_composition_info: list = work_info.work_composition  # [0(준비), 1(언로딩 이동), 2(언로딩 작업), 3(로딩 이동), 4(로딩 작업), 5(복귀)]
        work_composition_list: list = orjson.loads(agv_work_data.work_composition_list)
        cmd_path_list: list = orjson.loads(agv_work_data.cmd_path_list)
        cmd_agv_collision_list: list = orjson.loads(agv_work_data.cmd_agv_collision_list)

        for now_work_composition_index in range(len(work_composition_info)):
            fast_start_work_process: int = now_work_composition_index
            work_composition_idx: int = work_composition_info[now_work_composition_index]
            work_composition: WorkCompositionList | None = self.work_composition_list.get(work_composition_idx)
            if work_composition is not None:
                if work_composition.fast_start_zone is True and fast_start_flag is True:
                    # 빠른 가능 구역이라면
                    if fast_start_process == -1:
                        fast_start_process = fast_start_work_process
                        work_process = fast_start_work_process + 1
            else:
                log_msg: str = f"작업을 시작 할 수 없습니다. (작업 구성 데이터가 없습니다.), " \
                               f"에러코드: 15 (작업 지정 실패), " \
                               f"항목 번호: {agv_work_data.idx}, " \
                               f"시작할 작업 번호: {agv_work_data.work_idx}, "
                self.logger.info(f"[명령 시작] [{module_name}] {log_msg}")
                self.set_cmd_error(module_name, agv_work_data.idx, 15)  # 작업 지정 실패
                return False

        if fast_start_flag is True:
            if fast_start_process == -1:
                # 빠른 시작이 참인데 빠른 시작 부근이 없는 경우 넘기기
                return False
            else:
                destination_position: str = work_composition_list[fast_start_process]  # 목적지
                destination_waypoint: int | None = self.waypoint_graph.get_node_idx(destination_position)
                if destination_waypoint is None:
                    # 목적지 웨이포인트가 없는 경우 넘기기
                    return False
                if self.set_start_waypoint(module_name, agv_work_data, work_composition_list, start_waypoint, destination_waypoint, work_info.start_idx) is False:
                    # 시작 웨이포인트를 지정못할 경우 넘기기
                    return False

        self.agv_work_data_clear(module_name)
        if restart_flag is True:
            # 재시작 여부가 True인 경우
            if work_process == 0:
                cmd_process = 0
            else:
                cmd_process -= 1
                cmd_process = max(0, cmd_process)

        if work_process == 0 and cmd_process == 0 and fast_start_flag is False:
            # 빠른시작이 아니고 둘다 0일 경우 위치 지정
            try:
                now_x_axis: float = self.agv_status[module_name]['x_axis']
                now_y_axis: float = self.agv_status[module_name]['y_axis']
                now_angle: float = self.agv_status[module_name]['angle']

                destination_process_idx: int = work_info.start_idx[-1] + 1
                target_position: int = work_composition_list[destination_process_idx]
                target_waypoint: int | None = self.waypoint_graph.get_node_idx(target_position)
                if target_waypoint is None:
                    raise Exception("목표 웨이포인트 없음")
                else:
                    closest_node, intersection_point, closest_edge = self.waypoint_graph.find_destination_closest_edge(now_x_axis, now_y_axis, now_angle, target_waypoint)
                    if closest_node is None or intersection_point is None or closest_edge is None:
                        raise Exception("근접 웨이포인트 없음")

                    if work_info.all_position_flag is True:
                        # 임시 노드 구성
                        command_data_1 = {
                            "cmd_type": 1,
                            "X": now_x_axis,
                            "Y": now_y_axis,
                            "A": now_angle,
                        }
                        temp_node_name = f"{module_name}_temp"
                        self.waypoint_graph.add_node(f"{temp_node_name}_1", now_x_axis, now_y_axis, now_angle,
                                                     command_data_1, f"{temp_node_name}_1", "임시 1")

                        command_data_2 = {
                            "cmd_type": 1,
                            "X": intersection_point[0],
                            "Y": intersection_point[1],
                            "A": now_angle,
                        }
                        self.waypoint_graph.add_node(f"{temp_node_name}_2", intersection_point[0], intersection_point[1],
                                                     now_angle, command_data_2, f"{temp_node_name}_2", "임시 2")

                        self.waypoint_graph.add_edge(f"{temp_node_name}_1", f"{temp_node_name}_2")
                        self.waypoint_graph.add_edge(f"{temp_node_name}_2", closest_node)

                        self.agv_data[module_name]["temp_nodes"] = {
                            "node": [f"{temp_node_name}_1", f"{temp_node_name}_2"],
                            "edge": [(f"{temp_node_name}_1", f"{temp_node_name}_2"), (f"{temp_node_name}_2", closest_node)],
                        }

                        start_waypoint_name = f"{temp_node_name}_1"
                        start_waypoint = f"{temp_node_name}_1"
                    else:
                        start_waypoint_name = self.waypoint_graph.nodes[closest_node].description
                        start_waypoint = closest_node

                    for i in work_info.start_idx:
                        work_composition_list[i] = start_waypoint_name

                if self.set_start_waypoint(module_name, agv_work_data, work_composition_list, start_waypoint, target_waypoint, work_info.start_idx) is False:
                    # 시작 웨이포인트를 지정 못 할 경우
                    raise Exception("시작 웨이포인트 지정 실패")
            except Exception as e:
                self.send_event(module_name, "error", f"{agv_work_data.idx} 항목 작업 시작 불가 ({e})")
                log_msg: str = f"작업을 시작 할 수 없습니다. ({e})" \
                               f"에러코드: 14 (웨이포인트 지정 실패), " \
                               f"항목 번호: {agv_work_data.idx} "
                self.set_cmd_error(module_name, agv_work_data.idx, 14)  # 웨이포인트 지정 실패
                self.logger.info(f"[명령 시작] [{module_name}] {log_msg}")
                return False

        self.send_set_charge(module_name, False)  # 충전 OFF 보내기
        self.set_agv_cmd_status(module_name, True)
        self.agv_data[module_name]['reach_flag'] = True
        self.agv_data[module_name]['work_process'] = work_process
        self.agv_data[module_name]['cmd_process'] = cmd_process
        self.agv_data[module_name]['work_composition_info'] = work_composition_info
        self.agv_data[module_name]['work_composition_list'] = work_composition_list
        self.agv_data[module_name]['cmd_path_list'] = cmd_path_list
        self.agv_data[module_name]['cmd_agv_collision_list'] = cmd_agv_collision_list
        self.agv_data[module_name]['agv_work_data'] = agv_work_data
        self.agv_data[module_name]['fast_start_flag'] = fast_start_flag
        self.agv_data[module_name]['cmd_error_flag'] = False

        log_msg: str = f"작업 명령을 시작합니다. " \
                       f"항목 번호: {agv_work_data.idx}, " \
                       f"시작한 작업 번호: {agv_work_data.work_idx}, " \
                       f"작업 진행 번호: {work_process}, " \
                       f"명령 진행 번호: {cmd_process}"
        self.logger.info(f"[명령 시작] [{module_name}] {log_msg}")
        self.send_event(module_name, "success", f"{agv_work_data.idx} 항목 작업 시작")
        return True

    # 시작 가능한 웨이포인트인지 확인
    def set_start_waypoint(self, module_name: str, agv_work_data: AgvWorkList, work_composition_list: list,
                           start_waypoint: int, target_waypoint: int, position_idx: list):
        # ============ 시작 노드 이름 찾기 ==================
        print(module_name, agv_work_data, work_composition_list, start_waypoint, target_waypoint, position_idx)
        start_waypoint_node: Node | None = self.waypoint_graph.nodes.get(start_waypoint)
        start_node_name: str = ""
        if start_waypoint_node is not None:
            start_node_name = start_waypoint_node.description
        if start_node_name == "":
            # 노드 이름이 없다면 넘기기
            return False

        # ============= 경로 구성 가능한지 확인 =================
        path: list | None = self.waypoint_graph.lpa_star(module_name, start_waypoint, target_waypoint, False,False)
        if path is None or len(path) == 0:
            # 경로 구성에 실패한 경우 넘기기
            return False

        # ============= 시작 노드 입력 =================
        for i in position_idx:
            work_composition_list[i] = start_node_name
        try:
            # DB 업데이트
            agv_work_data.work_composition_list = orjson.dumps(work_composition_list, default=json_default).decode("utf-8")
            update_agv_work(self.db, agv_work_data)
        except Exception:
            # 적용 실패 시 넘기기
            print(traceback.format_exc())
            return False
        return True

    # 명령 도달 처리 함수
    def cmd_reach_process(self, module_name: str):
        agv_work_data: AgvWorkList = self.agv_data[module_name]['agv_work_data']
        if self.agv_data[module_name]['reach_flag'] is True:
            # 웨이포인트 도달할 경우
            work_process: int = self.agv_data[module_name]['work_process']
            cmd_process: int = self.agv_data[module_name]['cmd_process'] + 1

            work_composition_list: list = self.agv_data[module_name]['work_composition_list']
            cmd_path_flag: bool = False
            if len(self.agv_data[module_name]['cmd_path_list']) == 0:
                try:
                    self.cmd_init_path(module_name, agv_work_data.work_idx)
                    cmd_path_flag = True
                except Exception as e:
                    print(traceback.format_exc())
                    self.send_event(module_name, "error", f"{agv_work_data.idx} 항목 작업 진행 불가", str(e))
                    log_msg: str = f"작업을 진행 할 수 없습니다. ({e})" \
                                   f"에러코드: 14 (웨이포인트 지정 실패), " \
                                   f"항목 번호: {agv_work_data.idx} "
                    self.set_cmd_error(module_name, agv_work_data.idx, 14)  # 웨이포인트 지정 실패
                    self.logger.info(f"[명령 수행] [{module_name}] {log_msg}")
                    return

            cmd_path_list = self.agv_data[module_name]['cmd_path_list']
            work_composition_count: int = len(cmd_path_list)
            cmd_composition_count: int = len(cmd_path_list[work_process])

            print("===================================================")
            print("웨이포인트 도달", work_process, cmd_process, work_composition_count, cmd_composition_count)
            print("===================================================")

            # =========================
            # 명령 수행 번호 최종 도달
            # =========================
            if (cmd_composition_count != 0 or work_process == 0) and cmd_process >= cmd_composition_count:
                # 명령 수행 번호가 최종 도달한 경우
                if work_process + 1 >= len(work_composition_list):
                    # 다음 작업 수행 번호가 최종 도달한 경우 작업 완료
                    log_msg: str = f"작업 명령을 완료했습니다. " \
                                   f"항목 번호: {agv_work_data.idx}, " \
                                   f"완료한 작업 번호: {agv_work_data.work_idx}"
                    self.logger.info(f"[작업 수행] [{module_name}] {log_msg}")
                    self.send_event(module_name, "success", f"{agv_work_data.idx} 항목 작업 완료")
                    self.set_agv_cmd_status(module_name, False)
                    self.agv_work_data_clear(module_name)
                    self.set_cmd_pause(module_name)

                    # DB 업데이트
                    set_agv_work_complete(self.db, agv_work_data.idx, 1)
                    return
                else:
                    # 작업 수행 번호가 최종 도달이 아닌 경우 다음 명령 진행
                    cmd_process = 1
                    work_process += 1

            # =========================
            # 빠른 시작 가능 구역일 경우 출발 웨이포인트 찾기
            # =========================
            work_composition_info_idx: int = self.agv_data[module_name]["work_composition_info"][work_process]
            work_composition_info: WorkCompositionList = self.work_composition_list[work_composition_info_idx]
            if work_composition_info.fast_start_possible is True:
                # 빠른 시작 가능 구역 이라면
                start_waypoint = 0
                if work_composition_count != 0 and cmd_composition_count != 0:
                    start_waypoint: int = cmd_path_list[work_process][cmd_process - 1]
                else:
                    start_position: str = work_composition_list[work_process]
                    start_waypoint_idx: int | None = self.waypoint_graph.get_node_idx(start_position)
                    if start_waypoint_idx is not None:
                        # 출발 웨이포인트가 없는 경우 넘기기
                        start_waypoint = start_waypoint_idx

                if start_waypoint != 0 and self.work_fast_start(module_name, start_waypoint=start_waypoint) is True:
                    return

            log_msg: str = f"다음 웨이포인트 진행합니다. " \
                           f"항목 번호: {agv_work_data.idx}, " \
                           f"진행중인 작업: {agv_work_data.work_idx}, " \
                           f"다음 작업 번호: {work_process}, " \
                           f"다음 웨이포인트 번호: {cmd_process}"
            self.logger.info(f"[작업 수행] [{module_name}] {log_msg}")
            self.set_agv_cmd_status(module_name, True)

            # 작업 수행 번호, 명령 수행 번호 업데이트
            self.agv_data[module_name]['work_process'] = work_process
            self.agv_data[module_name]['cmd_process'] = cmd_process
            print("===================================================")
            print("다음 웨이포인트 진행", work_process, cmd_process, work_composition_count, cmd_composition_count)
            print("===================================================")

            # =========================
            # DB 업데이트
            # =========================
            agv_work_data.error_flag = False
            agv_work_data.error_code = 0
            agv_work_data.work_process = work_process
            agv_work_data.cmd_process = cmd_process
            if cmd_path_flag is True:
                agv_work_data.cmd_path_list = orjson.dumps(self.agv_data[module_name]['cmd_path_list'], default=json_default).decode("utf-8")
                agv_work_data.cmd_agv_collision_list = orjson.dumps(self.agv_data[module_name]['cmd_agv_collision_list'], default=json_default).decode("utf-8")
            update_agv_work(self.db, agv_work_data)
        else:
            # 웨이포인트 도달하지 않은 경우 초기화 진행
            try:
                self.cmd_init_process(module_name)
            except Exception as e:
                print(traceback.format_exc())
                self.send_event(module_name, "error", f"{agv_work_data.idx} 항목 작업 진행 불가", str(e))
                log_msg: str = f"작업을 진행 할 수 없습니다. ({e})" \
                               f"에러코드: 15 (작업 지정 실패), " \
                               f"항목 번호: {agv_work_data.idx}"
                self.set_cmd_error(module_name, agv_work_data.idx, 15)  # 작업 지정 실패
                self.logger.info(f"[명령 수행] [{module_name}] {log_msg}")
        self.agv_data[module_name]['cmd_error_flag'] = False

    # 경로 구성
    def cmd_init_path(self, module_name: str, work_idx: int):
        cmd_path_list: list = []
        cmd_agv_collision_list: list = []
        start_waypoint: int | str = 0
        work_composition_list: list = self.agv_data[module_name]['work_composition_list']

        work_info: WorkInfoList | None = self.work_info_list.get(work_idx)
        if work_info is None:
            raise Exception("명령 구성 정보 없음")

        for i in range(len(work_composition_list)):
            destination_waypoint = self.waypoint_graph.get_node_idx(work_composition_list[i])
            cmd_composition_list: list = []
            work_composition_idx: int = self.agv_data[module_name]["work_composition_info"][i]
            work_composition: WorkCompositionList | None = self.work_composition_list.get(work_composition_idx)
            if i != 0:
                if work_composition is None:
                    raise Exception("명령 구성 정보 없음")

                if work_composition.driving_flag is True:
                    # 주행 작업이라면
                    path = self.waypoint_graph.lpa_star(module_name, start_waypoint, destination_waypoint,False, False)
                    if path is None or len(path) == 0:
                        raise Exception("경로 구성 실패")
                    cmd_composition_list += path

                    # ======= 충돌 확인 위치 찾기 =======
                    for path_i in range(1, len(path)):
                        pre_path = path[path_i - 1]
                        target_path = path[path_i]
                        edge_command_data: dict = self.waypoint_graph.edge_command_data[pre_path][target_path]
                        interlock_data_list = edge_command_data.get("interlock", [])
                        for interlock_data in interlock_data_list:
                            if interlock_data.get("name") == "agv_collision":
                                cmd_agv_collision_list.append([i, path_i])
                else:
                    # 주행 이외 작업이라면
                    cmd_composition_list.append(start_waypoint)
                    target_waypoint = start_waypoint
                    command_composition: list = work_composition.command
                    for idx in range(len(command_composition)):
                        command_data = command_composition[idx]
                        option: dict = command_data.get("option", {})
                        interlock_data_list = option.get("interlock", [])
                        cmd_composition_list.append(target_waypoint)

                        # ======= 충돌 확인 위치 찾기 =======
                        for interlock_data in interlock_data_list:
                            if interlock_data.get("name") == "agv_collision":
                                cmd_agv_collision_list.append([i, idx + 1])
            cmd_path_list.append(cmd_composition_list)
            start_waypoint = destination_waypoint
        self.agv_data[module_name]['cmd_path_list'] = cmd_path_list
        self.agv_data[module_name]['cmd_agv_collision_list'] = cmd_agv_collision_list

    # 명령 초기화 처리
    def cmd_init_process(self, module_name: str):
        # =======================
        # 초기화
        # =======================
        if self.agv_data[module_name]['init_flag'] is False:
            self.set_cmd_composition(module_name)
            self.agv_data[module_name]['init_flag'] = True

        # =======================
        # 인터락 전 신호 보내기
        # =======================
        if self.agv_data[module_name]['pre_working_sgn_flag'] is False:
            # 이전 작업 신호 전송하지 않는 경우
            self.send_working_signal(module_name, "pre_sgn")
            self.agv_data[module_name]['pre_working_sgn_flag'] = True

        # =======================
        # 인터락 확인
        # =======================
        wait_reason: list = []
        if self.agv_data[module_name]['interlock_check_flag'] is False:
            # 인터락 확인이 안되었다면
            interlock_check_flag: bool = self.get_interlock_check(module_name, wait_reason)
            self.agv_data[module_name]['interlock_check_flag'] = interlock_check_flag
            if interlock_check_flag is True:
                # 인터락 확인이 되었다면 명령 진행
                command_data: dict = self.agv_data[module_name]["cmd_composition_list"]["command_data"]
                self.agv_data[module_name]['wait_flag'] = False
                self.agv_data[module_name]["wait_reason"].clear()
                self.send_working_signal(module_name, "after_sgn")
                self.agv_data[module_name]['work_start_time'] = datetime.datetime.now()
                self.send_agv_cmd(module_name, cmd_flag=True, command_data=command_data)
            else:
                if self.agv_data[module_name]['wait_flag'] is False or len(wait_reason) != len(self.agv_data[module_name]["wait_reason"]):
                    # 대기 상태가 아닌 경우 AGV 명령 데이터 갱신 (대기 이유 리스트가 바뀐 경우도 AGV 명령 데이터 갱신)
                    self.agv_data[module_name]['wait_flag'] = True
                    self.agv_data[module_name]["wait_reason"] = wait_reason
                    self.send_agv_cmd(module_name, cmd_flag=True)
            self.agv_data[module_name]['interlock_check_flag'] = interlock_check_flag
        else:
            # 인터락 확인 (명령 비상 정지)
            wait_reason: list = []
            interlock_check_flag = self.get_interlock_check(module_name, wait_reason)
            self.set_cmd_emergency(module_name, not interlock_check_flag, wait_reason)

    # 작업 신호 보내기
    def send_working_signal(self, module_name: str, sgn_type: str):
        cmd_composition_list: dict = self.agv_data[module_name]['cmd_composition_list']
        working_sgn_data_list = cmd_composition_list.get(sgn_type, [])

        send_working_sgn_data = {}
        for working_sgn_data in working_sgn_data_list:
            try:
                interlock_signal: dict = self.interlock_signal_data[working_sgn_data["name"]][working_sgn_data["sub"]]
                module_name: str = interlock_signal["module_name"]
                status_name: str = interlock_signal["status_name"]
                if send_working_sgn_data.get(module_name) is None:
                    send_working_sgn_data[module_name] = {}
                send_working_sgn_data[module_name][status_name] = working_sgn_data["value"]
            except Exception as e:
                print(traceback.format_exc())

        for module_name, working_sgn_data in send_working_sgn_data.items():
            cmd_data: dict = {
                "type": "working_sgn_data",
                "module_name": module_name,
                'data': working_sgn_data
            }
            self.cmd_send_data_queue.put(cmd_data)

    # 명령 구성
    def set_cmd_composition(self, module_name: str):
        work_composition_list: list = self.agv_data[module_name]['work_composition_list']
        work_process: int = self.agv_data[module_name]['work_process']
        cmd_process: int = self.agv_data[module_name]['cmd_process']
        cmd_path_list: list = self.agv_data[module_name]['cmd_path_list']
        work_composition_info_idx: int = self.agv_data[module_name]["work_composition_info"][work_process]
        work_composition_info: WorkCompositionList = self.work_composition_list[work_composition_info_idx]

        cmd_composition_list = {}
        if work_composition_info.driving_flag is True:
            # 주행 작업인 경우
            start_waypoint: int = cmd_path_list[work_process][cmd_process - 1]
            destination_waypoint: int = cmd_path_list[work_process][cmd_process]

            start_node: Node = self.waypoint_graph.nodes[start_waypoint]
            destination_node: Node = self.waypoint_graph.nodes[destination_waypoint]
            command_data: dict = destination_node.command_data
            command_option_data: dict = self.waypoint_graph.edge_command_data[start_waypoint][destination_waypoint]
            pre_axis_data = {
                "pre_X": start_node.x,
                "pre_Y": start_node.y,
            }
        else:
            # 주행 이외 작업인 경우
            pre_axis_data = {}
            work_command_data: dict = work_composition_info.command[cmd_process - 1]
            waypoint: dict = work_command_data["waypoint"]
            command_option_data: dict = work_command_data.get("option", {})
            waypoint_number: int = waypoint.get("number", 0)
            sub_name: str = waypoint.get("sub", "")
            if sub_name == "com":
                composition_name: str = work_composition_list[work_process]
            elif sub_name == "agv":
                composition_name: str = module_name
            else:
                composition_name: str = ""

            waypoint_type: str | None = waypoint.get("type")
            if waypoint_type == "driving":
                # 타입이 주행이라면
                waypoint_data: WaypointDriving | None = get_waypoint_driving(self.db, waypoint_number, composition_name)
                start_waypoint = cmd_path_list[work_process][cmd_process - 1]
                start_node: Node = self.waypoint_graph.nodes[start_waypoint]
                pre_axis_data["pre_X"] = start_node.x
                pre_axis_data["pre_Y"] = start_node.y
            elif waypoint_type == "common":
                # 타입이 주행이외이라면
                waypoint_data: WaypointCommon | None = get_waypoint_common(self.db, waypoint_number, composition_name)
            else:
                # 타입이 존재하지않다면
                waypoint_data = None

            if waypoint_data is None:
                raise Exception(f"{waypoint_number} 항목의 웨이포인트가 없습니다.")
            command_data = orjson.loads(waypoint_data.command)

        cmd_composition_list["command_data"] = command_data | command_option_data.get("command", {}) | pre_axis_data
        cmd_composition_list["pre_sgn"] = command_option_data.get("pre_sgn", [])
        cmd_composition_list["interlock"] = command_option_data.get("interlock", [])
        cmd_composition_list["after_sgn"] = command_option_data.get("after_sgn", [])
        self.agv_data[module_name]["cmd_composition_list"] = cmd_composition_list

    # 인터록 확인
    def get_interlock_check(self, module_name: str, wait_reason: list) -> bool:
        work_process: int = self.agv_data[module_name]['work_process']
        cmd_process: int = self.agv_data[module_name]['cmd_process']
        cmd_path_list: list = self.agv_data[module_name]['cmd_path_list']
        cmd_composition_list: dict = self.agv_data[module_name]['cmd_composition_list']
        interlock_data_list: list = cmd_composition_list.get("interlock", [])
        interlock_check_flag: bool = True
        for interlock_data in interlock_data_list:
            if interlock_data["name"] == "agv_collision":
                check_work_process_idx, check_cmd_process_idx = self.get_agv_collision_check(module_name,
                                                                                             work_process,
                                                                                             cmd_process,
                                                                                             True)
                start_position: int = cmd_path_list[work_process][cmd_process]
                destination_position: int = cmd_path_list[check_work_process_idx][check_cmd_process_idx]

                path: list | None = self.waypoint_graph.lpa_star(module_name, start_position, destination_position, False,False)
                if path is None or len(path) == 0:
                    interlock_check_flag = False
                    wait_reason.append("경로 상 AGV 존재")
            else:
                interlock_signal: dict = self.interlock_signal_data[interlock_data["name"]][interlock_data["sub"]]
                module_name: str = interlock_signal["module_name"]          # 모듈 이름
                status_name: str = interlock_signal["status_name"]          # 상태 이름
                pre_value: any = interlock_signal["value"]                  # 이전 값
                now_value = self.integrate_data[module_name][status_name]   # 현재 값
                interlock_value: any = interlock_data["value"]              # 조건 값

                timer = interlock_data.get("timer", 0)                      # 타이머 (일정 시간동안 유지 조건)
                if timer != 0:
                    if (now_value != pre_value or interlock_signal["time"] is None or
                            self.agv_data[module_name]['work_start_time'] > interlock_signal["time"]):
                        # 값이 맞지 않거나, 인터락 시간이 없거나, 인터락 시간이 작업 시작 시간보다 작을 경우 초기화
                        interlock_signal["value"] = now_value
                        interlock_signal["time"] = datetime.datetime.now()

                    if now_value == pre_value == interlock_value and self.now_time - interlock_signal["time"] >= datetime.timedelta(seconds=timer):
                        # 인터락 상태가 동일하고, 지정된 초 이상 유지된 경우 통과
                        pass
                    else:
                        # 데이터가 맞지 않다면
                        interlock_check_flag = False
                        wait_reason.append(f'{interlock_signal["description"]} [현재]{now_value} != [조건]{interlock_value} (유지 시간: {timer})')
                else:
                    if now_value != interlock_value:
                        # 하나라도 데이터가 맞지 않다면
                        interlock_check_flag = False
                        wait_reason.append(f'{interlock_signal["description"]} [현재]{now_value} != [조건]{interlock_value}')
        return interlock_check_flag

    # 자동 비상 정지 설정 (flag : True = 비상정지 설정 / False = 비상정지 해제)
    def set_cmd_emergency(self, agv_module_name: str, flag: bool, wait_reason: list | None = None):
        if self.agv_data[agv_module_name]['cmd_emergency'] is not flag:
            # 명령 비상정지가 걸려있다면 비상정지 해제
            self.agv_data[agv_module_name]['cmd_emergency'] = flag
            self.send_cmd_emergency_stop(agv_module_name, flag)
        elif self.agv_status[agv_module_name]['cmd_emg_stop'] is not flag and \
                self.pre_second != self.now_time.second:
            # 명령 비상정지가 걸려있지않는데 AGV가 걸려있다면 1초마다 비상정지 해제
            self.send_cmd_emergency_stop(agv_module_name, flag, wait_reason)

    # 명령 비상 정지 보내기
    def send_cmd_emergency_stop(self, module_name: str, flag: bool, wait_reason: list | None = None):
        cmd_data: dict = {
            "type": "send",
            'module_name': module_name,
            'data': {
                "cmd_emg_stop": {
                    "flag": flag
                }
            }
        }
        if wait_reason is not None:
            if len(wait_reason) != 0:
                cmd_data['data']['cmd_emg_stop']['wait_reason'] = wait_reason
        self.cmd_send_data_queue.put(cmd_data)
        self.logger.info(f"[명령 비상 정지] 명령 비상 정지 데이터를 보냅니다. 명령 비상 정지 데이터: {cmd_data}")

    # 작업 빠른 시작
    def work_fast_start(self, module_name: str, start_waypoint: int):
        # 작업 목록 가져오기
        work_list: list = get_agv_work_list(self.db, module_name)
        work_list_data: AgvWorkList = self.agv_data[module_name]['agv_work_data']
        agv_work_list_idx: int = work_list_data.idx
        agv_work_list_work_idx: int = work_list_data.work_idx

        if len(work_list) > 1:
            # 작업이 2개 이상 있을 경우
            work_index: int = 1
            if work_list[0].idx == agv_work_list_idx:
                # 0인덱스가 현재 인덱스일 경우 그 다음 인덱스로 설정
                work_index = 1
            else:
                if work_list[0].work_process == 0 and work_list[0].cmd_process == 0:
                    # 첫번째 작업 진행 번호가 0일 경우 현재 작업 리스트 번호 찾기
                    for i in range(1, len(work_list)):
                        if work_list[i].idx == agv_work_list_idx:
                            # 첫번째 작업 리스트 이후 현재 작업 리스트가 있다면 해당 작업 선택
                            work_index = 0
                            break
                    if work_index == 1:
                        # 다음 명령이 맞지않은 경우 (현재 작업 리스트가 없음) 빠른 시작 불가로 다음 웨이포인트 진행
                        return False
                else:
                    # 다음 명령이 맞지않은 경우 빠른 시작 불가로 다음 웨이포인트 진행
                    return False

            idx = work_list[work_index].idx  # 작업 seq 번호
            work_idx = work_list[work_index].work_idx  # 작업 번호
            work_process = work_list[work_index].work_process  # 작업 진행 번호
            cmd_process = work_list[work_index].cmd_process  # 명령 진행 번호
            error_flag = work_list[work_index].error_flag  # 에러 여부
            auto_flag = work_list[work_index].auto_flag
            self.agv_data[module_name]['auto_flag'] = auto_flag  # 자동 여부

            work_info: WorkInfoList | None = self.work_info_list.get(work_idx)
            if work_info is not None:
                if work_info.home_return_flag is True:
                    # 홈 복귀 작업이라면 빠른 시작 X
                    return False
                elif error_flag is True:
                    # 에러 발생한 경우 빠른 시작 X
                    return False
                elif self.agv_status[module_name]['bat_soc'] >= self.bat_acceptable or \
                     self.agv_status[module_name]['bat_ignore'] is True:
                    # 배터리 잔량이 허용치보다 높을 경우
                    if self.cmd_start(module_name, work_list[work_index], fast_start_flag=True, start_waypoint=start_waypoint) is False:
                        # 예외 발생 시 빠른 시작 불가능으로 다음 웨이포인트 진행
                        log_msg: str = f"다음 작업을 진행할 수 없어 해당 작업 계속 진행합니다."
                        self.logger.info(f"[작업 수행] [{module_name}] {log_msg}")
                        return False
                    else:
                        set_agv_work_start_time(self.db, idx)  # 시작 시간 설정
                        log_msg: str = f"다음 작업이 가능한 곳에 도착했습니다. 작업 명령을 완료했습니다. " \
                                       f"항목 번호: {agv_work_list_idx}, " \
                                       f"완료한 작업 번호: {agv_work_list_work_idx}"
                        self.logger.info(f"[작업 수행] [{module_name}] {log_msg}")
                        self.send_event(module_name, "success", f"{agv_work_list_work_idx} 항목 작업 완료")

                        # DB 업데이트
                        set_agv_work_complete(self.db, agv_work_list_idx, 1)
                        self.agv_work_data_clear(module_name, all_flag=False)
                        return True
                else:
                    # 배터리 잔량이 부족하여 빠른 시작 X
                    return False

    # =================================================
    #                   명령 큐 관련 함수
    # =================================================
    # 명령 큐 수신 프로세스
    async def cmd_queue_recv_process(self):
        while not self.stop_event.is_set():
            while self.cmd_recv_data_queue.qsize() != 0:
                try:
                    cmd_queue_data = self.cmd_recv_data_queue.get()  # 데이터 가져오기
                    cmd_type: str = cmd_queue_data['type']
                    cmd_data: any = cmd_queue_data['data']
                    if cmd_type == 'integrate_data':
                        # 통합 데이터라면
                        self.set_update_integrate_data(cmd_data)
                    elif cmd_type == 'add_cmd':
                        # 타입이 명령 추가라면
                        self.set_add_cmd(cmd_type, cmd_data)
                    elif cmd_type == 'add_auto_cmd':
                        # 타입이 명령 자동 추가라면
                        self.set_add_cmd(cmd_type, cmd_data)
                    elif cmd_type == 'cmd_stop':
                        # 타입이 명령 정지라면
                        self.set_cmd_stop(cmd_data)
                    elif cmd_type == 'cmd_restart':
                        # 타입이 명령 재시작이라면
                        self.set_cmd_restart(cmd_data)
                    elif cmd_type == 'cmd_delete':
                        # 타입이 명령 삭제라면
                        self.set_cmd_delete(cmd_data)
                    elif cmd_type == 'wait_clear':
                        # 타입이 대기 해제라면
                        self.set_wait_clear(cmd_data)
                    elif cmd_type == 'set_auto_mode':
                        self.set_auto_mode(cmd_data)
                    # elif cmd_type == 'cmd_position_init':
                    #     # 위치 초기화 명령
                    #     self.set_position_init(cmd_data)
                    elif cmd_type == 'bat_ignore':
                        self.set_bat_ignore(cmd_data)
                except Exception:
                    self.logger.warning(f"명령 수신 Queue 처리 도중 에러 발생, 에러 메시지: {traceback.format_exc()}")
            await asyncio.sleep(0.1)

    # 자동 모드 설정
    def set_auto_mode(self, cmd_data):
        module_name: str = cmd_data.get('module_name')
        flag: bool = cmd_data.get('flag', False)
        if self.agv_status.get(module_name) is not None:
            self.agv_status[module_name]["auto_mode"] = flag

    # 통합 데이터 업데이트
    def set_update_integrate_data(self, integrate_datas):
        for module_name, integrate_data in integrate_datas.items():

            if self.integrate_data.get(module_name) is None:
                self.integrate_data[module_name] = {}

            # 통합 데이터 업데이트
            self.integrate_data[module_name].update(flatten_dict(integrate_data))

            if self.agv_status.get(module_name) is not None:
                # AGV 데이터 업데이트
                connect_flag: bool | None = integrate_data.get("connect")
                if connect_flag is not None:
                    self.agv_status[module_name]['connect'] = connect_flag
                disable_flag: bool | None = integrate_data.get("disable")
                if disable_flag is not None:
                    self.agv_status[module_name]['disable'] = disable_flag
                agv_state_data: dict | None = integrate_data.get("agv_state")
                if agv_state_data is not None and len(agv_state_data) != 0:
                    self.agv_status[module_name].update(agv_state_data)
                cmd_info_data: dict | None = integrate_data.get("cmd_info")
                if cmd_info_data is not None and len(cmd_info_data) != 0:
                    self.set_agv_cmd_info(module_name, cmd_info_data)

    # AGV 명령 데이터 설정
    def set_agv_cmd_info(self, module_name: str, cmd_info_data: dict):
        # 'cmd_flag': False,  # 명령 수행 여부
        # 'cmd_start': False,  # 명령 수행 시작 여부
        # 'cmd_error': False,  # 명령 에러 여부
        # 'cmd_error_type': 0,  # 명령 에러 타입
        # 'cmd_reach_flag': False,  # 명령 도달 여부
        # 'cmd_work_no': 0,  # 작업 번호 (도착지 번호)
        # 'cmd_number': 0,  # 명령 번호 (웨이포인트[노드] 번호)
        # 'cmd_work_name': "",  # 명령 작업 이름
        # 'cmd_work_position': "",  # 명령 작업 위치
        # 'cmd_wait_flag': False,  # 명령 작업 대기 여부
        # 'precise_mode': False,  # 정밀 모드 여부
        self.agv_cmd_info[module_name].update(cmd_info_data)
        work_reach_flag: bool = cmd_info_data.get('cmd_reach_flag', False)
        cmd_flag: bool = self.agv_cmd_info[module_name].get('cmd_flag', False)
        work_no: int = self.agv_cmd_info[module_name].get('cmd_work_no', 0)
        cmd_number: int = self.agv_cmd_info[module_name].get('cmd_number', 0)
        move_error: bool = self.agv_cmd_info[module_name].get('cmd_error', False)
        error_type: int = self.agv_cmd_info[module_name].get('cmd_error_type', 0)
        cmd_start = self.agv_cmd_info[module_name].get('cmd_start')
        self.agv_data[module_name]['agv_cmd_flag'] = cmd_start
        self.logger.info(f"[{module_name}] 명령 수신 데이터: {self.agv_cmd_info[module_name]}")

        if self.agv_data[module_name]['acs_cmd_flag'] is True:
            # agv 가 명령 수행중일 경우
            if cmd_start is True:
                if self.agv_data[module_name]['cmd_process'] == cmd_number and self.agv_data[module_name]['work_process'] == work_no:
                    # 명령 번호가 동일 한 경우
                    if self.agv_data[module_name]['wait_flag'] is False:
                        # 대기 중이 아닌 경우
                        print("wait_flag: False")
                        if move_error is True:
                            # 에러 발생 시 자동 명령 에러 설정
                            agv_work_data: AgvWorkList = self.agv_data[module_name]['agv_work_data']
                            if agv_work_data is not None:
                                agv_work_list_idx: int = agv_work_data.idx
                                print("자동 에러 설정")
                                self.set_cmd_error(module_name, agv_work_list_idx, error_type)  # 자동 명령 에러
                        else:
                            if work_reach_flag is True:
                                print("reach_flag: True")
                                # 수행 완료했다면 도달 설정
                                self.agv_data[module_name]['reach_flag'] = True
                    self.agv_data[module_name]['work_flag'] = True
        else:
            if move_error is True and self.agv_data[module_name]['cmd_error_flag'] is False:
                # 자동 명령 오류가 났는데 ACS에서 오류가 발생하지 않았다면 AGV 자동 명령 초기화
                self.send_agv_cmd(module_name, cmd_flag=False)

    # 대기 명령 해제
    def set_wait_clear(self, cmd_data: dict):
        module_name: str = cmd_data.get('module_name')

        success_flag = True
        response_msg = ""
        if self.agv_data[module_name]['wait_flag'] is True:
            # 대기 중일 경우
            self.agv_data[module_name]['interlock_ignore'] = True
            log_text: str = f'[{module_name}] AGV 대기 명령 (비상 정지) 해제합니다.'
        elif self.agv_data[module_name]['cmd_emergency'] is True:
            # 자동 비상정지일 경우
            self.agv_data[module_name]['interlock_ignore'] = True
            self.agv_data[module_name]['cmd_emergency'] = False
            log_text: str = f'[{module_name}] 대기 명령 (비상 정지) 해제합니다.'
        else:
            success_flag = False
            log_text: str = f'[{module_name}] AGV가 대기 중이지 않습니다.'
            response_msg = "현재 AGV는 대기 중이지 않습니다"
        self.logger.info(f"[대기 명령 해제] {log_text}")

        cmd_data: dict = {
            "type": "response_cmd",
            "data": {
                "type": "wait_clear",
                "working_id": cmd_data.get('working_id', 0),
                "data": {
                    "flag": success_flag,
                    "msg": response_msg
                }
            }
        }
        self.cmd_send_data_queue.put(cmd_data)

    # 명령 추가 설정
    def set_add_cmd(self, cmd_type: str, cmd_data: dict):
        print("set_add_cmd", cmd_data)
        module_name: str | None = cmd_data.get('module_name', None)
        work_idx: int = cmd_data['work_idx']
        auto_flag: bool = cmd_data['auto_flag']
        force_flag: bool = cmd_data.get("force_flag", False)
        unloading_position: str = cmd_data["unloading_position"]
        loading_position: str = cmd_data["loading_position"]
        arrival_position: str = cmd_data["arrival_position"]

        unloading_position_display = self.waypoint_graph.get_node_display(unloading_position)
        loading_position_display = self.waypoint_graph.get_node_display(loading_position)
        arrival_position_display = self.waypoint_graph.get_node_display(arrival_position)

        display_str: str = f"{unloading_position_display} ▶ {loading_position_display}"

        log_msg: str = f"작업 번호: {work_idx}, " \
                       f"작업 위치: {display_str}, " \
                       f"도착 위치: {arrival_position_display}, " \
                       f"반/자동 여부: {'자동' if auto_flag is True else '반자동'}"
        success_flag = False
        response_msg = ""

        if module_name is None:
            module_name = self.get_auto_possible_agv(unloading_position)

        # DB 업데이트
        try:
            if module_name is not None:
                work_info: WorkInfoList | None = self.work_info_list.get(work_idx)
                if work_info is None:
                    response_msg = f"[{display_str}] 존재하지 않는 작업입니다"
                    self.logger.info(f"[명령 추가] [{module_name}] 존재하지 않는 작업입니다. ({log_msg})")
                else:
                    work_composition_list = []
                    for i in range(len(work_info.work_composition)):
                        if i in work_info.unloading_idx:
                            work_composition_list.append(unloading_position)
                        elif i in work_info.loading_idx:
                            work_composition_list.append(loading_position)
                        elif i in work_info.arrival_idx:
                            work_composition_list.append(arrival_position)
                        else:
                            work_composition_list.append("")

                    if work_info.home_return_flag is True:
                        # 복귀 작업인 경우
                        work_list: list = get_agv_work_list(self.db, module_name)
                        if len(work_list) == 0:
                            now_x_axis: float = self.agv_status[module_name]['x_axis']
                            now_y_axis: float = self.agv_status[module_name]['y_axis']
                            now_angle: float = self.agv_status[module_name]['angle']

                            agv_home_data: dict | None = self.agv_home.get(module_name, {}).get(arrival_position)
                            if agv_home_data is None:
                                raise Exception(f"도착지 {arrival_position} 웨이포인트 정보가 없습니다.")
                            arrival_position_waypoint = agv_home_data["waypoint_no"]

                            if arrival_position_waypoint is None:
                                response_msg = f"[{display_str}] {arrival_position} 웨이포인트 정보가 없습니다"
                                self.logger.info(f"[명령 추가] [{module_name}] 작업 명령이 들어왔으나, {arrival_position} 웨이포인트 정보가 없습니다. ({log_msg})")
                            else:
                                closest_node, intersection_point, closest_edge = self.waypoint_graph.find_destination_closest_edge(now_x_axis, now_y_axis, now_angle, arrival_position_waypoint.idx)
                                if closest_node is None or intersection_point is None or closest_edge is None:
                                    response_msg = f"[{display_str}] 복귀 가능한 구역이 아닙니다"
                                    self.logger.info(f"[명령 추가] [{module_name}] 작업 명령이 들어왔으나, 복귀 가능한 구역이 아닙니다. ({log_msg})")
                                else:
                                    for i in work_info.start_idx:
                                        work_composition_list[i] = closest_node
                                    idx = add_agv_work(self.db, module_name, work_idx, work_composition_list, auto_flag)
                                    self.logger.info(f"[명령 추가] [{module_name}] [{idx}] 작업 명령이 들어와 목록에 추가합니다. ({log_msg})")
                                    success_flag = True
                        else:
                            response_msg = f"[{display_str}] 작업 리스트를 초기화 후 다시 추가해주세요"
                            self.logger.info(f"[명령 추가] [{module_name}] 작업 리스트가 존재로 복귀가 불가능합니다. ({log_msg})")
                    else:
                        overlap_work_data = search_overlap_work(self.db, work_idx, work_info, cmd_data['work_composition_list'])
                        if overlap_work_data is False or force_flag is True:
                            idx = add_agv_work(self.db, module_name, work_idx, work_composition_list, auto_flag)
                            self.send_event(module_name, "success", f"{display_str} 작업 추가")
                            self.logger.info(f"[명령 추가] [{module_name}] [{idx}] 작업 명령이 들어와 목록에 추가합니다. ({log_msg})")
                            success_flag = True
                        else:
                            response_msg = f"[{display_str}] 동일한 작업이 존재합니다"
                            self.logger.info(f"[명령 추가] [{module_name}] 작업 명령이 들어왔으나, 동일한 작업이 존재합니다. ({log_msg})")
            else:
                response_msg = f"[{display_str}] 작업 가능한 AGV가 없습니다"
                self.logger.info(f"[명령 추가] 작업 명령이 들어왔으나, 작업 가능한 AGV가 없습니다. ({log_msg})")
        except Exception as e:
            response_msg = f"[{display_str}] 작업 명령 추가에 실패하였습니다"
            self.logger.info(f"[명령 추가] [{module_name}] 작업 명령 추가에 실패하였습니다. ({log_msg}) 예외 메시지: {traceback.format_exc()}")

        cmd_data: dict = {
            "type": "response_cmd",
            "data": {
                "type": cmd_type,
                "working_id": cmd_data.get('working_id', 0),
                "data": {
                    "flag": success_flag,
                    "msg": response_msg,
                }
            }
        }
        self.cmd_send_data_queue.put(cmd_data)

    # 작업 가능한 AGV 가져오기
    def get_auto_possible_agv(self, unloading_position: str):
        agv_working_cost = {}
        for agv_module_name, agv_data in self.agv_data.items():
            # ===================
            # 출발 위치 판단
            # ===================
            agv_cmd_flag = True if agv_data['cmd_error_flag'] is True or agv_data['acs_cmd_flag'] is True else False
            position_list = []
            if agv_cmd_flag is True:
                # 작업 중일 경우 로딩 위치를 시작 지점으로 설정
                work_composition_list: list = agv_data['work_composition_list']
                for i in range(agv_data['work_process'], len(work_composition_list)):
                    position_list.append(work_composition_list[i])
            else:
                if len(self.agv_data[agv_module_name]["work_position"]) != 0:
                    position_list.append(self.agv_data[agv_module_name]["work_position"])

            # ===================
            # 경로 비용 계산
            # ===================
            position_list.append(unloading_position)
            if agv_data["disable_flag"] is False and agv_data["auto_mode"]:
                cost = 0
                departure_position = ""
                for i in range(len(position_list)):
                    if i != 0:
                        destination_waypoint: int | None = self.waypoint_graph.get_node_idx(departure_position)
                        arrival_waypoint: int | None = self.waypoint_graph.get_node_idx(position_list[i])
                        if destination_waypoint is not None and arrival_waypoint is not None:
                            path: list | None = self.waypoint_graph.lpa_star(None, destination_waypoint, arrival_waypoint,False,False)
                            if path is not None:
                                # 경로가 있다면 비용 가져오기
                                cost += self.waypoint_graph.get_path_cost(path, False)
                    departure_position = position_list[i]

                if cost != 0:
                    # 비용이 0일 경우 AGV가 출발 가능한 위치가 아닌것으로 판단
                    agv_working_cost[agv_module_name] = cost

        working_agv_module_name = None
        min_cost = float('inf')
        for agv_module_name, cost in agv_working_cost.items():
            if cost < min_cost:
                # 최소 비용보다 낮은 비용이리면
                working_agv_module_name = agv_module_name
                min_cost = cost
        return working_agv_module_name

    # 명령 정지 설정
    def set_cmd_stop(self, cmd_data: dict):
        module_name: str = cmd_data['module_name']
        agv_work_data: AgvWorkList | None = self.agv_data[module_name].get('agv_work_data')
        if agv_work_data is not None:
            agv_work_list_idx: int = agv_work_data.idx
            if self.agv_data[module_name]['acs_cmd_flag'] is True:
                # 명령 수행 중이라면
                self.set_cmd_error(module_name, agv_work_list_idx, 8)  # 명령 정지로 인한 일시정지 코드 설정
            self.logger.info(f"[명령 정지] [{module_name}] {agv_work_list_idx} 항목을 정지합니다.")
        self.set_cmd_pause(module_name)

        cmd_data: dict = {
            "type": "response_cmd",
            "data": {
                "type": "cmd_stop",
                "working_id": cmd_data.get('working_id', 0),
                "data": {
                    "flag": True,
                    "msg": ""
                }
            }
        }
        self.cmd_send_data_queue.put(cmd_data)
        self.send_event(module_name, "warring", "명령 정지")

    # 명령 에러 설정
    def set_cmd_error(self, module_name: str, agv_work_list_idx: int, error_code: int):
        # 에러 업데이트
        self.agv_data[module_name]['cmd_error_flag'] = True
        error_description: str = self.error_description_list.get(error_code, "알 수 없음")
        try:
            set_agv_work_error(self.db, agv_work_list_idx=agv_work_list_idx, error_code=error_code)
            self.logger.info(f"[명령 오류] [{module_name}] {agv_work_list_idx} 항목에 오류가 발생하였습니다. 오류 코드: {error_code} ({error_description})")
            self.logger.info(f"[명령 오류] [{module_name}] {agv_work_list_idx} 항목을 수정하였습니다.")
        except Exception as e:
            self.logger.info(f"[명령 오류] [{module_name}] {agv_work_list_idx} 항목에 수정 중 예외가 발생하였습니다. 예외 메시지: {traceback.format_exc()}")

        # 명령 정지
        self.set_cmd_pause(module_name)
        self.agv_data[module_name]['acs_cmd_flag'] = False
        self.agv_data[module_name]['error_code'] = error_code

        self.send_event(module_name, "error", "명령 오류 발생!", f"오류 코드: {error_code} ({error_description})")

    # 명령 재시작 설정
    def set_cmd_restart(self, cmd_data: dict):
        module_name: str = cmd_data['module_name']

        log_msg: str = f'명령 재시작 명령이 들어왔습니다.'
        # 작업 목록 가져오기
        try:
            work_list = get_agv_work_list(self.db, module_name)
        except Exception:
            work_list = []

        success_flag = False
        response_msg = ""
        if len(work_list) > 0:
            # 작업이 1개 이상 있을 경우
            error_flag = work_list[0].error_flag  # 에러 여부

            if self.agv_data[module_name]['acs_cmd_flag'] is True:
                log_msg += '(현재 해당 AGV가 명령 수행 중이라 명령 재시작을 할 수 없습니다.)'
                response_msg = "현재 해당 AGV가 작업 중입니다"
            elif self.agv_data[module_name]['cmd_error_flag'] is False or error_flag is False:
                log_msg += '(현재 해당 AGV 의 작업에 오류가 발생하지않아 명령 재 시작을 할 수 없습니다.)'
                response_msg = "현재 해당 AGV의 작업에 오류가 발생하지않았습니다"
            else:
                agv_work_data: AgvWorkList = self.agv_data[module_name]['agv_work_data']
                home_return_flag = False
                if agv_work_data is not None:
                    work_idx: int = agv_work_data.work_idx
                    work_info: WorkInfoList | None = self.work_info_list.get(work_idx)
                    home_return_flag = work_info.home_return_flag

                if home_return_flag is True:
                    log_msg += '(복귀 작업은 재 시작이 불가능합니다.)'
                    response_msg = "복귀 작업은 재 시작이 불가능합니다"
                else:
                    self.agv_data[module_name]['work_restart'] = True
                    success_flag = True
        else:
            log_msg += '(현재 해당 AGV 의 작업 리스트가 없습니다.)'
            response_msg = "현재 해당 AGV의 작업 목록이 없습니다"
        self.logger.info(f"[명령 재시작] [{module_name}] {log_msg}")

        cmd_data: dict = {
            "type": "response_cmd",
            "data": {
                "type": "cmd_restart",
                "working_id": cmd_data.get('working_id', 0),
                "data": {
                    "flag": success_flag,
                    "msg": response_msg
                }
            }
        }
        self.cmd_send_data_queue.put(cmd_data)

    # 명령 일시정지 설정
    def set_cmd_pause(self, module_name: str):
        self.agv_data[module_name]['work_start_time'] = self.now_time
        self.set_agv_cmd_status(module_name, False)

        # 명령 정지 로그
        self.logger.info(f"[명령 정지] [{module_name}]에게 정지 명령을 보냅니다.")
        self.send_agv_cmd(module_name)  # 명령 정지 보내기

        # 명령 비상정지 해제
        self.set_cmd_emergency(module_name, False)

    # 명령 삭제
    def set_cmd_delete(self, cmd_data: dict):
        module_name: str = cmd_data['module_name']
        agv_work_list_idx: int = cmd_data.get('idx')
        agv_work_data: AgvWorkList | None = self.agv_data[module_name].get('agv_work_data')

        success_flag = True
        response_msg = ""
        if agv_work_list_idx is not None:
            if agv_work_data is not None:
                if agv_work_list_idx == agv_work_data.idx:
                    # 현재 작업 중인 명령과 삭제할 명령이 동일 한 경우 명령 정지
                    self.set_cmd_error(module_name, agv_work_list_idx, 8)
                    self.agv_work_data_clear(module_name)
                self.agv_data[module_name]['cmd_error_flag'] = False

            # DB 업데이트
            set_agv_work_complete(self.db, agv_work_list_idx, complete_flag=-1)
            self.logger.info(f"[명령 삭제] [{module_name}] {agv_work_list_idx} 항목을 삭제합니다.")
        else:
            success_flag = False
            response_msg = "요청 데이터가 없습니다"

        cmd_data: dict = {
            "type": "response_cmd",
            "data": {
                "type": "cmd_delete",
                "working_id": cmd_data.get('working_id', 0),
                "data": {
                    "flag": success_flag,
                    "msg": response_msg
                }
            }

        }
        self.cmd_send_data_queue.put(cmd_data)
        self.send_event(module_name, "warring", f"{agv_work_list_idx} 항목 명령 삭제")

    # AGV 작업 데이터 초기화
    def agv_work_data_clear(self, module_name, all_flag=True):
        if all_flag is True:
            self.agv_data[module_name]["work_name"] = ""
            self.agv_data[module_name]["work_position"] = ""
            self.agv_data[module_name]['work_composition_list'].clear()
            self.agv_data[module_name]['cmd_composition_list'].clear()
            self.agv_data[module_name]['cmd_path_list'].clear()
            self.agv_data[module_name]['cmd_agv_collision_list'].clear()
            self.agv_data[module_name]['work_process'] = 0
            self.agv_data[module_name]['cmd_process'] = 0

        if len(self.agv_data[module_name]["temp_nodes"]) != 0:
            # 임시 노드가 있을 경우 클리어
            for node_name in self.agv_data[module_name]["temp_nodes"].get("node", []):
                self.waypoint_graph.remove_node(node_name)
            self.waypoint_graph.remove_edge(self.agv_data[module_name]["temp_nodes"].get("edge", []))
            self.agv_data[module_name]["temp_nodes"].clear()

        # 신호 all 초기화
        cmd_data: dict = {
            "type": "working_sgn_data_all_clear",
            "module_name": module_name
        }
        self.cmd_send_data_queue.put(cmd_data)

    # 배터리 무시 설정
    def set_bat_ignore(self, cmd_data: dict):
        module_name: str = cmd_data['module_name']
        bat_ignore_flag: bool = cmd_data.get('flag', False)
        self.agv_data[module_name]['bat_ignore'] = bat_ignore_flag

    # 명령 보내기
    def send_agv_cmd(self, module_name: str, cmd_flag: bool = False, command_data=None):
        if command_data is None:
            command_data = {}
        error_flag: bool = self.agv_data[module_name]['cmd_error_flag']
        command_data["error_flag"] = error_flag

        if cmd_flag is True or error_flag is True:
            cmd_type = command_data.get("cmd_type", 0)
            work_process = self.agv_data[module_name]['work_process']
            cmd_process = self.agv_data[module_name]['cmd_process']
        else:
            # 명령 완료 혹은 삭제인 경우
            cmd_type = 0
            work_process = 0
            cmd_process = 0

        now_x_axis: float = self.agv_status[module_name]['x_axis']
        now_y_axis: float = self.agv_status[module_name]['y_axis']
        now_angle: float = self.agv_status[module_name]['angle']
        if 1 <= cmd_type <= 2:
            if command_data.get("A") == 0.01:
                # 각도가 0.01로 할 경우 현재 각도로 설정
                command_data["A"] = now_angle

        work_position = self.agv_data[module_name]["work_position"]
        cmd_data: dict = {
            "type": "send",
            'module_name': module_name,
            'data': {
                "command": {
                    'move': int(cmd_flag),
                    'type': cmd_type,
                    'work_no': work_process,
                    'number': cmd_process,
                    'command_data': command_data,
                    'work_name': self.agv_data[module_name]["work_name"],
                    "work_position": self.waypoint_graph.get_node_display(work_position),
                    "wait_flag": self.agv_data[module_name]["wait_flag"],
                    "wait_reason": self.agv_data[module_name]["wait_reason"]
                }
            }
        }
        self.cmd_send_data_queue.put(cmd_data)
        self.logger.info(f"[작업 명령] 작업 명령을 보냅니다. 명령 데이터: {cmd_data}")

        cmd_data: dict = {
            "type": "working_position_data",
            'module_name': module_name,
            'data': self.agv_data[module_name]['work_composition_list'][self.agv_data[module_name]['work_process'] - 1:]
        }
        self.cmd_send_data_queue.put(cmd_data)

    # 충전 설정 보내기
    def send_set_charge(self, module_name: str, flag: bool = True):
        cmd_data: dict = {
            "type": "send",
            'module_name': module_name,
            'data': {
                "cmd_charge": flag
            }
        }
        self.cmd_send_data_queue.put(cmd_data)

    # AGV 명령 상태 설정
    def set_agv_cmd_status(self, module_name: str, acs_cmd_flag: bool = True):
        self.agv_data[module_name]['acs_cmd_flag'] = acs_cmd_flag
        self.agv_data[module_name]['wait_flag'] = False
        self.agv_data[module_name]['reach_flag'] = False
        self.agv_data[module_name]['work_restart'] = False
        self.agv_data[module_name]['work_flag'] = False
        self.agv_data[module_name]['init_flag'] = False
        self.agv_data[module_name]['pre_working_sgn_flag'] = False
        self.agv_data[module_name]['interlock_ignore'] = False
        self.agv_data[module_name]['interlock_check_flag'] = False
        self.agv_data[module_name]['wait_position_flag'] = False
        if self.agv_data[module_name]['work_restart_flag'] is False:
            self.agv_data[module_name]['work_restart_count'] = 0
        self.agv_data[module_name]['work_restart_flag'] = False

        if acs_cmd_flag is True:
            # 명령 수행이 참일 경우 작업 시간 갱신
            self.agv_data[module_name]['work_start_time'] = datetime.datetime.now()

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
        self.cmd_send_data_queue.put(cmd_data)

# 명령 프로세스 동작
async def run_command_process(cmd_send_data_queue: mp.Queue, cmd_recv_data_queue: mp.Queue,
                              cmd_logger: Logger | None, stop_event: mp.Event):
    command_server_process = CommandServer(cmd_send_data_queue, cmd_recv_data_queue,
                                           cmd_logger, stop_event)
    task_list = [
        asyncio.create_task(command_server_process.run_cmd_process()),
        asyncio.create_task(command_server_process.cmd_queue_recv_process()),
        asyncio.create_task(command_server_process.collision_process()),
        asyncio.create_task(command_server_process.update_process())
    ]
    for task_item in task_list:
        await task_item


# 명령 서버 시작
def start_command_server(cmd_send_data_queue, cmd_recv_data_queue, stop_event):
    cmd_logger = get_logger("command_server", stop_event=stop_event)
    try:
        asyncio.run(run_command_process(cmd_send_data_queue, cmd_recv_data_queue, cmd_logger, stop_event))
    except Exception as e:
        cmd_logger.warning(f"예외 발생 {traceback.format_exc()}")
        if stop_event.is_set() is False:
            stop_event.set()
        send_kill_data = {
            "type": "exit"
        }
        cmd_send_data_queue.put(send_kill_data)
        cmd_recv_data_queue.put(send_kill_data)
