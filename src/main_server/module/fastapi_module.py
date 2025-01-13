# -*- coding: utf-8 -*-
import datetime
import logging
import time
import asyncio

from fastapi import FastAPI, APIRouter
from abc import *   # 추상 클래스 사용
from starlette.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from src.main_server.module.logger import get_logger, LoggerPrint
from functools import partial
from fastapi.staticfiles import StaticFiles


# 고유번호 가져오기
def get_id():
    return str(round(time.mktime(datetime.datetime.now().timetuple())))


# 응답 확인
async def get_response_check(response_check, working_id):
    start_time = datetime.datetime.now()
    response_check[working_id] = {}
    success_flag = False
    msg = None
    data = None
    try:
        while True:
            response_data = response_check[working_id].get("result")
            if response_data is not None:
                success_flag = response_data.get("flag", False)
                msg = response_data.get("msg", msg)
                data = response_data.get("data", data)
                break

            now_time = datetime.datetime.now()
            if now_time - start_time >= datetime.timedelta(seconds=5):
                # 5초 동안 응답이 없으면 자동 OFF
                msg = "서버의 응답이 없습니다."
                break
            await asyncio.sleep(0.1)
    except Exception:
        pass

    if response_check.get(working_id) is not None:
        del response_check[working_id]

    return_data = {"flag": success_flag}
    if msg is not None:
        # 메시지가 있다면 메세지 추가
        return_data["msg"] = msg
    if data is not None:
        # 데이터가 있으면 데이터 추가
        return_data["data"] = data
    return return_data


# React Router 연결
class SpaFallbackMiddleware(BaseHTTPMiddleware):
    def __init__(self, index_html_path, app):
        self.index_html_path = index_html_path
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if response.status_code == 404:
            # 404 에러가 발생하면 React 애플리케이션의 index.html 파일을 반환
            response = HTMLResponse(content=open(self.index_html_path, "r", encoding="utf-8").read(), status_code=200)
        return response


# API 서버
class APIServerModule(metaclass=ABCMeta):
    # 생성자
    def __init__(self, program_name, origins, stop_event, logger=None, allow_ips=None, allow_urls=None):
        # Set Variable
        self.program_name = program_name
        self.allow_ips = allow_ips          # 허용 IP
        self.allow_urls = allow_urls        # 허용 URL
        self.stop_event = stop_event
        if logger is None:
            self.logger = LoggerPrint(self.program_name)
        else:
            self.logger = logger
        self.api_app: FastAPI = FastAPI(docs_url=None, redoc_url=None)

        self.api_app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._set_logger()
        self._set_middleware()

    def _set_middleware(self):
        @self.api_app.middleware("http")
        async def check_allow(request: Request, call_next):
            if self.allow_ips is not None:
                # 허용 아이피가 존재할 경우
                client_ip = request.client.host
                if client_ip not in self.allow_ips:
                    raise HTTPException(status_code=403, detail="접근이 허용되지 않은 IP입니다.")

            if self.allow_urls is not None:
                # 허용 URL이 존재할 경우
                if request.url.path in self.allow_urls:
                    response = await call_next(request)
                    response.headers["Access-Control-Allow-Origin"] = "*"
                    response.headers["Access-Control-Allow-Methods"] = "*"
                    response.headers["Access-Control-Allow-Headers"] = "*"
                    return response
            response = await call_next(request)
            return response

    # 로그 설정
    def _set_logger(self):
        @self.api_app.on_event("startup")
        async def startup_event():
            pass
            # if isinstance(self.logger, logging.Logger) is True:
            #     logger_access = logging.getLogger('uvicorn.access')
            #     logger_error = logging.getLogger('uvicorn.error')
            #     get_logger(self.program_name, logger=logger_error, console_flag=True, duplicate_flag=True, stop_event=self.stop_event)
            #     get_logger(self.program_name, logger=logger_access, console_flag=True, duplicate_flag=True, stop_event=self.stop_event)

    def get_app(self):
        return self.api_app


class APIRouterModule(metaclass=ABCMeta):
    # 생성자
    def __init__(self, program_name, prefix="", logger=None):
        # Set Variable
        if logger is None:
            self.logger = LoggerPrint(program_name)
        else:
            self.logger = logger
        self.router = APIRouter(prefix=prefix)
        self._set_routes()

    # route 설정
    @abstractmethod
    def _set_routes(self):
        pass

    def get_router(self):
        return self.router


# 웹 서버
class WebServer(APIServerModule):
    def __init__(self, program_name: str, origins: list, logger, web_dir_path, stop_event):
        super().__init__(program_name, origins, stop_event, logger=logger)
        # React 앱의 빌드 파일이 있는 디렉토리를 정적 파일 디렉토리로 설정합니다.
        self.api_app.mount("/", StaticFiles(directory=web_dir_path, html=True))

        # 미들 웨어 설정
        self.api_app.add_middleware(partial(SpaFallbackMiddleware, f"{web_dir_path}/index.html"))
