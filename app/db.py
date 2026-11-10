import os
import re
import urllib.parse
import logging
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, pool, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

raw_url = os.getenv("DATABASE_URL", "").strip()
db_password = os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD")
APP_ENV = os.getenv("APP_ENV", "development").lower()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resolve_db_url(url: str, password: str = None) -> str:
    if not url:
        default_db = os.path.join(BASE_DIR, "restaurant.db").replace("\\", "/")
        return f"sqlite:///{default_db}"
    if url.startswith("sqlite:///"):
        sub = url[len("sqlite:///"):]
        if not os.path.isabs(sub) and not sub.startswith(":memory:"):
            abs_path = os.path.normpath(os.path.join(BASE_DIR, sub)).replace("\\", "/")
            return f"sqlite:///{abs_path}"
        return url
    if url.startswith("psql"):
        host_m = re.search(r'-h\s+([^\s]+)', url)
        user_m = re.search(r'-U\s+([^\s]+)', url)
        db_m = re.search(r'-d\s+([^\s]+)', url)
        port_m = re.search(r'-p\s+([^\s]+)', url)
        pwd_m = re.search(r'-W\s+([^\s]+)', url) or re.search(r'--password[=\s]+([^\s]+)', url)
        
        host = host_m.group(1) if host_m else "localhost"
        user = user_m.group(1) if user_m else "postgres"
        db = db_m.group(1) if db_m else "postgres"
        port = port_m.group(1) if port_m else "5432"

        if not password and user == "maitred_dev_user":
            password = "maitred_dev_pA$$W0rD"
        
        extracted_pwd = pwd_m.group(1) if pwd_m else None
        effective_pwd = password or extracted_pwd
        if not effective_pwd and user == "maitred_dev_user":
            effective_pwd = "maitred_dev_pA$$W0rD"
            
        pwd_encoded = urllib.parse.quote_plus(effective_pwd) if effective_pwd else ""
        pwd_part = f":{pwd_encoded}" if pwd_encoded else ""
        ssl_part = "?sslmode=require" if "rds.amazonaws.com" in host else ""
        return f"postgresql+psycopg2://{user}{pwd_part}@{host}:{port}/{db}{ssl_part}"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "rds.amazonaws.com" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
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
        print(f"[DB] Connected successfully to remote database: {DATABASE_URL.split('@')[-1]}")
        logger.info(f"Connected successfully to remote database: {DATABASE_URL.split('@')[-1]}")
except Exception as e:
    if APP_ENV != "production":
        print(
            f"[DB] Warning: Failed to connect to primary database ({DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}): {e}. "
            "Falling back to local SQLite database (restaurant.db)."
        )
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
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
        except Exception as e:
            logger.warning(f"Could not set SQLite PRAGMA: {e}")
