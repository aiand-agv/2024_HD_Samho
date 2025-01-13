# =========================
# 와치독스 프로세스
# =========================
# "master_plc": {
#     "send": "acs_to_master_plc_watch_dog",
#     "recv": "master_plc_to_acs_watch_dog",
# }
watchdogs_process_parameter = {
    "agv_1": {
        "send": "acs_to_agv_watch_dog",
        "recv": "agv_to_acs_watch_dog"
    },
    "agv_2": {
        "send": "acs_to_agv_watch_dog",
        "recv": "agv_to_acs_watch_dog"
    }
}



# =========================
# 핑 프로세스
# =========================
# "mes": {
#     "connect": {
#         "ip_address": "10.15.40.4",
#         "start_time": "07:00:00",
#         "end_time": "20:00:00",
#         "cycle": 5 * 60
#     },
# }
ping_process_parameter = {
    "agv_1": {
        "airlink_ping": {
            "ip_address": "192.168.2.201",
        },
        "agv_pc_ping": {
            "ip_address": "192.168.2.101",
        }
    },
    "agv_2": {
        "airlink_ping": {
            "ip_address": "192.168.2.202",
        },
        "agv_pc_ping": {
            "ip_address": "192.168.2.102",
        }
    },
}