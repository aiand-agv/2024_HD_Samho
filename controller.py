from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from db_sever import DBServer  # DBServer 클래스 임포트
import uvicorn
import time
import sys
import signal

from src.main_server.module.thread_with_exception import ThreadWithException


class Controller () :

    def __init__(self, stop_event):
        self.stop_event = stop_event

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        server = DBServer(self.stop_event)
        asyncio.create_task(server.run())
        app.state.db_server = server
        yield
    def create_app(self):
        app = FastAPI(lifespan= self.lifespan)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.post("/serial/post/test")
        async def read_post_data(request: Request):
            server = request.app.state.db_server
            status = server.influxdb_connection_check()
            result = server.result
            print(f"data :  {result}")
            message = "DB가 연결되지 않았습니다"
            if status:
                return {"status": status, "data": result}
            else:
                return {"status": status, "data": {"message": message}}
        return  app

    def shutdown_server(self, thread):
        print("Shutting down server...")
        self.stop_event.set()
        thread.join(timeout=5)
        sys.exit(0)

    def run_server(self):
        app = self.create_app()
        uvicorn.run(app, host="localhost", port=8000, access_log=False)

    def start_server(self):
        try:
            api_server_thread = ThreadWithException(self.run_server)
            api_server_thread.start()

            # signal.signal(signal.SIGINT, lambda sig, frame: shutdown_server(stop_event, api_server_thread))
            # signal.signal(signal.SIGTERM, lambda sig, frame: shutdown_server(stop_event, api_server_thread))

            while not self.stop_event.is_set():
                time.sleep(0.1)
            if api_server_thread.run_flag:
                api_server_thread.raise_exception()
                api_server_thread.join()
        except Exception as e:
            print(f"Error : API Server Do not Start")

