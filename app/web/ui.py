"""服务端渲染页面。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.db import get_session
from app.models.models import Item, Module, PushRecord, RunRecord, Source

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _value_score(llm_output: str | None) -> str:
    if not llm_output:
        return "-"
    try:
        data = json.loads(llm_output)
    except (json.JSONDecodeError, TypeError):
        return "-"
    v = data.get("value", data.get("score"))
    try:
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return "-"


templates.env.filters["value_score"] = _value_score


@router.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    modules = list(session.execute(select(Module).order_by(Module.id)).scalars())
    module_stats = []
    for m in modules:
        source_count = session.execute(select(func.count(Source.id)).where(Source.module_id == m.id)).scalar_one()
        last_run = session.execute(select(RunRecord).where(RunRecord.module_id == m.id).order_by(desc(RunRecord.started_at)).limit(1)).scalar_one_or_none()
        module_stats.append({"module": m, "source_count": source_count, "last_run": last_run})
    runs = list(session.execute(select(RunRecord).order_by(desc(RunRecord.started_at)).limit(20)).scalars())
    items = list(session.execute(select(Item).order_by(desc(Item.fetched_at)).limit(20)).scalars())
    return templates.TemplateResponse(request, "index.html", {
        "module_stats": module_stats, "runs": runs, "items": items,
    })


@router.get("/modules")
def modules_page(request: Request, session: Session = Depends(get_session)):
    modules = list(session.execute(select(Module).order_by(Module.id)).scalars())
    module_stats = []
    for m in modules:
        source_count = session.execute(select(func.count(Source.id)).where(Source.module_id == m.id)).scalar_one()
        last_run = session.execute(select(RunRecord).where(RunRecord.module_id == m.id).order_by(desc(RunRecord.started_at)).limit(1)).scalar_one_or_none()
        sources = list(session.execute(select(Source).where(Source.module_id == m.id).order_by(Source.id)).scalars())
        module_stats.append({"module": m, "source_count": source_count, "last_run": last_run, "sources": sources})
    return templates.TemplateResponse(request, "modules.html", {"module_stats": module_stats})


@router.get("/sources")
def sources_page(request: Request, session: Session = Depends(get_session)):
    sources = list(session.execute(select(Source).order_by(Source.module_id, Source.id)).scalars())
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})


@router.get("/digest")
def digest_page(request: Request, session: Session = Depends(get_session)):
    rows = session.execute(
        select(PushRecord, Item, Module)
        .join(Item, PushRecord.item_id == Item.id)
        .join(Module, Item.module_id == Module.id)
        .order_by(desc(PushRecord.pushed_at))
        .limit(200)
    ).all()
    digests = [
        {
            "module": module,
            "item": item,
            "channel": rec.channel,
            "pushed_at": rec.pushed_at,
            "status": rec.status,
        }
        for rec, item, module in rows
    ]
    return templates.TemplateResponse(request, "digest.html", {"digests": digests})


@router.get("/runs")
def runs_page(request: Request, session: Session = Depends(get_session)):
    runs = list(session.execute(select(RunRecord).order_by(desc(RunRecord.started_at)).limit(100)).scalars())
    module_names = {m.id: m.name for m in session.execute(select(Module)).scalars()}
    return templates.TemplateResponse(request, "runs.html", {"runs": runs, "module_names": module_names})


@router.get("/feedback")
def feedback_page(request: Request, session: Session = Depends(get_session)):
    items = list(session.execute(
        select(Item).where(Item.status.in_(["pushed", "selected", "new"]))
        .order_by(desc(Item.fetched_at)).limit(50)
    ).scalars())
    sources = list(session.execute(select(Source).order_by(Source.module_id, Source.id)).scalars())
    return templates.TemplateResponse(request, "feedback.html", {"items": items, "sources": sources})
