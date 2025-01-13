import datetime


class WatchdogsProcess:
    def __init__(self, watchdogs_parameter: dict):
        self.watchdogs_data: dict = {}
        for module_name, watchdogs_info in watchdogs_parameter.items():
            self.watchdogs_data[module_name] = {}
            send_watchdogs_data_name = watchdogs_info.get("send")
            recv_watchdogs_data_name = watchdogs_info.get("recv")

            if send_watchdogs_data_name is not None:
                self.watchdogs_data[module_name]["send"] = {
                    "key": send_watchdogs_data_name,
                    "value": False,
                }

            if recv_watchdogs_data_name is not None:
                self.watchdogs_data[module_name]["recv"] = {
                    "key": recv_watchdogs_data_name,
                    "value": False,
                    "time": datetime.datetime.now(),
                }

    # 와치독스 데이터 가져오기
    def get_watchdogs_data(self, module_name: str, watchdogs_type: str):
        return self.watchdogs_data.get(module_name, {}).get(watchdogs_type)
