"""学习平台 API —— 供 test1 前端调用。

提供四组能力：
  1. /api/study/knowledge  知识条目（论文/博客），解析 items.llm_output 取出 LLM 生成的摘要、要点、标签
  2. /api/study/today      今日计划（解析 plan/daily/ 最新日报）
  3. /api/study/checkin    打卡读写（落 checkins 表 + 回写日报 md，双写保证单一事实来源）
  4. /api/study/courses    课程资料

设计原则（见 AGENTS.md）：
  - 数据库是持久状态；md 是给人看的事实来源。打卡时两者同步更新。
  - 禁止编造：LLM 没生成的内容就返回空，前端显示"暂无摘要"。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.models.db import get_session
from app.models.models import CheckIn, Course, Item, Module

router = APIRouter(prefix="/api/study", tags=["study"])

# plan 目录：项目根/plan
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = PROJECT_ROOT / "plan"
DAILY_DIR = PLAN_DIR / "daily"

# 状态符号 <-> 数据库 status 双向映射（与 AGENTS.md 7.3 节一致）
STATUS_TO_MARK = {"done": "x", "todo": " ", "partial": "!", "blocked": "?"}
MARK_TO_STATUS = {"x": "done", " ": "todo", "": "todo", "!": "partial", "?": "blocked"}

# 打卡项分类 -> md 里的行首关键字（用于回写时定位行）
CATEGORY_LABELS = {
    "ai-infra": "AI Infra",
    "paper": "论文",
    "interview": "面经",
    "drone": "横向",
    "blocker": "卡点",
}


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def _parse_llm_output(raw: str | None) -> dict[str, Any]:
    """解析 items.llm_output（LLM 批量筛选的 JSON 输出）。

    返回 {summary, reason, tags, score, value, relevant}；解析失败返回空字典。
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {
            "summary": data.get("summary") or "",
            "reason": data.get("reason") or "",
            "tags": data.get("tags") or [],
            "score": data.get("score"),
            "value": data.get("value"),
            "relevant": data.get("relevant"),
        }
    except (json.JSONDecodeError, TypeError):
        return {}


def _item_to_knowledge(item: Item, module_name: str = "") -> dict[str, Any]:
    """把 Item 转成前端知识卡片。

    优先级：LLM 生成的中文摘要 > 数据库 summary > 正文截断。
    原链接始终附在最后（松的要求：先展示加工过的内容，想深入再跳原链接）。
    """
    llm = _parse_llm_output(item.llm_output)
    ai_summary = (llm.get("summary") or "").strip()
    fallback = (item.summary or "").strip()
    body = (item.raw_content or "").strip()

    return {
        "id": item.id,
        "title": item.title or "(无标题)",
        "url": item.url or "",
        "module": module_name,
        "module_id": item.module_id,
        # 三个层级的摘要，前端按需选用
        "ai_summary": ai_summary,                       # LLM 中文摘要（首选）
        "origin_summary": fallback,                     # RSS 原文摘要
        "body_excerpt": body[:600] + ("..." if len(body) > 600 else ""),
        # LLM 的判断
        "reason": llm.get("reason") or "",              # 为什么值得看
        "tags": llm.get("tags") or [],
        "score": llm.get("score") if llm.get("score") is not None else item.llm_score,
        "value": llm.get("value"),
        "final_score": item.final_score,
        "status": item.status,
        "author": item.author or "",
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
        "has_ai_summary": bool(ai_summary),             # 前端据此决定是否显示"暂无摘要"
    }


def _latest_daily_md() -> Path | None:
    """找 plan/daily/ 下最新的日报（按文件名日期倒序，排除 -sources.md）。"""
    if not DAILY_DIR.exists():
        return None
    candidates = [
        p for p in DAILY_DIR.glob("*.md")
        if re.match(r"\d{4}-\d{2}-\d{2}(-\d+)?\.md$", p.name)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def _parse_section(content: str, heading: str) -> str:
    """提取 md 中某个 ## 标题下的正文（到下一个 ## 为止）。"""
    pattern = rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, content, re.M | re.S)
    return m.group(1).strip() if m else ""


