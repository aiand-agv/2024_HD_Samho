# AGV 데이터
import copy
import datetime
import traceback

import orjson
from sqlalchemy.orm import Session

from src.api_server.domain.acs_main.main_parameter import agv_module_name_description, motor_description, \
    status_description, section_description, system_module_name_parameter, menu_list, agv_module_number, module_description
from src.database.curd import get_agv_work_list, get_all_agv_work_list, get_work_info, \
    get_work_composition_list, get_cmd_error_description, get_agv_search_work_list, get_all_agv_search_work_list
from src.database.database import get_db
from src.main_server.module.cofigparser import get_configparser
from src.main_server.module.collection_of_functions import update_dict


# 상태 데이터 변환 (숫자, bool 외 string으로 변환)
def change_status_data(status_data):
    if type(status_data) in [int, float, bool]:
        return status_data
    else:
        return str(status_data)


class WorkListData:
    def __init__(self):
        self.update_time = datetime.datetime.now() - datetime.timedelta(seconds=30)
        self.error_description_list: dict = {}
        self.work_info_list: dict = {}
        self.work_composition_list: dict = {}
        self.work_position_display: dict = {}
        self.get_update_data()

    # 30초 간격으로 데이터 업데이트
    def get_update_data(self):
        now_time: datetime.datetime = datetime.datetime.now()
        if now_time - self.update_time >= datetime.timedelta(seconds=30):
            db = next(get_db())
            self.update_error_description(db)  # 오류 설명 갱신
            self.update_work_info_list(db)  # 작업 정보 리스트 갱신
            self.update_work_composition_list(db)  # 작업 구성 리스트 갱신
            self.update_time = now_time
            db.close()

    # 오류 설명 갱신
    def update_error_description(self, db: Session):
        error_list_data: dict = {}
        error_description_list: list = get_cmd_error_description(db)
        for error_description in error_description_list:
            error_list_data[error_description.idx] = error_description.description
        self.error_description_list.update(error_list_data)

    # 작업 정보 리스트 갱신
    def update_work_info_list(self, db: Session):
        work_info_data: dict = {}
        work_info_list: list = get_work_info(db)
        for work_info in work_info_list:
            try:
                work_info.work_composition = orjson.loads(work_info.work_composition)
            except:
                if type(work_info.work_composition) is list:
                    pass
                else:
                    work_info.work_composition = []
            work_info_data[work_info.idx] = work_info
        self.work_info_list.update(work_info_data)

    # 작업 구성 리스트 갱신
    def update_work_composition_list(self, db):
        work_composition_list: list = get_work_composition_list(db)
        work_composition_dict: dict = {}
        for work_composition in work_composition_list:
            work_composition_dict[work_composition.idx] = work_composition
        self.work_composition_list.update(work_composition_dict)

    # 작업 리스트 가져오기
    def get_work_list(self, db: Session, module_name=None, search_flag=False, search_date=None):
        if search_flag is True:
            if module_name is None:
                work_list_datas = get_all_agv_search_work_list(db, search_date)
            else:
                work_list_datas = get_agv_search_work_list(db, module_name, search_date)
        else:
            if module_name is None:
                work_list_datas = get_all_agv_work_list(db)
            else:
                work_list_datas = get_agv_work_list(db, module_name)

        return_list = []
        idx = 1
        working_flag = False  # 작업 중 여부

        for work_list_data in work_list_datas:
            agv_no: str = work_list_data.agv_module_name[4:]

            # 작업 이름 / 로딩 & 언로딩 위치 가져오기
            work_info_data = self.work_info_list.get(work_list_data.work_idx)

            # 작업 이름 설정
            if work_info_data is None:
                work_name: str = f"{work_list_data.work_idx}번 작업"
            else:
                work_name: str = work_info_data.work_name

            # 배출 위치 설정
            if work_list_data.unloading_position_display == "" or work_list_data.unloading_position_display is None:
                unloading_position: str = "-"
            else:
                unloading_position: str = work_list_data.unloading_position_display

            # 공급 위치 설정
            if work_list_data.loading_position_display == "" or work_list_data.loading_position_display is None:
                loading_position: str = "-"
            else:
                loading_position: str = work_list_data.loading_position_display

            # AGV 경로 설정
            try:
                cmd_path_list: list = orjson.loads(work_list_data.cmd_path_list)
            except:
                print(traceback.format_exc())
                cmd_path_list: list = []

            all_count: int = 0
            now_count: int = 0
            work_count: int = len(cmd_path_list)
            cmd_count: int = 0
            for i in range(len(cmd_path_list)):
                cmd_len: int = len(cmd_path_list[i])
                if i <= work_list_data.work_process:
                    if i == work_list_data.work_process:
                        cmd_count = cmd_len
                        now_count += min(cmd_len, work_list_data.cmd_process)
                    else:
                        now_count += cmd_len
                all_count += cmd_len
            work_status_percent: float = (now_count / all_count) * 100

            work_status = "대기 중"
            if work_list_data.complete_flag == -1:
                work_status = "작업 삭제"
            elif work_list_data.complete_flag == 1:
                work_status = "작업 완료"
            elif work_list_data.error_flag is False and work_list_data.work_process != 0:
                working_flag = True
                work_status = "작업 중"
            elif work_list_data.error_flag is True:
                work_status = "작업 정지"

            data_dict = {
                "idx": idx,
                "db_idx": work_list_data.idx,
                "recv_time": work_list_data.received_time,
                "agv_no": agv_no,
                "work_name": work_name,
                "unloading_position": unloading_position,
                "loading_position": loading_position,
                "work_status": {
                    "percent": round(work_status_percent, 1),
                    "work_process": work_list_data.work_process,
                    "work_count": work_count,
                    "cmd_process": work_list_data.cmd_process,
                    "cmd_count": cmd_count,
                    "status": work_status
                },
                "auto_flag": work_list_data.auto_flag,
                "error_status": {
                    "flag": work_list_data.error_flag,
                    "code": work_list_data.error_code,
                    "description": self.error_description_list.get(work_list_data.error_code, "알 수 없음")
                }
            }
            idx += 1
            return_list.append(data_dict)
        return working_flag, return_list


