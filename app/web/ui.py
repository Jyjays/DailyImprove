"""服务端渲染页面。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.db import get_session
from app.models.models import Item, Module, RunRecord, Source

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


@router.get("/sources")
def sources_page(request: Request, session: Session = Depends(get_session)):
    sources = list(session.execute(select(Source).order_by(Source.module_id, Source.id)).scalars())
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})