def _parse_checklist(section: str) -> list[dict[str, Any]]:
    """解析 md 里的 checkbox 行 -> [{mark, text, status}]。"""
    out = []
    for line in section.splitlines():
        m = re.match(r"^\s*-\s*\[(.)\]\s*(.*)$", line)
        if m:
            mark, text = m.group(1), m.group(2).strip()
            out.append({"mark": mark, "text": text, "status": MARK_TO_STATUS.get(mark, "todo")})
    return out


def _split_md_row(line: str) -> list[str]:
    """拆分一行 md 表格，处理单元格内的转义竖线 \\|。"""
    cells = re.split(r"(?<!\\)\|", line.strip())
    # 首尾空串是边框竖线产生的
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.replace("\\|", "|").strip() for c in cells]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def _parse_md_table(section: str) -> dict[str, Any]:
    """解析 md 表格 -> {headers: [...], rows: [[...]]}。

    取该段中第一个表格；无表格返回空结构。
    """
    rows: list[list[str]] = []
    headers: list[str] = []
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if rows:
                break  # 表格结束
            continue
        cells = _split_md_row(s)
        if _is_separator_row(cells):
            continue
        if not headers:
            headers = cells
        else:
            rows.append(cells)
    return {"headers": headers, "rows": rows} if headers else {"headers": [], "rows": []}


def _rewrite_md_checklist(md_path: Path, updates: dict[str, dict[str, str]]) -> bool:
    """把打卡状态回写进日报 md 的「今日打卡」段。

    updates: {category: {"status": "done", "note": "..."}}
    按 CATEGORY_LABELS 的关键字定位行；找不到对应行就不改，返回 False。
    """
    try:
        content = md_path.read_text(encoding="utf-8")
    except OSError:
        return False

    lines = content.splitlines(keepends=True)
    in_section = False
    changed = False

    for i, line in enumerate(lines):
        if re.match(r"^##\s+", line):
            in_section = bool(re.match(r"^##\s+今日打卡", line))
            continue
        if not in_section:
            continue

        m = re.match(r"^(\s*-\s*\[)(.)(\]\s*)(.*)$", line)
        if not m:
            continue

        text = m.group(4)
        for category, label in CATEGORY_LABELS.items():
            if category not in updates:
                continue
            if not text.startswith(label):
                continue

            upd = updates[category]
            new_mark = STATUS_TO_MARK.get(upd.get("status", "todo"), " ")
            note = (upd.get("note") or "").strip()

            # 保留原文本主干，剥离旧的说明（以"——"或"｜"接续的部分）
            main_text = re.split(r"[—–|]", text)[0].strip().rstrip("：:").strip()
            new_text = f"{main_text}"
            if note:
                new_text += f" —— {note}"
            lines[i] = f"{m.group(1)}{new_mark}{m.group(3)}{new_text}\n"
            changed = True
            break

    if changed:
        try:
            md_path.write_text("".join(lines), encoding="utf-8")
        except OSError:
            return False
    return changed


# --------------------------------------------------------------------------
# 1. 知识条目
# --------------------------------------------------------------------------

@router.get("/knowledge")
def list_knowledge(
    module_key: str | None = None,
    limit: int = 50,
    has_ai: bool = False,
    q: str | None = None,
    session: Session = Depends(get_session),
):
    """知识条目列表。默认按入库时间倒序。

    has_ai=true 只返回有 LLM 摘要的；q 在标题/摘要里做关键词过滤。
    """
    stmt = session.query(Item, Module.name).outerjoin(Module, Item.module_id == Module.id)
    if module_key:
        stmt = stmt.filter(Module.key == module_key)
    rows = stmt.order_by(desc(Item.id)).limit(limit * 3).all()

    items = [_item_to_knowledge(it, name or "") for it, name in rows]

    if has_ai:
        items = [x for x in items if x["has_ai_summary"]]
    if q:
        kw = q.lower()
        items = [
            x for x in items
            if kw in x["title"].lower()
            or kw in (x["ai_summary"] or "").lower()
            or kw in (x["origin_summary"] or "").lower()
            or any(kw in t.lower() for t in x["tags"])
        ]

    total = len(items)
    return {"total": total, "items": items[:limit]}


