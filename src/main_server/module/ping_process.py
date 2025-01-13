
import datetime
import logging
import multiprocessing as mp
import atexit
import time
import traceback

from src.main_server.module.logger import get_logger, LoggerPrint
from src.main_server.module.thread_with_exception import ThreadWithException
from ping3 import ping


def check_ip_address(ip_address):
    try:
        response = ping(ip_address, unit="ms")
        if response is False or response is None:
            return False
        else:
            return True
    except Exception:
        return False


class PingProcess:
    def __init__(self, program_name: str, ping_process_parameter: dict = {},
                 data_queue: mp.Queue = mp.Queue(), logger: logging.Logger = None, stop_event = mp.Event()):
        self.data_queue: mp.Queue = data_queue   # 데이터 큐
        self.stop_event: mp.Event = stop_event
        self.task_list: list = []  # 비동기 통신 리스트
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger
        atexit.register(self.__del__)
        self.run_process(ping_process_parameter)

    def __del__(self):
        self.close()

    def close(self):
        self.logger.info(f'프로그램을 종료합니다.')

        for task_item in self.task_list:
            if task_item.run_flag is True:
                task_item.raise_exception()

    def run_process(self, ping_process_parameter):
        for module_name, ip_address_data in ping_process_parameter.items():
            for ip_address_key, option_data in ip_address_data.items():
                self.task_list.append(ThreadWithException(self.ping_process, module_name, ip_address_key, option_data))

        for task_item in self.task_list:
            task_item.start()

        for task_item in self.task_list:
            task_item.join()
        self.close()

    def ping_process(self, args):
        module_name, ip_address_key, option_data = args
        ip_address = option_data.get("ip_address")
        cycle = option_data.get("cycle", 1)
        start_time = option_data.get("start_time")
        end_time = option_data.get("end_time")
        pre_data: bool = False
        count: int = 0

        if ip_address is None:
            self.logger.info(f'[{module_name}] {ip_address_key} 아이피가 존재하지 않음')
            return

        time_limit_flag = False
        if start_time is not None and end_time is not None:
            time_limit_flag = True
            start_hours, start_minutes, start_seconds = map(int, start_time.split(":"))
            end_hours, end_minutes, end_seconds = map(int, end_time.split(":"))
            start_time = datetime.timedelta(hours=start_hours, minutes=start_minutes, seconds=start_seconds)
            end_time = datetime.timedelta(hours=end_hours, minutes=end_minutes, seconds=end_seconds)

        pre_ping_check_flag = None
        while not self.stop_event.is_set():
            ping_check_flag = True
            if time_limit_flag is True:
                now_time = datetime.datetime.now()
                now_date = datetime.datetime.combine(now_time.date(), datetime.datetime.min.time())
                if now_date + start_time <= now_time <= now_date + end_time:
                    ping_check_flag = True
                else:
                    ping_check_flag = False
                if pre_ping_check_flag != ping_check_flag:
                    if ping_check_flag is True:
                        self.logger.info(f'[{module_name}] {ip_address_key} 핑 테스트 시작 ({start_time} ~ {end_time})')
                    else:
                        self.logger.info(f'[{module_name}] {ip_address_key} 핑 테스트 종료 ({start_time} ~ {end_time})')
                    pre_ping_check_flag = ping_check_flag

            if ping_check_flag is True:
                now_data = check_ip_address(ip_address)
                if now_data is True:
                    count = 0
                if pre_data != now_data:
                    if now_data is False:
                        # 핑 테스트 실패한 경우 5회 카운트 후에도 안되면 False 전송
                        if count < 5:
                            count += 1
                            time.sleep(1)
                            continue
                        self.logger.info(f'[{module_name}] {ip_address_key} 핑 테스트 실패')
                    else:
                        self.logger.info(f'[{module_name}] {ip_address_key} 핑 테스트 성공')

                    pre_data = now_data
                    self.data_queue.put({
                        "type": "ping_data",
                        "module_name": module_name,
                        "data": {ip_address_key: now_data}
                    })
            time.sleep(cycle)

# 핑 프로세스 시작
def start_ping_process(ping_process_parameter, data_queue, stop_event):
    ping_logger = get_logger("ping_process", stop_event=stop_event)
    try:
        PingProcess(program_name="ping_process", ping_process_parameter=ping_process_parameter, data_queue=data_queue, logger=ping_logger, stop_event=stop_event)
    except Exception as e:
        ping_logger.warning(f"예외 발생 {traceback.format_exc()}")