# =================================
# AGV 모니터링 관련
# =================================
# AGV 제품 감지 가져오기
def get_agv_product_detect(data):
    if data is not None:
        pallet_detect = data.get("pallet_detect")
        if data.get("pallet_detect") is not None:
            return pallet_detect
    return None


# AGV 맵 위치 옵션
def get_agv_map_option(agv_module_name):
    if agv_module_name == 'agv_1':
        map_x_axis_1, map_y_axis_1 = (0.1275754716387745, -0.319266875966772)
        map_x_axis_2, map_y_axis_2 = (0.7141113281250001, 0.13732897007314554)
        agv_x_axis_1, agv_y_axis_1 = (13.848760604858398, -4.8555707931518555)
        agv_x_axis_2, agv_y_axis_2 = (9.035820007324219, -8.620009422302246)

        axis_reverse = False
        if axis_reverse is True:
            agv_x_axis_1, agv_x_axis_2, agv_y_axis_1, agv_y_axis_2 = agv_y_axis_1, agv_y_axis_2, agv_x_axis_1, agv_x_axis_2

        return {
            "x_scale": 1 if agv_x_axis_1 == agv_x_axis_2 or map_x_axis_1 == map_x_axis_2 else (map_x_axis_1 - map_x_axis_2) / (agv_x_axis_1 - agv_x_axis_2),
            "y_scale": 1 if agv_y_axis_1 == agv_y_axis_2 or map_y_axis_1 == map_y_axis_2 else (map_y_axis_1 - map_y_axis_2) / (agv_y_axis_1 - agv_y_axis_2),
            "map_point": [map_x_axis_1, map_y_axis_1],
            "agv_point": [agv_x_axis_1, agv_y_axis_1],
            "angle_offset": 180,
            "angle_scale": -1,
            "axis_reverse": axis_reverse
        }
    elif agv_module_name == 'agv_2':
        map_x_axis_1, map_y_axis_1 = (0.6866455078125001, -0.8678867310885294)
        map_x_axis_2, map_y_axis_2 = (0.5438232421875001, -0.5108574890167433)
        agv_x_axis_1, agv_y_axis_1 = (-0.8747264742851257, -1.8594112396240234)
        agv_x_axis_2, agv_y_axis_2 = (-1.8525959253311157, 1.539440631866455)

        axis_reverse = False
        if axis_reverse is True:
            agv_x_axis_1, agv_x_axis_2, agv_y_axis_1, agv_y_axis_2 = agv_y_axis_1, agv_y_axis_2, agv_x_axis_1, agv_x_axis_2

        return {
            "x_scale": 1 if agv_x_axis_1 == agv_x_axis_2 or map_x_axis_1 == map_x_axis_2 else (map_x_axis_1 - map_x_axis_2) / (agv_x_axis_1 - agv_x_axis_2),
            "y_scale": 1 if agv_y_axis_1 == agv_y_axis_2 or map_y_axis_1 == map_y_axis_2 else (map_y_axis_1 - map_y_axis_2) / (agv_y_axis_1 - agv_y_axis_2),
            "map_point": [map_x_axis_1, map_y_axis_1],
            "agv_point": [agv_x_axis_1, agv_y_axis_1],
            "angle_offset": 0,
            "angle_scale": -1,
            "axis_reverse": axis_reverse
        }


