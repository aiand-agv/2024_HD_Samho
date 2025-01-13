import datetime
import orjson
from sqlalchemy.orm import Session

from src.database.models import CmdErrorCodeList, AgvWorkList, WorkInfoList, AgvHomePosition, WorkCompositionList, \
    WaypointDriving, WaypointDrivingEdge, WaypointCommon, DatabaseUpdate, EventList, InterlockSignal
from src.main_server.module.collection_of_functions import json_default


# 명령 오류 설명 가져오기
def get_cmd_error_description(db: Session):
    cmd_error_description = db.query(CmdErrorCodeList).all()
    return cmd_error_description


# 명령 오류 설정
def set_agv_work_error(db: Session, agv_work_list_idx: int, error_code: int):
    agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.idx == agv_work_list_idx).first()
    if agv_work_list_data is None:
        # 해당 작업 번호가 존재하지 않다면 예외 발생
        raise Exception("해당 작업 번호가 존재하지 않습니다.")
    else:
        agv_work_list_data.error_flag = True
        agv_work_list_data.error_code = error_code
        db.add(agv_work_list_data)
        db.commit()


# 명령 완료 설정
def set_agv_work_complete(db: Session, agv_work_list_idx: int, complete_flag: int):
    agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.idx == agv_work_list_idx).first()
    if agv_work_list_data is None:
        # 해당 작업 번호가 존재하지 않다면 예외 발생
        raise Exception("해당 작업 번호가 존재하지 않습니다.")
    else:
        agv_work_list_data.complete_flag = complete_flag
        agv_work_list_data.end_time = datetime.datetime.now()
        db.add(agv_work_list_data)
        db.commit()


# 명령 시작 설정
def set_agv_work_start_time(db: Session, agv_work_list_idx: int):
    agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.idx == agv_work_list_idx).first()
    if agv_work_list_data is None:
        # 해당 작업 번호가 존재하지 않다면 예외 발생
        raise Exception("해당 작업 번호가 존재하지 않습니다.")
    else:
        agv_work_list_data.start_time = datetime.datetime.now()
        db.add(agv_work_list_data)
        db.commit()


# 명령 리스트 가져오기
def get_agv_work_list(db: Session, module_name: str):
    agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.agv_module_name == module_name, AgvWorkList.complete_flag == 0).all()
    return agv_work_list_data


# 명령 리스트 전부 가져오기
def get_all_agv_work_list(db: Session):
    agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.complete_flag == 0).all()
    return agv_work_list_data


# 명령 리스트 가져오기
def get_agv_search_work_list(db: Session, module_name: str, search_date: str):
    if search_date is None:
        agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.agv_module_name == module_name).all()
    else:
        start_time = datetime.datetime.strptime(search_date, '%Y-%m-%d')
        end_time = start_time + datetime.timedelta(days=1)
        agv_work_list_data = db.query(AgvWorkList).filter(AgvWorkList.agv_module_name == module_name, AgvWorkList.received_time >= start_time, AgvWorkList.received_time < end_time).all()
    return agv_work_list_data


# 명령 리스트 전부 가져오기
def get_all_agv_search_work_list(db: Session, search_date: str | None):
    if search_date is None:
        work_time_list = db.query(AgvWorkList).all()
    else:
        start_time = datetime.datetime.strptime(search_date, '%Y-%m-%d')
        end_time = start_time + datetime.timedelta(days=1)
        work_time_list = db.query(AgvWorkList).filter(AgvWorkList.received_time >= start_time, AgvWorkList.received_time < end_time).all()
    return work_time_list


# 중복 작업 찾기
def search_overlap_work(db: Session, work_idx: int, work_info: WorkInfoList, composition_list: list):
    overlap_work_data = db.query(AgvWorkList).filter(AgvWorkList.complete_flag == 0, AgvWorkList.work_idx == work_idx).all()
    for work_data in overlap_work_data:
        try:
            work_composition_list = orjson.loads(work_data.work_composition_list)
        except:
            work_composition_list = []

        count = 0
        overlap_count = 0
        start_idx = work_info.start_idx[-1] + 1
        for idx in range(start_idx, len(composition_list)):
            try:
                add_work_position = composition_list[idx]
                work_position = work_composition_list[idx]
                count += 1
                if add_work_position == work_position:
                    overlap_count += 1
            except:
                pass
        if overlap_count == count and count != 0:
            # 겹치는 개수랑 작업개수랑 동일한 경우 중복된다고 판단
            return True
    return False


