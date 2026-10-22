from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from pathlib import Path
from collections.abc import Generator
import os

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / "config" / ".env.supabase")

USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"


def _get_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer greater than or equal to {minimum}.") from exc

    if parsed < minimum:
        raise RuntimeError(f"{name} must be an integer greater than or equal to {minimum}.")
    return parsed


# Keep one independent connection available for each concurrent request that
# needs the database, while allowing short bursts above the steady-state pool.
engine = create_engine(
    DATABASE_URL,
    pool_size=_get_int("DB_POOL_SIZE", 10),
    max_overflow=_get_int("DB_MAX_OVERFLOW", 20, minimum=0),
    pool_timeout=_get_int("DB_POOL_TIMEOUT", 30),
    pool_pre_ping=True,
)
session = sessionmaker(bind=engine)

def get_db() -> Generator[Session, None, None]:
    db = session()
    try:
        yield db
    finally:
        db.close()