class AgvData:
    def __init__(self):
        self.agv_recv_data: dict = {}
        self.agv_data: dict = {}
        self.motor_info_dict: dict = {}
        self.updated_agv_data: dict = {}
        self.error_list_data: dict = {}
        for agv_module_name, agv_module_name_name in agv_module_name_description.items():
            self.agv_data[agv_module_name] = {
                "module_name": agv_module_name,
                "name": agv_module_name_name,
                "menu_list": menu_list.get(agv_module_name, []),
                "map_option": get_agv_map_option(agv_module_name),
                "number": agv_module_number.get(agv_module_name, 0),
                "connect": False,
                "disable": False,
                "auto_mode": True,
                # "bat_soc": 82.1 + round(agv_module_number.get(agv_module_name, 0)*3.2),
                # "x_axis": 0.0,
                # "y_axis": 0.0,
                # "angle": 0.0,
                # "cmd_work_position": "대기 장소",
                # "module_description": module_description
            }
            self.motor_info_dict[agv_module_name] = {}
            self.error_list_data[agv_module_name] = {}

        #
        # self.agv_data["agv_1"].update({
        #     "connect": True,
        #     "bat_soc": 81.8,
        #     "charge_flag": True,
        #     "cmd_work_position": "대기 위치"
        # })
        # self.agv_data["agv_2"].update({
        #     "connect": True,
        #     "bat_soc": 81.4,
        #     "cmd_work_position": "대기 위치"
        # })


        self.update_time: datetime.datetime = datetime.datetime.now()

    # AGV 업데이트 데이터 가져오기
    def get_update_agv_data(self):
        now_time: datetime.datetime = datetime.datetime.now()
        if now_time - self.update_time >= datetime.timedelta(seconds=1):
            return_update_data = {}
            for agv_module_name, agv_data in self.updated_agv_data.items():
                if len(agv_data) != 0:
                    return_update_data[agv_module_name] = agv_data
            self.updated_agv_data.clear()
            self.update_time = now_time
            return return_update_data

    # AGV 데이터 업데이트
    def update_agv_data(self, agv_module_name, new_data):
        agv_update_data: dict = self.update_check_agv_data(agv_module_name, new_data)
        if len(agv_update_data) != 0:
            if self.updated_agv_data.get(agv_module_name) is None:
                self.updated_agv_data[agv_module_name] = {}
            self.updated_agv_data[agv_module_name].update(agv_update_data)
            self.agv_data[agv_module_name].update(agv_update_data)

    # AGV 데이터 업데이트 확인
    def update_check_agv_data(self, agv_module_name, new_data):
        agv_update_data = {}
        if self.agv_data.get(agv_module_name) is not None:
            agv_state = new_data.get("agv_state", {})
            cmd_info = new_data.get("cmd_info", {})
            motor_info = new_data.get("motor_info", {})
            digital_input = new_data.get("digital_input")
            error_data = new_data.get("error_data")
            update_dict(self.motor_info_dict[agv_module_name], motor_info)
            # self.motor_info_dict[agv_module_name].update(motor_info)

            # 모터 정보 가져오기 (구동 타입 입력)
            movement_type_dict: dict = {}
            for motor_name, motor_data in self.motor_info_dict[agv_module_name].items():
                motor_description_info = motor_description.get(motor_name)
                motor_cmd = motor_data.get('cmd')
                if motor_description_info is not None and motor_cmd is not None and motor_cmd != 0:
                    motor_explain = motor_description_info.get("explain", motor_name)
                    plus_name = motor_description_info.get("plus")
                    minus_name = motor_description_info.get("minus")
                    add_explain = plus_name if motor_cmd > 0 else minus_name
                    movement_type_dict[motor_explain] = add_explain
            movement_type = ""
            for motor_explain, add_explain in movement_type_dict.items():
                if movement_type != "":
                    movement_type += " & "
                movement_type += motor_explain + ('' if add_explain is None else f" {add_explain}")

            if self.agv_data[agv_module_name].get("movement_type") != movement_type:
                agv_update_data["movement_type"] = movement_type

            for data_name, data_value in new_data.items():
                if type(data_value) is not dict:
                    # 값 타입이 딕셔너리가 아니라면 데이터 갱신
                    agv_update_data[data_name] = data_value

            product_detect = get_agv_product_detect(digital_input)
            if product_detect is not None:
                agv_update_data["product_detect"] = product_detect

            if error_data is not None and len(error_data) != 0:
                update_dict(self.error_list_data[agv_module_name], error_data)

            # 에러 리스트 변경 여부
            send_error_list = []
            for module_name, connect_flag in self.error_list_data[agv_module_name].get("connect", {}).items():
                if connect_flag is True:
                    # 연결 해제 됨
                    send_error_list.append(f"{module_description.get(module_name, module_name)} 연결 해제 됨")

            for module_name, error_flag in self.error_list_data[agv_module_name].get("error_flag", {}).items():
                if error_flag is True:
                    # 비트 알람 에러
                    error_text = self.error_list_data[agv_module_name].get("error_text", {}).get(module_name, '')
                    send_error_list.append(f"{module_description.get(module_name, module_name)} {error_text}")
            error_list_str = ", ".join(send_error_list)

            if self.agv_data[agv_module_name].get("error_data") != error_list_str:
                agv_update_data["error_data"] = error_list_str

            agv_update_data.update(agv_state)
            agv_update_data.update(cmd_info)
        return agv_update_data

    # AGV 데이터 가져오기
    def get_agv_data(self):
        return self.agv_data

    # AGV 인지 확인
    def is_module_name_agv(self, module_name):
        return True if self.agv_data.get(module_name) is not None else False

    # AGV 자동 모드 설정
    def set_agv_auto_mode(self, agv_module_name, flag):
        if self.agv_data.get(agv_module_name) is not None:
            if self.updated_agv_data.get(agv_module_name) is None:
                self.updated_agv_data[agv_module_name] = {}
            self.agv_data[agv_module_name]['auto_mode'] = flag
            self.updated_agv_data[agv_module_name]['auto_mode'] = flag


