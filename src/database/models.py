import datetime

from pymodbus.utilities import default
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, REAL, DateTime, BLOB, TEXT, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.database.database import Base



# 작업 명령 표시 리스트
class WorkCommandDisplayList(Base):
    __tablename__ = "work_command_display_list"
    __doc__ = "작업 명령 표시 리스트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    agv_list = Column(TEXT, comment="AGV 리스트")
    product = Column(TEXT, comment="제품 분류")
    unloading = Column(TEXT, comment="배출 위치")
    loading = Column(TEXT, comment="공급 위치")
    work_idx = Column(Integer, ForeignKey("work_info_list.idx"), comment="작업 번호")
    work_composition = Column(TEXT, comment="작업 구성 정보")


# ===============================================
# Command 관련 Table
# ===============================================
# 작업 정보 리스트
class WorkInfoList(Base):
    __tablename__ = "work_info_list"
    __doc__ = "작업 정보 리스트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    work_name = Column(TEXT, comment="작업 이름")
    work_composition = Column(TEXT, comment="작업 구성 리스트")
    start_idx = Column(TEXT, default="[]", comment="시작 작업 인덱스")
    unloading_idx = Column(TEXT, default="[]", comment="배출 작업 인덱스")
    loading_idx = Column(TEXT, default="[]", comment="공급 작업 인덱스")
    arrival_idx = Column(TEXT, default="[]", comment="도착(복귀) 작업 인덱스")
    home_return_flag = Column(Boolean, default=False, comment="홈 복귀 작업 여부")
    all_position_flag = Column(Boolean, default=False, comment="모든 위치 작업 가능 여부")


# 작업 구성 리스트
class WorkCompositionList(Base):
    __tablename__ = "work_composition_list"
    __doc__ = "작업 구성 리스트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    composition_name = Column(TEXT, comment="구성 이름")
    fast_start_possible = Column(Boolean, default=False, comment="빠른 시작 가능 여부")
    fast_start_zone = Column(Boolean, default=False, comment="빠른 시작 가능 구역")
    driving_flag = Column(Boolean, default=False, comment="주행 작업 여부")
    command = Column(TEXT, default="{}", comment="명령 데이터")
    display = Column(TEXT, default="", comment="작업 표시")
    description = Column(TEXT, default="", comment="설명")
    # wait_flag = Column(Boolean, comment="대기 작업 여부", doc="대기 작업 여부")
    # 1번 작업 구성: 충전소 -> 언로딩 위치 (빠른 시작 가능 구역)
    # 2번 작업 구성: 언로딩 작업
    # 3번 작업 구성: 언로딩 위치 -> 로딩 위치
    # 4번 작업 구성: 로딩 작업
    # 5번 작업 구성: 로딩 위치 -> 충전소 (빠른 시작 가능)
    # 구성 이름으로 각 노드에서 해야할 작업 가져옴


# AGV 작업 리스트
class AgvWorkList(Base):
    __tablename__ = "agv_work_list"
    __doc__ = "AGV 작업 리스트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    agv_module_name = Column(TEXT, nullable=False, comment="AGV 이름")
    work_idx = Column(Integer, ForeignKey("work_info_list.idx"), comment="작업 번호")
    work_composition_list = Column(TEXT, default="[]", comment="작업 구성 리스트")
    product = Column(TEXT, default="", comment="제품 구분")
    cmd_path_list = Column(TEXT, default="[]", comment="명령 경로 리스트")
    cmd_agv_collision_list = Column(TEXT, default="[]", comment="AGV 충돌 확인 리스트")
    unloading_position_display = Column(TEXT, default="", comment="배출 장소 표시")
    loading_position_display = Column(TEXT, default="", comment="공급 장소 표시")
    work_process = Column(Integer, default=0, comment="작업 진행 번호")
    cmd_process = Column(Integer, default=0, comment="명령 진행 번호")
    error_flag = Column(Boolean, default=False, comment="오류 여부")
    error_code = Column(Integer, default=0, comment="오류 코드")
    auto_flag = Column(Boolean, default=False, comment="자동 작업 여부")
    complete_flag = Column(Integer, default=0, comment="완료 여부 (1: 정상 완료 | 0: 완료 X | -1: 명령 삭제)")
    received_time = Column(DateTime, default=datetime.datetime.now, comment="작업 수신 시간")
    start_time = Column(DateTime, nullable=True, comment="작업 시작 시간")
    end_time = Column(DateTime, nullable=True, comment="작업 종료 시간")

    cmd_composition_list = Column(TEXT, default="[]", comment="명령 구성 리스트")


