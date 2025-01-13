import datetime
import traceback
from typing import Optional

from fastapi import Depends, Request
from fastapi.params import Cookie
from sqlalchemy.orm import Session
from jose import jwt

from src.database.database import get_db
from src.api_server.domain.auth.auth_crud import password_checking



SECRET_KEY = "6elf3ododbuzjiy34gpd51jg3v02asu0jjhcgea8gshqd1kiju4qeyrampwcn0zn"
ALGORITHM = "HS256"


# 로그인 해쉬 체크
def login_hash_check(request: Request, login_hash: Optional[str] = Cookie(None),
                           db: Session = Depends(get_db)):
    print("login_hash", login_hash)
    if login_hash is not None:
        hash_item = {
            "password": login_hash
        }
        return_json = login_check(request, hash_item, db)
        return return_json.get("success", False)
    else:
        return False


def login_check(request: Request, hash_item: dict, db: Session = Depends(get_db)):
    return_json = {
        "success": False
    }
    try:
        payload = jwt.decode(hash_item["password"], SECRET_KEY, algorithms=[ALGORITHM])
        password_item = {
            "password": payload.get("pw")
        }
    except Exception:
        return_json["msg"] = "알 수 없는 오류가 발생하였습니다"
    else:
        if request.client.host != payload.get("ip"):
            # 아이피가 맞지 않을 경우
            return_json["msg"] = "로그인에 실패하였습니다"
        else:
            # 아이피가 맞을 경우
            try:
                flag = password_checking(db, password_item)
                if flag is True:
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