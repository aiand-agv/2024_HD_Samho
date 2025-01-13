#################################
# LS 산전 PLC 파라미터
#################################
# LS 산전 PLC 주소 파라미터
from src.main_server.module.cofigparser import get_configparser

ls_plc_address_param = {}

# LS 산전 PLC 디바이스 타입 정보
ls_plc_device_types = {}

# LS 산전 PLC 디바이스 데이터 정보
ls_plc_device_data_info = {}


#################################
# MELSEC PLC 파라미터
#################################
# MELSEC PLC 주소 파라미터
melsec_plc_address_param = {}

# MELSEC PLC 데이터 정보 파라미터
melsec_plc_device_types = {}

# MELSEC PLC 디바이스 데이터 정보
melsec_plc_device_data_info = {}


#################################
# MODBUS 파라미터
#################################
modbus_address_param = {}

modbus_data_types = {}

modbus_data_info = {}


#################################
# AGV 파라미터
#################################
ip_address = get_configparser("option", "ip_address", "192.168.2.100")
header_code = get_configparser("option", "header_code", "sis_agv")
agv_address_param = {
    "agv_1": {
        "ip_address": ip_address,
        "port": 8511,
        "server_flag": True,
        "agv_number": 1,
        "header_code": header_code
    },
    "agv_2": {
        "ip_address": ip_address,
        "port": 8512,
        "server_flag": True,
        "agv_number": 2,
        "header_code": header_code
    },
}

other_address_param = {
    # "mes": {
    #     "ip_address": ip_address,
    #     "port": 8500,
    #     "server_flag": True,
    #     "header_code": header_code
    # }
}

#################################
# 기타
#################################
# 필터 적용할 데이터
# "agv_1": {
#     "move_avg_filter": {
#         "battery": 100
#     },
#     "unsigned": {
#         "battery": True
#     }
# }
data_filter = {

}

