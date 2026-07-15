import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models import User

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-development-secret")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()
def hash_password(password: str): return pwd_context.hash(password)
def verify_password(password: str, password_hash: str): return pwd_context.verify(password, password_hash)
def create_token(user: User):
    expiry = datetime.now(timezone.utc) + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")))
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": expiry}, SECRET_KEY, algorithm=ALGORITHM)
def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    try: user_id = int(jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])["sub"])
    except (JWTError, KeyError, ValueError): raise HTTPException(status_code=401, detail="Token ไม่ถูกต้องหรือหมดอายุ")
    user = db.get(User, user_id)
    if not user or not user.is_active: raise HTTPException(status_code=401, detail="ไม่พบบัญชีผู้ใช้")
    return user
def require_roles(*roles):
    def check(user: User = Depends(current_user)):
        if user.role not in roles: raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์ดำเนินการนี้")
        return user
    return check

