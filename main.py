# -*- coding: utf-8 -*-
import asyncio
import multiprocessing as mp
import os
import shutil
import sys
import time
import traceback
import signal
import subprocess
import threading
from ipaddress import ip_address
from src.main_server.module.cofigparser import get_configparser
from src.web_server.web_server import web_server_start

import controller



# UI 프로그램 실행
def run_ui_exe(event: mp.Event, ui_exe_path):
    try:
        # exe 파일을 실행하고 그 프로세스를 모니터링
        ui_subprocess = subprocess.Popen([ui_exe_path], shell=True)
        ui_subprocess.wait()  # 실행된 프로세스가 종료될 때까지 대기
    except Exception as e:
        print(f"Error: {traceback.format_exc()}")
    finally:
        # 프로세스가 종료되면 이벤트를 set
        event.set()
#
# def run_ui_exe(event: mp.Event, ui_exe_path):
#     try:
#         print(f"Running exe: {ui_exe_path}")
#         # ui_subprocess = subprocess.Popen(['osascript', '-e', f'tell app "Terminal" to do script "{ui_exe_path}"'])
#         # ui_subprocess.wait()
#         # # stdout, stderr = ui_subprocess.communicate()  # 실행된 프로세스의 출력 대기
#         # # print(f"STDOUT: {stdout.decode('utf-8')}")
#         # # print(f"STDERR: {stderr.decode('utf-8')}")
#         time.sleep(600)
#     except Exception as e:
#         print(f"Error: {traceback.format_exc()}")
#     event.set()  # 예외 발생 시 이벤트를 set하여 종료하도록 처리
#
#
#
# # UI 프로그램 실행
# def run_ui_browser(ui_exe_path):
#     try:
#         # exe 파일을 실행하고 그 프로세스를 모니터링
#         ui_subprocess = subprocess.Popen("wine", [ui_exe_path], shell=True)
#         ui_subprocess.wait()  # 실행된 프로세스가 종료될 때까지 대기
#     except Exception as e:
#         print(f"Error: {traceback.format_exc()}")


if __name__ == "__main__":
    # ==========================
    # 옵션 설정
    # ==========================
    mp.freeze_support()
    # set_event_loop_policy(WindowsSelectorEventLoopPolicy())


    # ==========================
    # 임시 폴더 삭제
    # ==========================
    # base_dir = os.path.dirname(os.path.abspath(__file__))
    # setup_path, setup_dir = os.path.split(base_dir)
    # print(setup_path, setup_dir)
    # for file in os.listdir(setup_path):
    #     if file.startswith("_MEI") is True and file != setup_dir:
    #         print("삭제", file)
    #         shutil.rmtree(os.path.join(setup_path, file))
    # ui_temp_path = os.path.join(os.getenv('APPDATA'), "iljin_desktop")
    # if os.path.isdir(ui_temp_path) is True:
    #     shutil.rmtree(os.path.join(setup_path, ui_temp_path))

    # ==========================
    # 종료 시그널
    # ==========================
    stop_event = mp.Event()
    # logger = get_logger("main_program", stop_event=stop_event)
    def exit_sigint():
        # logger.info("프로그램 종료 시그널")
        stop_event.set()
    signal.signal(signal.SIGINT, lambda sig, frame: exit_sigint())

    # # ==========================
    # # 서버 관련 변수
    # # ==========================
    ip_address = get_configparser("option", "ip_address", "127.0.0.1")
    api_port: int = int(get_configparser("option", "api_port", "8000"))
    web_port: int = int(get_configparser("option", "web_port", "3000"))
    web_build_path: str = "web_build"

    origins: list = [
        "http://localhost",
        "http://127.0.0.1",
        f"http://{ip_address}",
        f"http://localhost:{api_port}",
        f"http://127.0.0.1:{api_port}",
        f"http://{ip_address}:{api_port}",
        f"http://localhost:{web_port}",
        f"http://127.0.0.1:{web_port}",
        f"http://{ip_address}:{web_port}"
    ]
    #
    # # 개발 여부
    if get_configparser("option", "dev", "1") == "1":
        origins.append("http://127.0.0.1:3000")
        origins.append("http://localhost:3000")
        origins.append(f"http://{ip_address}:3000")

    process_data: dict = {}
    # ==========================
    # 메인 서버 시작
    # ==========================
    # send_queue: mp.Queue = mp.Queue()
    # recv_queue: mp.Queue = mp.Queue()
    # process_data["main_server"] = mp.Process(target=start_main_server,
    #                                  args=(send_queue, recv_queue, stop_event),
    #                                  name="main_server")
    # process_data["main_server"].start()

    # ==========================
    # 웹 서버 시작
    # ==========================
    process_data["web_server"] = mp.Process(target=web_server_start,
                                            args=(
                                            "web_server", ip_address, web_port, origins, stop_event, web_build_path),
                                            name="web_server")
    process_data["web_server"].start()

    # ==========================
    # UI 프로그램 실행
    # ==========================
    # UI 프로그램 여부
    # if get_configparser("option", "ui", "1") == "1":
    # exe_path: str = os.path.join(os.getcwd(), "test_hd_samho.sh")
    # process_data["ui_process"] = mp.Process(target=run_ui_exe, args=(stop_event, exe_path))
    # process_data["ui_process"].start()

    controller.Controller(stop_event).start_server()
    # ==========================
    # API 서버 시작
    # ==========================
    # api_server_start("api_server",
    #                  ip_address=ip_address, port=api_port, origins=origins, stop_event=stop_event,
    #                  send_queue=send_queue, recv_queue=recv_queue)

    # ==========================
    # 프로세스 종료
    # ==========================
    # for _process in process_data.values():
    #     try:
    #         if _process.is_alive():
    #             _process.terminate()
    #             _process.join(1)
    #             if _process.is_alive():
    #                 _process.kill()
    #     except Exception as e:
    #         pass
    # print("프로그램 종료")
    # sys.exit(1)
