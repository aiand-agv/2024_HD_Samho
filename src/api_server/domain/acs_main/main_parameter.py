# -*- coding: utf-8 -*-
# ===========================
# 모듈 이름 설명
# ===========================
agv_module_name_description = {
    "agv_1": "AGV 1호기",
    "agv_2": "AGV 2호기",
}

agv_module_number = {
    "agv_1": 1,
    "agv_2": 2,
}

system_module_name_parameter = {
    # "mes": "MASTER PLC"
}

# 모듈 설명
module_description = {
    "front_left": "전방 좌측 주행 모터 드라이버",
    "front_right": "전방 우측 주행 모터 드라이버",
    "rear_left": "후방 좌측 주행 모터 드라이버",
    "rear_right": "후방 우측 주행 모터 드라이버",
    "front_left_steering": "전방 좌측 조향 모터 드라이버",
    "front_right_steering": "전방 우측 조향 모터 드라이버",
    "rear_left_steering": "후방 좌측 조향 모터 드라이버",
    "rear_right_steering": "후방 우측 조향 모터 드라이버",
    "fork/y": "포크 y축 모터 드라이버",
    "ls_plc": "LS산전 PLC",
    "scanF/raw": "전방 LRF",
    "scanB/raw": "후방 LRF",
    "scanS/raw": "SLAM Lidar",
    "ecan_fork": "포크 ECAN",
    "ecan_drive": "주행 ECAN",
    "acs": "ACS",
    "tablet_joystick": "조이스틱",

    # ========== 과제 용 ==========
    "slamloc/pose": "위치 추정",
    "slamloc": "CP112 (PLC)",
}

# ===========================
# 시스템 파라미터
# ===========================
def get_menu_list(subject, btn_type, url=None, request_url=None, toggle=None, big=None, toggle_subject=None, params=None):
    menu_list_data = {
        "subject": subject,
        "type": btn_type,
    }
    if url is not None:
        menu_list_data["url"] = url
    if request_url is not None:
        menu_list_data["request_url"] = request_url
    if toggle is not None:
        menu_list_data["toggle"] = toggle
        if toggle_subject is not None:
            menu_list_data["toggle_subject"] = toggle_subject
        else:
            menu_list_data["toggle_subject"] = f"{subject} 해제"
    if big is not None:
        menu_list_data["big"] = big
    if params is not None:
        menu_list_data["params"] = params
    return menu_list_data


# AGV 메뉴 리스트 가져오기
def get_agv_menu_list(module_name):
    return [
        get_menu_list("상태 정보", "popup", f"/status/{module_name}", big=True),
        get_menu_list("AGV 작업 관리", "popup", "/work_management", big=True, params=f"?module_name={module_name}&name={agv_module_name_description.get(module_name, "module_name")}"),
        get_menu_list("날짜별 작업 보기", "popup", "/search_work_list", big=True, params=f"?module_name={module_name}&name={agv_module_name_description.get(module_name, "module_name")}"),
        get_menu_list("자동모드", "request", request_url="/set_auto_mode", toggle="auto_mode"),
        get_menu_list("비활성화", "request", request_url="/set_disable", toggle="disable"),
        get_menu_list("비상정지", "request", request_url="/emergency_stop", toggle="acs_emg_stop"),
        get_menu_list("비상모드", "request", request_url="/set_emg_mode", toggle="acs_emg_mode"),
    ]

# HMI 메뉴 리스트 가져오기
def get_hmi_menu_list(module_name):
    return [
        get_menu_list("상태 정보", "popup", f"/status/{module_name}", big=True),
        get_menu_list("AGV 호출", "check_request",  request_url=f"/call/{module_name}"),
        get_menu_list("비활성화", "request", request_url="/set_disable", toggle="disable")
    ]


