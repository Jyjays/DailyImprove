"""APScheduler 调度封装。"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.models.db import SessionLocal
from app.models.models import Module
from app.orchestrator import run_module
from app.utils.logger import logger


class SchedulerManager:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Shanghai"))

    def start(self) -> None:
        self.scheduler.start()
        self.resync_jobs()
        logger.info("调度器已启动")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def resync_jobs(self) -> None:
        session = SessionLocal()
        try:
            modules = list(session.execute(
                select(Module).where(Module.enabled == 1)
            ).scalars())
            keys_in_db = {m.key for m in modules}
            for job in self.scheduler.get_jobs():
                if job.id.startswith("module-") and job.id[7:] not in keys_in_db:
                    self.scheduler.remove_job(job.id)
                    logger.info("移除调度任务: %s", job.id)
            for module in modules:
                self._schedule_module(module.key, module.schedule, module.timezone)
        finally:
            session.close()

    def _schedule_module(self, key: str, cron_expr: str, timezone: str) -> None:
        job_id = f"module-{key}"
        try:
            trigger = CronTrigger.from_crontab(cron_expr, timezone=ZoneInfo(timezone))
        except Exception as e:
            logger.error("模块 %s cron 表达式无效: %s（%s）", key, cron_expr, e)
            return
        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info("更新调度任务 %s: %s", job_id, cron_expr)
        else:
            self.scheduler.add_job(
                run_module,
                trigger=trigger,
                args=[key],
                id=job_id,
                name=f"module-{key}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            logger.info("新增调度任务 %s: %s", job_id, cron_expr)

    def schedule_module(self, key: str, cron_expr: str, timezone: str = "Asia/Shanghai") -> None:
        self._schedule_module(key, cron_expr, timezone)


scheduler_manager = SchedulerManager()