class AcsData:
    def __init__(self):
        self.acs_data: dict = {
            "name": "ACS",
            "title": "이동 용접 로봇 제어 시스템",
            "menu_list": menu_list.get("acs", []),
            "acs_emergency_stop": False
        }
        self.send_data: dict = {}
        self.update_time: datetime.datetime = datetime.datetime.now()

    # ACS 데이터 가져오기
    def get_acs_data(self):
        return self.acs_data

    # ACS 업데이트 데이터 가져오기
    def get_update_acs_data(self):
        now_time: datetime.datetime = datetime.datetime.now()
        if now_time - self.update_time >= datetime.timedelta(seconds=1):
            send_data_dict = {}
            for data_key, data_value in self.acs_data.items():
                if self.send_data.get(data_key) != data_value:
                    self.send_data[data_key] = data_value
                    send_data_dict[data_key] = data_value
            self.update_time = now_time
            return send_data_dict

    def set_acs_emergency_stop(self, flag: bool):
        self.acs_data["acs_emergency_stop"] = flag

#############################################################################################
# 시스템 상태 관련 내용
#############################################################################################
# 시스템 데이터
class SystemData:
    def __init__(self):
        self.system_data: dict = {}
        for system_module_name, system_module_name_name in system_module_name_parameter.items():
            self.system_data[system_module_name] = {
                "module_name": system_module_name,
                "name": system_module_name_name,
                "menu_list": menu_list.get(system_module_name, [])
            }

        self.updated_system_data: dict = {}
        self.update_time: datetime.datetime = datetime.datetime.now()

    # 시스템 업데이트 데이터 가져오기
    def get_update_system_data(self):
        now_time: datetime.datetime = datetime.datetime.now()
        if now_time - self.update_time >= datetime.timedelta(seconds=1):
            return_update_data = {}
            for system_module_name, system_data in self.updated_system_data.items():
                if len(system_data) != 0:
                    return_update_data[system_module_name] = system_data
            self.updated_system_data.clear()
            self.update_time = now_time
            return return_update_data

    # 시스템 데이터 업데이트
    def update_system_data(self, system_module_name, new_data):
        system_update_data: dict = {}
        if self.system_data.get(system_module_name) is not None:
            for data_key, data_value in new_data.items():
                if type(data_value) is dict:
                    new_data = {}
                    for _data_key, _data_value in data_value.items():
                        new_data[f"{data_key}_{_data_key}"] = _data_value
                    self.system_data[system_module_name].update(new_data)
                    system_update_data.update(new_data)
                else:
                    self.system_data[system_module_name][data_key] = data_value
                    system_update_data.update({data_key: data_value})

        if len(system_update_data) != 0:
            if self.updated_system_data.get(system_module_name) is None:
                self.updated_system_data[system_module_name] = {}
            self.updated_system_data[system_module_name].update(system_update_data)
            self.system_data[system_module_name].update(system_update_data)

    # AGV 데이터 가져오기
    def get_system_data(self):
        return self.system_data

