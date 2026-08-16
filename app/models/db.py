from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from app.models import models  # noqa: F401  # 注册模型
    Base.metadata.create_all(bind=engine)
    # SQLite 部分唯一索引：持久型内容永久去重；时效型仅按日期建普通索引
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_items_persistent_dedup "
                "ON items(module_id, unique_key) WHERE lifetime = 'persistent'"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_items_ephemeral_dedup "
                "ON items(module_id, unique_key, fetched_at) WHERE lifetime = 'ephemeral'"
            ))


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
