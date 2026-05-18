from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from functools import lru_cache
from app.core.config import get_settings
from app.core.logging import logger


@lru_cache()
def get_engine() -> Engine:
    s = get_settings()
    return create_engine(
        s.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


def check_db() -> bool:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB check failed: {e}")
        return False
