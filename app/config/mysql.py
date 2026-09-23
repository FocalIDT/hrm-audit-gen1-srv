import os
import urllib.parse
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config.config import (DATABASE_URL_OVERRIDE, MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT,
                               MYSQL_USER)
from app.config.logging_config import get_logger

logger = get_logger(class_name=__name__)

# mysql-connector ships a C extension and a pure-Python driver. The C extension
# segfaults on connect under some Windows builds, so allow opting into the pure
# driver locally. Defaults to off, so deployed (Linux) behaviour is unchanged.
_USE_PURE = os.environ.get("MYSQL_USE_PURE", "").strip().lower() in {"1", "true", "yes"}

if DATABASE_URL_OVERRIDE:
    DATABASE_URL = DATABASE_URL_OVERRIDE
    _engine_kwargs = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
else:
    encoded_password = urllib.parse.quote(MYSQL_PASSWORD)
    DATABASE_URL = (f"mysql+mysqlconnector://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}:{MYSQL_PORT}/"
                    f"{MYSQL_DB}?charset=utf8mb4")
    _engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "connect_args": {"use_pure": True} if _USE_PURE else {},
    }

engine = create_engine(DATABASE_URL, echo=False, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]
