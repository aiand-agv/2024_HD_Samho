# -*- coding: utf-8 -*-
import traceback
import time
import uvicorn
import multiprocessing as mp

from src.api_server.domain.acs_main.main_router import MainAPIRouter
from src.api_server.domain.auth.auth_router import AuthAPIRouter
from src.main_server.module.fastapi_module import APIServerModule
from src.main_server.module.logger import get_logger
from src.main_server.module.thread_with_exception import ThreadWithException


class APIServer(APIServerModule):
    # route 설정
    def set_main_router(self, send_queue, recv_queue, stop_event):
        main_router = MainAPIRouter(self.program_name, prefix="", logger=self.logger,
                                    send_queue=send_queue, recv_queue=recv_queue,
                                    stop_event=stop_event)
        self.api_app.include_router(main_router.get_router())

        auth_router = AuthAPIRouter(self.program_name, prefix="/auth", logger=self.logger)
        self.api_app.include_router(auth_router.get_router())


def run_api_server(args):
    api_app, ip_address, port, access_log = args
    uvicorn.run(api_app, host=ip_address, port=port, access_log=access_log)


def api_server_start(program_name: str, ip_address: str, port: int, origins: list,
                     stop_event: mp.Event, send_queue: mp.Queue, recv_queue: mp.Queue):
    api_logger = get_logger(program_name, stop_event=stop_event, console_flag=True)
    api_server = APIServer(program_name=program_name, origins=origins, logger=api_logger, stop_event=stop_event)
    api_server.set_main_router(send_queue, recv_queue, stop_event)
    api_app = api_server.get_app()
    try:
        api_server_thread = ThreadWithException(run_api_server, api_app, ip_address, port, False)
        api_server_thread.start()

        while not stop_event.is_set():
            time.sleep(0.1)

        if api_server_thread.run_flag:
            api_server_thread.raise_exception()
    except Exception:
        api_logger.warning(traceback.format_exc())
    api_logger.info(f"{program_name} 종료")