# =================================
# 상태 모니터링 관련
# =================================
# 상태 모니터링 타이틀 가져오기
def get_status_monitoring_title(module_name):
    module_description_text = agv_module_name_description.get(module_name)
    if module_description_text is None:
        module_description_text = system_module_name_parameter.get(module_name, module_name)
    return f"{module_description_text} 상태 모니터링"


# 상태 데이터 가져오기
def get_status_monitoring_description_data():
    status_description_data = {}
    for module_name, module_data_info in status_description.items():
        status_description_data[module_name] = {}
        for data_name, data_info in module_data_info.items():
            set_status_monitoring_description_data(status_description_data, module_name, data_name, data_info)
    return status_description_data


# 상태 데이터 설정
def set_status_monitoring_description_data(status_description_data, module_name, data_name, data_value, data_key=None):
    if type(data_value) is dict and data_value.get("explain") is None:
        for _data_name, _data_value in data_value.items():
            if data_key is None:
                key_name = f"{data_name}"
            else:
                key_name = f"{data_key}_{data_name}"
            set_status_monitoring_description_data(status_description_data, module_name, _data_name, _data_value, key_name)
    else:
        if data_key is not None:
            key_name = f"{data_key}_{data_name}"
        else:
            key_name = data_name

        section = data_value.get("section", "N/A")
        explain = data_value.get("explain", "알 수 없음")
        value = data_value.get("value", 0)
        address = data_value.get("address")

        if status_description_data[module_name].get(section) is None:
            # 섹션이 존재하지 않다면 섹션 정보 추가
            section_info = section_description.get(section)
            if section_info is None:
                # 섹션 정보가 없는데 "recv" "send"라면 섹션 정보 추가
                section_type = "column"
                module_name_name = agv_module_name_description.get(module_name)
                if module_name_name is None:
                    module_name_name = system_module_name_parameter.get(module_name, module_name)
                if section == "recv":
                    section_name = f"{module_name_name} ▶ ACS"
                elif section == "send":
                    section_name = f"ACS ▶ {module_name_name}"
                else:
                    section_name = section
            else:
                section_name = section_info.get("title", section)
                section_type = section_info.get("type", "column")

            status_description_data[module_name][section] = {
                "title": section_name,
                "type": section_type,
                "data": {}
            }

        status_description_data[module_name][section]["data"][key_name] = {
            "explain": explain,  # 데이터 설명
            "contact_flag": True if type(value) is bool else False,  # 접점 여부 (접점 일 경우 스위치)
            "value": change_status_data(value)  # 값
        }
        if address is not None:
            # 주소값이 존재할 경우 주소값 넣기
            status_description_data[module_name][section]["data"][key_name]["address"] = address  # 주소값


