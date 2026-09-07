"""REST API。"""
from __future__ import annotations

import re
import threading
from datetime import datetime
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.feedback import apply_feedback, get_source_effective_rating
from app.models.db import SessionLocal, get_session
from app.models.models import Feedback, Item, Module, PushRecord, RunRecord, Source
from app.module_loader import sync_module_file
from app.orchestrator import run_module
from app.scheduler import scheduler_manager
from app.schemas import parse_module_cfg

router = APIRouter(prefix="/api")


class FeedbackIn(BaseModel):
    source_id: int | None = None
    item_id: int | None = None
    module_id: int | None = None
    feedback_type: str
    rating: int | None = None


class ModuleToggleIn(BaseModel):
    enabled: bool


class ModuleCreateIn(BaseModel):
    key: str
    yaml: str


def _module_dict(m: Module, source_count: int = 0, last_run: RunRecord | None = None) -> dict[str, Any]:
    return {
        "id": m.id,
        "key": m.key,
        "name": m.name,
        "enabled": bool(m.enabled),
        "schedule": m.schedule,
        "timezone": m.timezone,
        "lifetime": m.lifetime,
        "max_items": m.max_items,
        "source_count": source_count,
        "last_run": {
            "status": last_run.status,
            "finished_at": last_run.finished_at.isoformat() if last_run and last_run.finished_at else None,
        } if last_run else None,
    }


@router.get("/status")
def status(session: Session = Depends(get_session)):
    module_count = session.execute(select(func.count(Module.id))).scalar_one()
    item_count = session.execute(select(func.count(Item.id))).scalar_one()
    today_runs = session.execute(select(func.count(RunRecord.id)).where(RunRecord.started_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))).scalar_one()
    return {"scheduler_running": scheduler_manager.scheduler.running, "modules": module_count, "items": item_count, "runs_today": today_runs}


@router.get("/modules")
def list_modules(session: Session = Depends(get_session)):
    modules = list(session.execute(select(Module).order_by(Module.id)).scalars())
    result = []
    for m in modules:
        source_count = session.execute(select(func.count(Source.id)).where(Source.module_id == m.id)).scalar_one()
        last_run = session.execute(select(RunRecord).where(RunRecord.module_id == m.id).order_by(desc(RunRecord.started_at)).limit(1)).scalar_one_or_none()
        result.append(_module_dict(m, source_count, last_run))
    return result


@router.post("/modules/{module_key}/run")
def trigger_run(module_key: str):
    # 同步运行更直观，便于手动触发；调度器触发走 run_module
    try:
        run = run_module(module_key, manual=True)
        return {"ok": True, "run_id": run.id, "status": run.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/modules/{module_id}")
def toggle_module(module_id: int, payload: ModuleToggleIn, session: Session = Depends(get_session)):
    module = session.get(Module, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="模块不存在")
    module.enabled = 1 if payload.enabled else 0
    session.commit()
    scheduler_manager.resync_jobs()
    return {"ok": True}


@router.post("/modules/create")
def create_module(payload: ModuleCreateIn, session: Session = Depends(get_session)):
    key = payload.key.strip()
    if not key or not re.fullmatch(r"[\w-]+", key):
        raise HTTPException(status_code=400, detail="key 只能包含字母、数字、下划线、连字符")
    try:
        data = yaml.safe_load(payload.yaml) or {}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {e}")
    if "key" not in data:
        data["key"] = key
    elif str(data["key"]) != key:
        raise HTTPException(status_code=400, detail=f"YAML 内 key({data['key']}) 与表单 key({key}) 不一致")
    try:
        parse_module_cfg(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"配置校验失败: {e}")

    target = settings.modules_dir / f"{key}.yaml"
    target.write_text(payload.yaml, encoding="utf-8")
    try:
        sync_module_file(session, target)
        session.commit()
        scheduler_manager.resync_jobs()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"同步失败: {e}")
    return {"ok": True, "key": key}


@router.get("/modules/{module_key}/yaml")
def get_module_yaml(module_key: str, session: Session = Depends(get_session)):
    module = session.execute(select(Module).where(Module.key == module_key)).scalar_one_or_none()
    if module is None:
        raise HTTPException(status_code=404, detail="模块不存在")
    return {"key": module.key, "yaml": module.config_yaml or ""}


@router.get("/sources")
def list_sources(session: Session = Depends(get_session)):
    sources = list(session.execute(select(Source).order_by(Source.module_id, Source.id)).scalars())
    return [
        {
            "id": s.id,
            "module_id": s.module_id,
            "module_key": s.module.key if s.module else None,
            "name": s.name,
            "type": s.type,
            "url": s.url,
            "base_weight": s.base_weight,
            "rating_avg": s.rating_avg,
            "rating_count": s.rating_count,
            "effective_rating": round(get_source_effective_rating(s), 3),
            "is_paused": bool(s.is_paused),
            "last_fetch_at": s.last_fetch_at.isoformat() if s.last_fetch_at else None,
            "last_error": s.last_error,
        }
        for s in sources
    ]


@router.get("/items")
def list_items(module_key: str | None = None, limit: int = 50, session: Session = Depends(get_session)):
    query = select(Item).order_by(desc(Item.fetched_at)).limit(min(limit, 200))
    if module_key:
        query = query.join(Module).where(Module.key == module_key).order_by(desc(Item.fetched_at)).limit(min(limit, 200))
    items = list(session.execute(query).scalars())
    return [
        {
            "id": it.id,
            "module_key": it.module.key if it.module else None,
            "source_name": it.source.name if it.source else None,
            "source_id": it.source_id,
            "title": it.title,
            "url": it.url,
            "summary": (it.summary or "")[:200],
            "lifetime": it.lifetime,
            "status": it.status,
            "llm_score": it.llm_score,
            "final_score": it.final_score,
            "fetched_at": it.fetched_at.isoformat() if it.fetched_at else None,
        }
        for it in items
    ]


@router.get("/runs")
def list_runs(module_key: str | None = None, limit: int = 30, session: Session = Depends(get_session)):
    query = select(RunRecord).order_by(desc(RunRecord.started_at)).limit(min(limit, 200))
    if module_key:
        query = query.join(Module).where(Module.key == module_key).order_by(desc(RunRecord.started_at)).limit(min(limit, 200))
    runs = list(session.execute(query).scalars())
    return [
        {
            "id": r.id,
            "module_key": r.module_id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "fetched_count": r.fetched_count,
            "after_dedup_count": r.after_dedup_count,
            "after_filter_count": r.after_filter_count,
            "selected_count": r.selected_count,
            "pushed_count": r.pushed_count,
            "error_msg": r.error_msg,
        }
        for r in runs
    ]


@router.post("/feedback")
def create_feedback(payload: FeedbackIn, session: Session = Depends(get_session)):
    try:
        fb = apply_feedback(
            session,
            source_id=payload.source_id,
            item_id=payload.item_id,
            module_id=payload.module_id,
            feedback_type=payload.feedback_type,
            rating=payload.rating,
        )
        return {"ok": True, "id": fb.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
