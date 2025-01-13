import traceback
import multiprocessing as mp
import uvicorn

from src.main_server.module.fastapi_module import WebServer
from src.main_server.module.logger import get_logger


# 웹 서버 시작
def web_server_start(program_name: str, ip_address: str, port: int, origins: list, stop_event: mp.Event, web_dir_path: str):
    web_logger = get_logger(program_name, stop_event=stop_event)
    web_server = WebServer(program_name=program_name, origins=origins, logger=web_logger, web_dir_path=web_dir_path, stop_event=stop_event)
    web_app = web_server.get_app()
    try:
        uvicorn.run(web_app, host=ip_address, port=port, access_log=False)
    except Exception:
        web_logger.warning(traceback.format_exc())
    web_logger.info(f"{program_name} 종료")