# 상태 모니터링 데이터
class StatusMonitoringData:
    def __init__(self):
        self.status_description_data: dict = status_description
        self.status_monitoring_data: dict = get_status_monitoring_description_data()
        self.na_flag = True if get_configparser("option", "dev", "1") == "1" else False

    # 상태 모니터링 데이터 가져오기
    def get_status_monitoring_data(self, module_name):
        return self.status_monitoring_data.get(module_name, {})

    # 상태 모니터링 데이터 업데이트
    def update_status_monitoring_data(self, module_name, data):
        return_data = {
            "data": {},
            "new_status_flag": False
        }
        status_description_data = status_description.get(module_name)
        for data_name, data_value in data.items():
            if status_description_data is not None:
                # 모듈 상태 설명이 있을 경우
                self.set_update_status_monitoring_data(self.status_description_data[module_name], return_data, module_name, data_name, data_value, na_flag=self.na_flag)
        return return_data

    # 상태 모니터링 데이터 업데이트 설정
    def set_update_status_monitoring_data(self, status_description_data, return_data, module_name, data_name, data_value, data_key=None, na_flag=False):
        if type(data_value) is dict:
            for _data_name, _data_value in data_value.items():
                if data_key is None:
                    key_name = f"{data_name}"
                else:
                    key_name = f"{data_key}_{data_name}"
                self.set_update_status_monitoring_data(status_description_data.get(data_name, {}), return_data, module_name, _data_name, _data_value, key_name, na_flag=na_flag)
        else:
            status_description_info = status_description_data.get(data_name)
            if data_key is not None:
                key_name = f"{data_key}_{data_name}"
            else:
                key_name = data_name

            if type(data_value) is float:
                data_value = round(data_value, 2)
            if status_description_info is not None:
                # 해당 데이터에 대한 상태 설명 있다면
                section = status_description_info.get("section", "N/A")
                try:
                    if return_data["data"].get(section) is None:
                        return_data["data"][section] = {}
                    return_data["data"][section][key_name] = data_value
                    self.status_monitoring_data[module_name][section]["data"][key_name]["value"] = data_value
                except:
                    # 해당 데이터의 상태 모니터링 데이터에 없음
                    pass
            elif na_flag is True:
                # 상태 설명이 없다면 생성
                section = "N/A"
                if return_data["data"].get(section) is None:
                    return_data["data"][section] = {}
                return_data["data"][section][key_name] = data_value
                if self.status_monitoring_data[module_name].get(section) is None:
                    self.status_monitoring_data[module_name][section] = {
                        "title": "알 수 없음",
                        "type": "column",
                        "data": {}
                    }
                self.status_monitoring_data[module_name][section]["data"][key_name] = {
                    "explain": key_name,                                            # 데이터 설명
                    "contact_flag": True if type(data_value) is bool else False,    # 접점 여부 (접점 일 경우 스위치)
                    "value": data_value                                             # 값
                }
                return_data["new_status_flag"] = True