# AGV 오류 리스트
class CmdErrorCodeList(Base):
    __tablename__ = "cmd_error_code_list"
    __doc__ = "자동 명령 오류 코드 리스트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    description = Column(TEXT, default="", comment="오류 설명")


# 작업 정보 리스트
class AgvHomePosition(Base):
    __tablename__ = "agv_home_position"
    __doc__ = "AGV 홈 포지션"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    agv_module_name = Column(TEXT, nullable=False, comment="AGV 이름")
    charge_flag = Column(Boolean, default=False, comment="충전 여부")
    waypoint_no = Column(Integer, default=0, comment="웨이포인트 번호")
    description = Column(TEXT, default="", comment="설명")


# 주행 웨이포인트
class WaypointDriving(Base):
    __tablename__ = "waypoint_driving"
    __doc__ = "주행 웨이포인트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    number = Column(Integer, nullable=False, comment="웨이포인트 번호")
    composition = Column(TEXT, default="", comment="구성 이름")
    name = Column(TEXT, default="", comment="웨이포인트 이름")
    command = Column(TEXT, default="{}", comment="명령 데이터")
    description = Column(TEXT, default="", comment="설명")


# 주행 웨이포인트 간선 정보
class WaypointDrivingEdge(Base):
    __tablename__ = "waypoint_driving_edge"
    __doc__ = "주행 웨이포인트 간선 정보"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    waypoint_1_no = Column(Integer, nullable=False, comment="1번 웨이포인트 번호(노드)")
    waypoint_2_no = Column(Integer, nullable=False, comment="2번 웨이포인트 번호(노드)")
    arrow = Column(TEXT, default="↔", comment="방향 표시(1←2, 1→2, 1↔2)")
    command = Column(TEXT, default="{}", comment="출발 전 명령 데이터")
    return_range = Column(TEXT, default="{}", comment="복귀 범위")
    work_zone = Column(Boolean, default=False, comment="작업 공간 여부")
    description = Column(TEXT, default="", comment="설명")


# 주행 이외 웨이포인트
class WaypointCommon(Base):
    __tablename__ = "waypoint_common"
    __doc__ = "주행 이외 웨이포인트"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    number = Column(Integer, comment="웨이포인트 번호")
    composition = Column(TEXT, default="", comment="구성 이름")
    command = Column(TEXT, default="{}", comment="명령 데이터")
    description = Column(TEXT, default="", comment="설명")


# 신호/인터락
class InterlockSignal(Base):
    __tablename__ = "interlock_signal"
    __doc__ = "신호 & 인터락"

    idx = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="index")
    module_name = Column(Integer, comment="모듈 이름")
    status_name = Column(TEXT, comment="상태 이름")
    main_name = Column(TEXT, default="", comment="데이터 메인 이름")
    sub_name = Column(TEXT, default="", comment="데이터 서브 이름 (구분 이름)")
    description = Column(TEXT, default="", comment="설명")


# ===============================================
# 기타 Table
# ===============================================
# 비밀번호
class Password(Base):
    __tablename__ = "password"

    idx = Column(Integer, primary_key=True)
    password = Column(String)


# DB 갱신
class DatabaseUpdate(Base):
    __tablename__ = "database_update"

    idx = Column(Integer, primary_key=True)
    name = Column(TEXT, default="")
    update_time = Column(DateTime, default=datetime.datetime.now, comment="업데이트 시간")


# 이벤트 리스트
class EventList(Base):
    __tablename__ = "event_list"

    idx = Column(Integer, primary_key=True, index=True)
    module_name = Column(String, nullable=True)
    error_type = Column(String, nullable=True)
    alarm = Column(String, nullable=True)
    msg = Column(String, nullable=True)
    event_date = Column(DateTime, default=datetime.datetime.now)