# 메뉴 리스트
menu_list = {
    "mes": [
        get_menu_list("상태 정보", "popup", f"/status/mes", big=True),
        get_menu_list("비활성화", "request", request_url="/set_disable", toggle="disable")
    ],
    "loading_hmi": get_hmi_menu_list('loading_hmi'),
    "unloading_hmi": get_hmi_menu_list('unloading_hmi'),
    "assembly_buffer_hmi": get_hmi_menu_list('assembly_buffer_hmi'),
    "assembly_hmi": get_hmi_menu_list('assembly_hmi'),
    "airtightness_buffer_hmi": get_hmi_menu_list('airtightness_buffer_hmi'),
    "airtightness_hmi": get_hmi_menu_list('airtightness_hmi'),
    "loop_buffer_hmi": get_hmi_menu_list('loop_buffer_hmi'),
    "loop_hmi": get_hmi_menu_list('loop_hmi'),
    "agv_1": get_agv_menu_list("agv_1"),
    "agv_2": get_agv_menu_list("agv_2"),
    "acs": [
        get_menu_list("관리자 로그인", "popup", url="/login"),
        get_menu_list("비밀번호 변경", "popup", url="/change_password"),
        get_menu_list("AGV 작업 관리", "popup", url="/work_management", big=True),
        get_menu_list("날짜별 작업 보기", "popup", "/search_work_list", big=True),
        get_menu_list("이벤트 보기", "popup", url="/event"),
        get_menu_list("비상정지", "request", request_url="/acs_emergency_stop", toggle="acs_emergency_stop"),
    ]
}

# ===========================
# 상태 파라미터
# ===========================
# 상태(접점) 설명 만들기
def make_status_description(section, explain, value, address=None):
    return {
        "section": section,  # 섹션
        "explain": explain,  # 설명
        "value": value,       # 기본 값
        "address": address    # 주소값
    }


