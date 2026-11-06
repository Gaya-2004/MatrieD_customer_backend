import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, pool, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

raw_url = os.getenv("DATABASE_URL", "").strip()
db_password = os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD")
APP_ENV = os.getenv("APP_ENV", "development").lower()

def resolve_db_url(url: str, password: str = None) -> str:
    if not url:
        return "sqlite:///restaurant.db"
    if url.startswith("psql"):
        host_m = re.search(r'-h\s+([^\s]+)', url)
        user_m = re.search(r'-U\s+([^\s]+)', url)
        db_m = re.search(r'-d\s+([^\s]+)', url)
        port_m = re.search(r'-p\s+([^\s]+)', url)
        
        host = host_m.group(1) if host_m else "localhost"
        user = user_m.group(1) if user_m else "postgres"
        db = db_m.group(1) if db_m else "postgres"
        port = port_m.group(1) if port_m else "5432"
        
        pwd_part = f":{password}" if password else ""
        return f"postgresql+psycopg2://{user}{pwd_part}@{host}:{port}/{db}"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url

DATABASE_URL = resolve_db_url(raw_url, db_password)

def init_engine(target_url: str):
    if target_url.startswith("sqlite"):
        return create_engine(
            target_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )
    return create_engine(
        target_url,
        connect_args={},
        poolclass=pool.QueuePool,
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_pre_ping=True,
        pool_recycle=3600,
    )

try:
    engine = init_engine(DATABASE_URL)
    if not DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Connected successfully to remote database: {DATABASE_URL.split('@')[-1]}")
except Exception as e:
    if APP_ENV != "production":
        logger.warning(
            f"Failed to connect to primary database ({DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}): {e}. "
            "Falling back to local SQLite database (restaurant.db)."
        )
        DATABASE_URL = "sqlite:///restaurant.db"
        engine = init_engine(DATABASE_URL)
    else:
        raise

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
