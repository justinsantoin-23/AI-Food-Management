import os, datetime as dt, bcrypt, jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./foodwise.db")
SECRET = os.getenv("SECRET_KEY", "dev-only-change-me")
engine = create_engine(DB_URL, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)

class Base(DeclarativeBase): pass

def now(): return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h.encode())
def make_token(uid):
    return jwt.encode({"sub": str(uid), "exp": now() + dt.timedelta(hours=12)}, SECRET, "HS256")

bearer = HTTPBearer()
def current_user(cred=Depends(bearer), db=Depends(get_db)):
    from models import User
    try: uid = int(jwt.decode(cred.credentials, SECRET, ["HS256"])["sub"])
    except Exception: raise HTTPException(401, "Session expired. Sign in again.")
    u = db.get(User, uid)
    if not u: raise HTTPException(401, "Account not found.")
    return u

def require(*roles):
    def dep(u=Depends(current_user)):
        if u.role not in roles: raise HTTPException(403, "Your account type can't do this.")
        return u
    return dep