# AGV 상태 정보 가져오기
def get_agv_status_description(number):
    return {
        "digital_input": {
            "emergency_button": make_status_description("contact", "비상 정지 버튼", False, "DI00"),
            "bumper": make_status_description("contact", "범퍼 감지", False, "DI01"),
            "pc_off_button": make_status_description("contact", "PC OFF 버튼", False,"DI02"),
            "bumper_bypass": make_status_description("contact", "범퍼 바이패스", False,"DI03"),
            "error_reset": make_status_description("contact", "에러 리셋 버튼", False, "DI04"),
            "lift_up_limit": make_status_description("contact", "리프트 상승 리미트", False, "DI05"),
            "lift_down_limit": make_status_description("contact", "리프트 하강 리미트", False, "DI06"),
            "pallet_detect": make_status_description("contact", "전방 제품 감지", False, "DI07"),
            "pallet_detect_2": make_status_description("contact", "후방 제품 감지", False, "DI08"),
        },
        "digital_output": {
            'charge_ct': make_status_description("contact", "충전 릴레이", False, "DO00"),
            'lift_up': make_status_description("contact", "리프트 상승", False, "DO01"),
            'lift_down': make_status_description("contact", "리프트 하강", False, "DO02"),
            'horn_1': make_status_description("contact", "멜로디 1", False, "DO03"),
            'horn_2': make_status_description("contact", "멜로디 2", False, "DO04"),
            'horn_3': make_status_description("contact", "멜로디 3", False, "DO05"),
            'horn_4': make_status_description("contact", "멜로디 4", False, "DO06"),
            'lamp_red': make_status_description("contact", "적색 경광등", False, "DO07"),
            'lamp_yellow': make_status_description("contact", "황색 경광등", False, "DO08"),
            'lamp_green': make_status_description("contact", "녹색 경광등", False, "DO09"),
            'buzzer': make_status_description("contact", "부저", False, "DO10"),
            'charge_sensor': make_status_description("contact", "도킹기 포토센서", False, "DO11")
        },
        "agv_state": {
            'error_flag': make_status_description("working_status", "오류 여부", False),
            'error_text': make_status_description("working_status", "오류 리스트", {}),
            'manual_mode': make_status_description("working_status", "메뉴얼 모드 여부", False),
            'acs_emg_mode': make_status_description("working_status", "ACS 비상 모드", False),
            'cmd_emg_stop': make_status_description("working_status", "자동 명령 비상 정지", False),
            'acs_emg_stop': make_status_description("working_status", "ACS 비상 정지", False),
            'emg_stop': make_status_description("working_status", "비상 정지", False),
            'obs_emg_stop': make_status_description("working_status", "장애물 감지 정지 여부", False),
            'obs_emg_slow': make_status_description("working_status", "장애물 감지 슬로우 여부", False),
            'emg_mode': make_status_description("working_status", "비상 모드 여부", False),
            'joy_emg_mode': make_status_description("working_status", "조이스틱 비상 모드 여부", False),
            'joy_emg_stop': make_status_description("working_status", "조이스틱 비상 정지 여부", False),
            'joy_emg_safety': make_status_description("working_status", "조이스틱 비상 안전 모드 여부", False),
            'volt': make_status_description("working_status", "배터리 전압", 0.0),
            'bat_soc': make_status_description("working_status", "배터리 잔량", 0.0),
            'full_charge': make_status_description("working_status", "충전 완료", False),
            'charge_flag': make_status_description("working_status", "충전 여부", False),
            'bat_alarm_flag': make_status_description("working_status", "배터리 부족 여부", False),
            'x_axis': make_status_description("working_status", "X 축", 0.0),
            'y_axis': make_status_description("working_status", "Y 축", 0.0),
            'angle': make_status_description("working_status", "각도", 0.0)
        },
        "agv_pc_ping": make_status_description("connect", "AGV PC 핑", False, f"ip.{100 + number}"),
        "airlink_ping": make_status_description("connect", "AP 핑", False, f"ip.{200 + number}"),
        "connect": make_status_description("connect", "AGV 연결 여부", False),
        "disable": make_status_description("working_status", "비활성화 여부", False),
        'acs_to_agv_watch_dog': make_status_description("working_status", "ACS ▶ AGV 와치독", False),
        'agv_to_acs_watch_dog': make_status_description("working_status", "AGV ▶ ACS 와치독", False),
        "connect_info": {
            "front_left": make_status_description("connect", module_description.get("front_left", "front_left"), False),
            "front_right": make_status_description("connect", module_description.get("front_right", "front_right"), False),
            "rear_left": make_status_description("connect", module_description.get("rear_left", "rear_left"), False),
            "rear_right": make_status_description("connect", module_description.get("rear_right", "rear_right"), False),
            "scanF/raw": make_status_description("connect", module_description.get("scanF/raw", "scanF/raw"), False),
            "scanB/raw": make_status_description("connect", module_description.get("scanB/raw", "scanB/raw"), False),
            "ecan": make_status_description("connect", module_description.get("ecan", "ecan"), False),
            "acs": make_status_description("connect", module_description.get("acs", "acs"), False),
            "slamloc": make_status_description("connect", module_description.get("slamloc", "slamloc"), False),
            "slamloc/pose": make_status_description("connect", module_description.get("slamloc/pose", "slamloc/pose"), False),
            "tablet_joystick": make_status_description("connect", module_description.get("tablet_joystick", "tablet_joystick"), False),
        },
        "cmd_info": {
            'cmd_flag': make_status_description("cmd_info", "명령 수행 여부", False),  # 명령 수행 여부
            'cmd_start': make_status_description("cmd_info", "명령 수행 시작 여부", False),  # 명령 수행 시작 여부
            'cmd_error': make_status_description("cmd_info", "명령 에러 여부", False),  # 명령 에러 여부
            'cmd_error_type': make_status_description("cmd_info", "명령 에러 타입", 0),  # 명령 에러 타입
            'cmd_reach_flag': make_status_description("cmd_info", "명령 도달 여부", False),  # 명령 도달 여부
            'cmd_work_no': make_status_description("cmd_info", "작업 수행 번호", 0),  # 작업 번호 (도착지 번호)
            'cmd_number': make_status_description("cmd_info", "명령 수행 번호", 0),  # 명령 번호 (웨이포인트[노드] 번호)
            'cmd_work_name': make_status_description("cmd_info", "명령 작업 이름", ""),  # 명령 작업 이름
            'cmd_work_position': make_status_description("cmd_info", "명령 작업 위치", ""),  # 명령 작업 위치
            'cmd_wait_flag': make_status_description("cmd_info", "명령 대기 여부", False),  # 명령 작업 대기 여부
            'cmd_wait_reason': make_status_description("cmd_info", "명령 대기 이유", ""),  # 명령 대기 이유
            'precise_mode': make_status_description("cmd_info", "정밀 모드 여부", False),  # 정밀 모드 여부
        },
        "motor_info": {
            "front_left": {
                "cmd": make_status_description("front_left_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("front_left_motor_info", "전압(V)", 0),
                'current': make_status_description("front_left_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("front_left_motor_info", "현재 속도(RPM)", 0),
                'position': make_status_description("front_left_motor_info", "위치값", 0),
                'torque': make_status_description("front_left_motor_info", "토크", 0),
                'error_code': make_status_description("front_left_motor_info", "오류 코드", 0),
                'error_text': make_status_description("front_left_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("front_left_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("front_left_motor_info", "모터 온도", "")
                },
            },
            "front_right": {
                "cmd": make_status_description("front_right_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("front_right_motor_info", "전압(V)", 0),
                'current': make_status_description("front_right_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("front_right_motor_info", "현재 속도(RPM)", 0),
                'position': make_status_description("front_right_motor_info", "위치값", 0),
                'torque': make_status_description("front_right_motor_info", "토크", 0),
                'error_code': make_status_description("front_right_motor_info", "오류 코드", 0),
                'error_text': make_status_description("front_right_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("front_right_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("front_right_motor_info", "모터 온도", "")
                },
            },
            "rear_left": {
                "cmd": make_status_description("rear_left_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("rear_left_motor_info", "전압(V)", 0),
                'current': make_status_description("rear_left_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("rear_left_motor_info", "현재 속도(RPM)", 0),
                'position': make_status_description("rear_left_motor_info", "위치값", 0),
                'torque': make_status_description("rear_left_motor_info", "토크", 0),
                'error_code': make_status_description("rear_left_motor_info", "오류 코드", 0),
                'error_text': make_status_description("rear_left_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("rear_left_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("rear_left_motor_info", "모터 온도", "")
                },
            },
            "rear_right": {
                "cmd": make_status_description("rear_right_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("rear_right_motor_info", "전압(V)", 0),
                'current': make_status_description("rear_right_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("rear_right_motor_info", "속도(RPM)", 0),
                'position': make_status_description("rear_right_motor_info", "위치값", 0),
                'torque': make_status_description("rear_right_motor_info", "토크", 0),
                'error_code': make_status_description("rear_right_motor_info", "오류 코드", 0),
                'error_text': make_status_description("rear_right_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("rear_right_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("rear_right_motor_info", "모터 온도", "")
                },
            },
            "front_left_steering": {
                "cmd": make_status_description("front_left_steering_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("front_left_steering_motor_info", "전압(V)", 0),
                'current': make_status_description("front_left_steering_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("front_left_steering_motor_info", "현재 속도(RPM)", 0),
                'position': make_status_description("front_left_steering_motor_info", "위치값", 0),
                'torque': make_status_description("front_left_steering_motor_info", "토크", 0),
                'error_code': make_status_description("front_left_steering_motor_info", "오류 코드", 0),
                'error_text': make_status_description("front_left_steering_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("front_left_steering_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("front_left_steering_motor_info", "모터 온도", "")
                },
            },
            "front_right_steering": {
                "cmd": make_status_description("front_right_steering_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("front_right_steering_motor_info", "전압(V)", 0),
                'current': make_status_description("front_right_steering_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("front_right_steering_motor_info", "현재 속도(RPM)", 0),
                'position': make_status_description("front_right_steering_motor_info", "위치값", 0),
                'torque': make_status_description("front_right_steering_motor_info", "토크", 0),
                'error_code': make_status_description("front_right_steering_motor_info", "오류 코드", 0),
                'error_text': make_status_description("front_left_steering_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("front_right_steering_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("front_right_steering_motor_info", "모터 온도", "")
                },
            },
            "rear_left_steering": {
                "cmd": make_status_description("rear_left_steering_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("rear_left_steering_motor_info", "전압(V)", 0),
                'current': make_status_description("rear_left_steering_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("rear_left_steering_motor_info", "현재 속도(RPM)", 0),
                'position': make_status_description("rear_left_steering_motor_info", "위치값", 0),
                'torque': make_status_description("rear_left_steering_motor_info", "토크", 0),
                'error_code': make_status_description("rear_left_steering_motor_info", "오류 코드", 0),
                'error_text': make_status_description("rear_left_steering_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("rear_left_steering_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("rear_left_steering_motor_info", "모터 온도", "")
                },
            },
            "rear_right_steering": {
                "cmd": make_status_description("rear_right_steering_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("rear_right_steering_motor_info", "전압(V)", 0),
                'current': make_status_description("rear_right_steering_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("rear_right_steering_motor_info", "속도(RPM)", 0),
                'position': make_status_description("rear_right_steering_motor_info", "위치값", 0),
                'torque': make_status_description("rear_right_steering_motor_info", "토크", 0),
                'error_code': make_status_description("rear_right_steering_motor_info", "오류 코드", 0),
                'error_text': make_status_description("rear_right_steering_motor_info", "오류 정보", ""),
                'status': {
                    "inverter_temperature": make_status_description("rear_right_steering_motor_info", "인버터 온도", ""),
                    "motor_temperature": make_status_description("rear_right_steering_motor_info", "모터 온도", "")
                },
            },
            "fork/y": {
                "cmd": make_status_description("fork_y_motor_info", "속도 지령(RPM)", 0),
                'volt': make_status_description("fork_y_motor_info", "전압(V)", 0),
                'current': make_status_description("fork_y_motor_info", "전류(A)", 0),
                'speed_rpm': make_status_description("fork_y_motor_info", "속도(RPM)", 0),
                'position': make_status_description("fork_y_motor_info", "위치값", 0),
                'torque': make_status_description("fork_y_motor_info", "토크", 0),
                'error_code': make_status_description("fork_y_motor_info", "오류 코드", 0),
                'error_text': make_status_description("fork_y_motor_info", "오류 정보", ""),
                'status': make_status_description("fork_y_motor_info", "상태 코드", ""),
            },
            "fork/z": {
                "cmd": make_status_description("cylinder_motor_info", "리프트 속도 지령(UP/DOWN)", 0),
            },
            "tilting": {
                "cmd": make_status_description("cylinder_motor_info", "리프트 속도 지령(UP/DOWN)", 0),
            }
        },
        "recv_time": make_status_description("working_status", "수신 시간", "")
    }


# HMI 상태 정보 가져오기
def get_hmi_status_description(hmi_number: int, speed_door_flag: bool = False):
    hmi_status_description = {
        "hmi_status": {
            'emergency_btn': make_status_description("hmi_contact", "비상정지 버튼", False, "DI0"),
            'buzzer_off': make_status_description("hmi_contact", "부저 OFF 버튼", False, "DI1"),
            "detect": make_status_description("hmi_contact", "제품 감지", False, "DI5"),
            'lamp_red': make_status_description("hmi_contact", "적색 경광등", False, "DO4"),
            'lamp_yellow': make_status_description("hmi_contact", "황색 경광등", False, "DO5"),
            'lamp_green': make_status_description("hmi_contact", "녹색 경광등", False, "DO6"),
            'buzzer': make_status_description("hmi_contact", "부저", False, "DO7"),
        },
        'acs_to_hmi_watch_dog': make_status_description("hmi_contact", "ACS ▶ HMI 와치독", False),
        'hmi_to_acs_watch_dog': make_status_description("hmi_contact", "HMI ▶ ACS 와치독", False),
        "connect": make_status_description("hmi_connect", "HMI 연결 여부", False),
        "disable": make_status_description("hmi_connect", "비활성화 여부", False),
        "moxa_e1212_ping": make_status_description("hmi_connect", "I/O 모듈 핑", False, f"ip.{119 + hmi_number}"),
        "hmi_pc_ping": make_status_description("hmi_connect", "HMI PC 핑", False, f"ip.{109 + hmi_number}"),
        "acs_hmi_status": {
            "loading": {
                "agv": make_status_description("hmi_data", "적재지 AGV", ""),
                "status": make_status_description("hmi_data", "적재지 상태", ""),
            },
            "unloading": {
                "agv": make_status_description("hmi_data", "출하지 AGV", ""),
                "status": make_status_description("hmi_data", "출하지 상태", "")
            },
            "assembly_buffer": {
                "agv": make_status_description("hmi_data", "조립 버퍼 AGV", ""),
                "status": make_status_description("hmi_data", "조립 버퍼 상태", "")
            },
            "assembly": {
                "agv": make_status_description("hmi_data", "조립 공정 AGV", ""),
                "status": make_status_description("hmi_data", "조립 공정 상태", "")
            },
            "airtightness_buffer": {
                "agv": make_status_description("hmi_data", "기밀 버퍼 AGV", ""),
                "status": make_status_description("hmi_data", "기밀 버퍼 상태", "")
            },
            "airtightness": {
                "agv": make_status_description("hmi_data", "기밀 공정 AGV", ""),
                "status": make_status_description("hmi_data", "기밀 공정 상태", "")
            },
            "loop_buffer": {
                "agv": make_status_description("hmi_data", "루프 버퍼 AGV", ""),
                "status": make_status_description("hmi_data", "루프 버퍼 상태", "")
            },
            "loop": {
                "agv": make_status_description("hmi_data", "루프 공정 AGV", ""),
                "status": make_status_description("hmi_data", "루프 공정 상태", "")
            },
            "charge": {
                "agv_1": make_status_description("hmi_data", "충전소 1호기 상태", ""),
                "agv_2": make_status_description("hmi_data", "충전소 2호기 상태", "")
            },
        },
        "work_unsatisfied": {
            "flag": make_status_description("hmi_data", "조건 불충족 여부", False),
            "unsatisfied": make_status_description("hmi_data", "조건 불충족 내용", "")
        },
        "recv_time": make_status_description("hmi_data", "수신 시간", "")
    }
    if speed_door_flag is True:
        hmi_status_description["hmi_status"].update({
            "speed_door_down_limit": make_status_description("hmi_contact", "스피드도어 닫힘 여부", False, "DI3"),
            "speed_door_up_limit": make_status_description("hmi_contact", "스피드도어 열림 여부", False, "DI4"),
            "speed_door_up": make_status_description("hmi_contact", "스피드도어 열림 명령", False, "DO0"),
            "speed_door_stop": make_status_description("hmi_contact", "스피드도어 정지 명령", False, "DO1"),
            "speed_door_down": make_status_description("hmi_contact", "스피드도어 닫힘 명령", False, "DO2")
        })
    if hmi_number == 1:
        hmi_status_description["airlink_ping"] = make_status_description("hmi_connect", "AP 핑", False, f"ip.{210}")
    elif hmi_number == 5:
        hmi_status_description["airlink_ping"] = make_status_description("hmi_connect", "AP 핑", False, f"ip.{211}")
    return hmi_status_description


# 상태(접점) 설명
status_description = {
    "agv_1": get_agv_status_description(1),
    "agv_2": get_agv_status_description(2),
    "loading_hmi": get_hmi_status_description(1, False),
    "unloading_hmi": get_hmi_status_description(2, False),
    "assembly_buffer_hmi": get_hmi_status_description(3, False),
    "assembly_hmi": get_hmi_status_description(4, False),
    "airtightness_buffer_hmi": get_hmi_status_description(5, False),
    "airtightness_hmi": get_hmi_status_description(6, True),
    "loop_buffer_hmi": get_hmi_status_description(7, False),
    "loop_hmi": get_hmi_status_description(8, False),
    "mes": {
        'buzzer_off': make_status_description("recv", "작업 지시", True, "D1000.0"),
        "detect": make_status_description("recv", "PLC ▶ ACS Watchdogs", True, "D1000.F"),
        'buzzer_off1': make_status_description("send", "작업 지시 확인", False, "D1001.0"),
        'emergency_btn1': make_status_description("send", "ACS ▶ PLC Watchdogs", False, "D1001.F"),
    }
}

# 섹션 설명
section_description = {
    "working_status": {
        "title": "작동 상태",
        "type": "row"
    },
    "contact": {
        "title": "I/O 상태",
        "type": "row"
    },
    "connect": {
        "title": "모듈 연결 상태",
        "type": "row"
    },
    "cmd_info": {
        "title": "명령 상태",
        "type": "row"
    },
    "hmi_contact": {
        "title": "감지 / 작동 상태",
        "type": "column"
    },
    "hmi_connect": {
        "title": "모듈 연결 상태",
        "type": "column"
    },
    "hmi_data": {
        "title": "ACS ▶ HMI 정보",
        "type": "row"
    },
    "front_left_motor_info": {
        "title": "전방 좌측 주행 모터드라이버 정보",
        "type": "row"
    },
    "front_right_motor_info": {
        "title": "전방 우측 주행 모터드라이버 정보",
        "type": "row"
    },
    "rear_left_motor_info": {
        "title": "후방 좌측 주행 모터드라이버 정보",
        "type": "row"
    },
    "rear_right_motor_info": {
        "title": "후방 우측 주행 모터드라이버 정보",
        "type": "row"
    },
    "front_left_steering_motor_info": {
        "title": "전방 좌측 조향 모터드라이버 정보",
        "type": "row"
    },
    "front_right_steering_motor_info": {
        "title": "전방 우측 조향 모터드라이버 정보",
        "type": "row"
    },
    "rear_left_steering_motor_info": {
        "title": "후방 좌측 조향 모터드라이버 정보",
        "type": "row"
    },
    "rear_right_steering_motor_info": {
        "title": "후방 우측 조향 모터드라이버 정보",
        "type": "row"
    },
}

# 모터 설명
motor_description = {
    "front_left": {
        "explain": "주행",
    },
    "front_right": {
        "explain": "주행",
    },
    "rear_left": {
        "explain": "주행",
    },
    "rear_right": {
        "explain": "주행",
    },
    "front_left_steering": {
        "explain": "조향",
    },
    "front_right_steering": {
        "explain": "조향",
    },
    "rear_left_steering": {
        "explain": "조향",
    },
    "rear_right_steering": {
        "explain": "조향",
    },
    "fork/z": {
        "explain": "포크",
    },
    "fork/y": {
        "explain": "포크",
    },
    "tilting": {
        "explain": "틸팅",
    },
    "conv": {
        "explain": "컨베이어",
    }
    # "lift": {
    #     "explain": "리프트",
    #     "plus": "상승",
    #     "minus": "하강"
    # }
}