# 전체 구성 리스트 가져오기 (위치 가져오기)
def get_all_composition_list(db: Session):
    all_work_data = db.query(AgvWorkList).filter(AgvWorkList.complete_flag == 0).all()

    all_composition_list = {}
    for work_data in all_work_data:
        try:
            work_composition_list = orjson.loads(work_data.work_composition_list)
        except:
            work_composition_list = []

        for index in range(len(work_composition_list)):
            try:
                position = work_composition_list[index]
                work_process = work_data.work_process - 1
                if position not in "charge":
                    # 지나간 곳은 False
                    all_composition_list[position] = True if index >= work_process else False
            except:
                pass
    return all_composition_list


# AGV 작업 추가
def add_agv_work(db: Session, module_name: str, work_idx: int, composition_list: list, auto_flag: bool):
    agv_work_data = AgvWorkList(
        agv_module_name=module_name,
        work_idx=work_idx,
        work_composition_list=orjson.dumps(composition_list, default=json_default).decode("utf-8"),
        auto_flag=auto_flag,
    )
    db.add(agv_work_data)
    db.commit()
    return agv_work_data.idx


# AGV 작업 업데이트
def update_agv_work(db: Session, agv_work_data: AgvWorkList):
    db.add(agv_work_data)
    db.commit()


# 작업 정보 가져오기
def get_work_info(db: Session):
    agv_work_list_data = db.query(WorkInfoList).all()
    return agv_work_list_data


# 작업 구성 리스트 가져오기
def get_work_composition_list(db: Session):
    work_composition_list = db.query(WorkCompositionList).all()
    return work_composition_list


# 인터록 & 작업 신호 가져오기
def get_interlock_signal(db: Session):
    interlock_signal_data = db.query(InterlockSignal).all()
    return interlock_signal_data


# AGV 홈 위치 가져오기
def get_agv_home_position(db: Session, module_name: str):
    agv_home_position_list = db.query(AgvHomePosition).filter(AgvHomePosition.agv_module_name == module_name).all()
    return agv_home_position_list


# 주행 웨이포인트 이름으로 가져오기
def get_waypoint_driving_name(db: Session, waypoint_name: str):
    waypoint_data = db.query(WaypointDriving).filter(WaypointDriving.name == waypoint_name).first()
    return waypoint_data


# 주행 웨이포인트 전부 가져오기
def get_all_waypoint_driving(db: Session):
    waypoint_data = db.query(WaypointDriving).all()
    return waypoint_data

# 주행 웨이포인트 가져오기
def get_waypoint_driving(db: Session, waypoint_no: int, composition_name: str = ""):
    waypoint_data = db.query(WaypointDriving).filter(
        WaypointDriving.number == waypoint_no,
        WaypointDriving.composition == composition_name
    ).first()
    return waypoint_data


# 주행 웨이포인트 간선 정보 가져오기
def get_waypoint_driving_edge(db: Session):
    waypoint_edge_data = db.query(WaypointDrivingEdge).all()
    return waypoint_edge_data


# 주행 이외 웨이포인트 가져오기
def get_waypoint_common(db: Session, waypoint_no: int, composition_name: str = ""):
    waypoint_data = db.query(WaypointCommon).filter(
        WaypointCommon.number == waypoint_no,
        WaypointCommon.composition == composition_name
    ).first()
    return waypoint_data


# DB 업데이트
def database_update(db: Session, name: str):
    database_update_data = db.query(DatabaseUpdate).filter(DatabaseUpdate.name == name).first()
    if database_update_data is None:
        database_update_data = DatabaseUpdate(
            name=name,
        )
    database_update_data.update_time = datetime.datetime.now()
    db.add(database_update_data)
    db.commit()


# DB 업데이트 정보 가져오기
def get_database_update(db: Session, name: str):
    database_update_data = db.query(DatabaseUpdate).filter(DatabaseUpdate.name == name).first()
    if database_update_data is None:
        # 정보가 없을 경우 강제 업데이트
        return True
    else:
        return False

# 이벤트 추가
def add_event(db: Session, event_data):
    event_list_data = EventList(
        module_name=event_data.get("module_name"),
        error_type=event_data.get("error_type"),
        alarm=event_data.get("alarm"),
        msg = event_data.get("msg"),
        event_date=event_data.get("date")
    )
    db.add(event_list_data)
    db.commit()


# 이벤트 보기
def search_event(db: Session, event_date: str):
    start_time = datetime.datetime.strptime(event_date, '%Y-%m-%d')
    end_time = start_time + datetime.timedelta(days=1)
    event_list_data = db.query(EventList).filter(EventList.event_date >= start_time, EventList.event_date < end_time).all()
    return event_list_data