@router.get("/knowledge/{item_id}")
def get_knowledge(item_id: int, session: Session = Depends(get_session)):
    """单条知识详情（含正文全文）。"""
    row = (
        session.query(Item, Module.name)
        .outerjoin(Module, Item.module_id == Module.id)
        .filter(Item.id == item_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="条目不存在")
    item, name = row
    data = _item_to_knowledge(item, name or "")
    data["body"] = item.raw_content or ""
    return data


# --------------------------------------------------------------------------
# 2. 今日计划
# --------------------------------------------------------------------------

@router.get("/today")
def get_today(target_date: str | None = None):
    """今日计划：从 plan/daily/ 最新日报解析出三件事与打卡清单。

    target_date 可指定某天（YYYY-MM-DD），默认取最新一份日报。
    """
    if target_date:
        md_path = DAILY_DIR / f"{target_date}.md"
        if not md_path.exists():
            # 兼容 -2.md 这类重名文件
            alt = sorted(DAILY_DIR.glob(f"{target_date}*.md"))
            md_path = alt[0] if alt else None
    else:
        md_path = _latest_daily_md()

    if not md_path or not md_path.exists():
        return {"date": target_date or date.today().isoformat(), "exists": False,
                "plan": [], "checklist": [], "summary": "", "source_file": None}

    content = md_path.read_text(encoding="utf-8")
    date_str = re.match(r"(\d{4}-\d{2}-\d{2})", md_path.name)
    plan_section = _parse_section(content, "今日三件事")
    check_section = _parse_section(content, "今日打卡")
    plan_table = _parse_md_table(plan_section)

    return {
        "date": date_str.group(1) if date_str else target_date,
        "exists": True,
        "source_file": md_path.name,
        # 不截断：截断会破坏 md 表格/列表结构，前端按 md 渲染
        "commit": _parse_section(content, "昨日承诺"),
        "summary": _parse_section(content, "昨日结果"),
        "plan_table": plan_table,
        "plan_raw": plan_section,
        "checklist": _parse_checklist(check_section),
        "tomorrow": _parse_section(content, "明日预告"),
    }


# --------------------------------------------------------------------------
# 3. 打卡
# --------------------------------------------------------------------------

class CheckInItem(BaseModel):
    category: str = Field(..., description="ai-infra/paper/interview/drone/blocker")
    title: str | None = None
    status: str = Field("todo", description="done/todo/partial/blocked")
    note: str | None = None


class CheckInPayload(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    items: list[CheckInItem]


@router.get("/checkin")
def get_checkin(date_str: str | None = None, session: Session = Depends(get_session)):
    """读某天打卡记录。没传日期就取今天。"""
    d = date_str or date.today().isoformat()
    rows = session.query(CheckIn).filter(CheckIn.date == d).all()
    return {
        "date": d,
        "items": [
            {
                "category": r.category,
                "title": r.title,
                "status": r.status,
                "note": r.note,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
    }


@router.post("/checkin")
def save_checkin(payload: CheckInPayload, session: Session = Depends(get_session)):
    """保存打卡：写 checkins 表 + 回写 plan/daily/<date>.md。

    双写保证：数据库供程序查询与统计，md 保持给人看的事实来源。
    """
    d = payload.date
    saved = []
    updates: dict[str, dict[str, str]] = {}

    for it in payload.items:
        row = session.query(CheckIn).filter(
            CheckIn.date == d, CheckIn.category == it.category
        ).first()

        if row:
            row.status = it.status
            row.note = it.note
            row.title = it.title or row.title
            row.updated_at = datetime.now()
        else:
            row = CheckIn(
                date=d,
                category=it.category,
                title=it.title or CATEGORY_LABELS.get(it.category, it.category),
                status=it.status,
                note=it.note,
            )
            session.add(row)
        saved.append({"category": it.category, "status": it.status})
        updates[it.category] = {"status": it.status, "note": it.note or ""}

    session.commit()

    # 回写 md
    md_written = False
    md_path = DAILY_DIR / f"{d}.md"
    if not md_path.exists():
        alt = sorted(DAILY_DIR.glob(f"{d}*.md"))
        md_path = alt[0] if alt else None
    if md_path and md_path.exists():
        md_written = _rewrite_md_checklist(md_path, updates)

    return {"ok": True, "date": d, "saved": saved, "md_written": md_written,
            "md_file": md_path.name if md_path and md_path.exists() else None}


@router.get("/checkin/stats")
def checkin_stats(days: int = 30, session: Session = Depends(get_session)):
    """近 N 天打卡统计：各分类完成率（供前端展示长期趋势）。"""
    rows = session.query(CheckIn).order_by(desc(CheckIn.date)).limit(days * 6).all()
    by_cat: dict[str, dict[str, int]] = {}
    for r in rows:
        c = by_cat.setdefault(r.category, {"done": 0, "total": 0})
        c["total"] += 1
        if r.status == "done":
            c["done"] += 1
    return {
        "days": days,
        "by_category": {
            k: {"done": v["done"], "total": v["total"],
                "rate": round(v["done"] / v["total"] * 100) if v["total"] else 0}
            for k, v in by_cat.items()
        },
    }


# --------------------------------------------------------------------------
# 4. 课程资料
# --------------------------------------------------------------------------

class CourseIn(BaseModel):
    title: str
    provider: str | None = None
    url: str | None = None
    description: str | None = None
    track: str = "ai-infra"
    phase: str | None = None
    resources: list[dict[str, str]] | None = None
    status: str = "未开始"
    progress: int = 0


@router.get("/courses")
def list_courses(track: str | None = None, session: Session = Depends(get_session)):
    stmt = session.query(Course).order_by(Course.phase, Course.id)
    if track:
        stmt = stmt.filter(Course.track == track)
    rows = stmt.all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "provider": c.provider,
                "url": c.url,
                "description": c.description,
                "track": c.track,
                "phase": c.phase,
                "resources": json.loads(c.resources) if c.resources else [],
                "status": c.status,
                "progress": c.progress,
            }
            for c in rows
        ],
    }


@router.post("/courses")
def create_course(payload: CourseIn, session: Session = Depends(get_session)):
    c = Course(
        title=payload.title,
        provider=payload.provider,
        url=payload.url,
        description=payload.description,
        track=payload.track,
        phase=payload.phase,
        resources=json.dumps(payload.resources or [], ensure_ascii=False),
        status=payload.status,
        progress=payload.progress,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return {"ok": True, "id": c.id}


@router.put("/courses/{course_id}")
def update_course(course_id: int, payload: CourseIn, session: Session = Depends(get_session)):
    c = session.query(Course).filter(Course.id == course_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    c.title = payload.title
    c.provider = payload.provider
    c.url = payload.url
    c.description = payload.description
    c.track = payload.track
    c.phase = payload.phase
    c.resources = json.dumps(payload.resources or [], ensure_ascii=False)
    c.status = payload.status
    c.progress = payload.progress
    session.commit()
    return {"ok": True, "id": c.id}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, session: Session = Depends(get_session)):
    c = session.query(Course).filter(Course.id == course_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    session.delete(c)
    session.commit()
    return {"ok": True}