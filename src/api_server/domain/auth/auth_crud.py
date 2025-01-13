from passlib.context import CryptContext
from sqlalchemy.orm import Session
from src.database.models import Password

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# 비밀번호 데이터 가져오기
def get_password_data(db: Session, password_item: dict):
    password_data = db.query(Password).filter(Password.idx == 1).first()
    if password_data is None:
        # 비밀번호가 없다면 비밀번호 추가
        db_password = Password(
            idx=1,
            password=pwd_context.hash(password_item["password"])
        )
        db.add(db_password)
        db.commit()
        return db_password
    else:
        return password_data


# 비밀번호 확인
def password_checking(db: Session, password_item: dict):
    password_data = get_password_data(db, password_item)
    return pwd_context.verify(password_item["password"], password_data.password)


# 비밀번호 변경
def password_changing(db: Session, password_item: dict):
    if password_checking(db, password_item) is True:
        # 비밀번호가 참이라면
        now_password_data = get_password_data(db, password_item)
        now_password_data.password = pwd_context.hash(password_item["change_password"])
        db.add(now_password_data)
        db.commit()
        return True
    else:
        # 비밀번호가 맞지 않다면
        return False
