from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.models.db import SessionLocal, init_db
from app.module_loader import sync_all_modules
from app.scheduler import scheduler_manager
from app.utils.logger import logger
from app.web.api import router as api_router
from app.web.ui import router as ui_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DailyImprove 启动中...")
    init_db()
    session = SessionLocal()
    try:
        sync_all_modules(session)
    finally:
        session.close()
    scheduler_manager.start()
    logger.info("DailyImprove 启动完成")
    yield
    scheduler_manager.shutdown()
    logger.info("DailyImprove 已退出")


app = FastAPI(title="DailyImprove", version="0.1", lifespan=lifespan)
app.include_router(ui_router)
app.include_router(api_router)
