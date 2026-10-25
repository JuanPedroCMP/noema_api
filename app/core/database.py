from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from pathlib import Path
from collections.abc import Generator
import os
import logging
from urllib.parse import quote_plus
from sqlalchemy import event

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / "config" / ".env.supabase")

logger = logging.getLogger(__name__)

def _required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Database setting '{name}' is not configured.")
    return value


USER = _required_setting("user")
PASSWORD = _required_setting("password")
HOST = _required_setting("host")
PORT = _required_setting("port")
DBNAME = _required_setting("dbname")

DATABASE_URL = (
    f"postgresql+psycopg2://{quote_plus(USER)}:{quote_plus(PASSWORD)}"
    f"@{HOST}:{PORT}/{quote_plus(DBNAME)}?sslmode=require"
)


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
    pool_size=_get_int("DB_POOL_SIZE", 15),
    max_overflow=_get_int("DB_MAX_OVERFLOW", 15, minimum=0),
    pool_timeout=_get_int("DB_POOL_TIMEOUT", 30),
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _log_database_connection(dbapi_connection, connection_record) -> None:
    """Log only after the database has accepted a new physical connection."""
    logger.info("DB successfully conected")


session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    db = session()
    try:
        yield db
    finally:
        db.close()
