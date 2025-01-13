import datetime
import traceback
from fastapi import Depends, Request
from sqlalchemy.orm import Session
from jose import jwt

from src.database.database import get_db
from src.api_server.domain.auth.auth_core import login_check, SECRET_KEY, ALGORITHM
from src.api_server.domain.auth.auth_crud import password_checking, password_changing
from src.main_server.module.fastapi_module import APIRouterModule


class AuthAPIRouter(APIRouterModule):
    def _set_routes(self):
        # 로그인
        @self.router.post("/login")
        async def login(request: Request, db: Session = Depends(get_db)):
            password_item = await request.json()
            return_json = {
                "msg": "",
                "success": False
            }
            try:
                flag = password_checking(db, password_item)
                if flag is False:
                    # 비밀번호가 맞지 않다면
                    return_json["msg"] = "비밀번호가 일치하지 않습니다"
                else:
                    # 비밀번호가 맞다면
                    hash_data = {
                        "pw": password_item["password"],
                        "ip": request.client.host,
                        "exp": datetime.datetime.now() + datetime.timedelta(days=365 * 100)
                    }
                    hash_token = jwt.encode(hash_data, SECRET_KEY, algorithm=ALGORITHM)
                    return_json["login_hash"] = hash_token
                    return_json["success"] = True
            except Exception:
                print(traceback.format_exc())
                return_json["msg"] = "DB에 접근할 수 없습니다"
            return return_json

        @self.router.post("/login_check")
        async def login_check_router(request: Request, db: Session = Depends(get_db)):
            hash_item = await request.json()
            return login_check(request, hash_item, db)

        # 비밀번호 확인
        @self.router.post("/password")
        async def password(request: Request, db: Session = Depends(get_db)):
            password_item = await request.json()
            msg: str = ""
            flag: bool = False
            try:
                flag = password_checking(db, password_item)
                if flag is False:
                    # 비밀번호가 맞지 않다면
                    msg = "비밀번호가 일치하지 않습니다"
            except Exception:
                print(traceback.format_exc())
                msg = "DB에 접근할 수 없습니다"
            return {"success": flag, "msg": msg}

        # 비밀번호 확인
        @self.router.post("/password_change")
        async def password_change(request: Request, db: Session = Depends(get_db)):
            password_item = await request.json()
            msg: str = ""
            flag: bool = False
            try:
                flag: bool = password_changing(db, password_item)
                if flag is False:
                    # 비밀번호가 맞지 않다면
                    msg = "비밀번호가 일치하지 않습니다"
            except Exception:
                print(traceback.format_exc())
                msg = "DB에 접근할 수 없습니다"
            return {"success": flag, "msg": msg}

