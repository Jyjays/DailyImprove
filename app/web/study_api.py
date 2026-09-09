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
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.models.db import get_session
from app.models.models import CheckIn, Course, Favorite, Item, Module, Source

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

# 知识条目的类型：论文 / 新闻 / 博客
KIND_LABELS = {"paper": "论文", "news": "新闻", "blog": "博客"}
KIND_ORDER = ["paper", "news", "blog"]

# 判定依据（先 URL 域名，再来源名，最后标题特征）
_PAPER_HOSTS = (
    "arxiv.org", "openreview.net", "pmlr.press", "proceedings.mlr.press",
    "dl.acm.org", "acm.org", "neurips.cc", "jmlr.org", "biorxiv.org",
    "ieeexplore.ieee.org", "link.springer.com", "sciencedirect.com", "nature.com",
)
_NEWS_HOSTS = (
    "news.ycombinator.com", "hnrss.org", "jiqizhixin.com", "qbitai.com",
    "36kr.com", "infoq.cn", "ithome.com", "leiphone.com", "syncedreview.com",
    "techcrunch.com", "theverge.com", "venturebeat.com",
)
_PAPER_NAME_KEYS = ("arxiv", "论文", "paper", "preprint")
_NEWS_NAME_KEYS = ("hacker news", "hnrss", "快讯", "新闻", "机器之心", "量子位", "36氪", "infoq")

# arXiv 标题特征：[cs.CL] xxx  /  arXiv:2601.01234
_ARXIV_TITLE_RE = re.compile(r"(^\[[a-z]{2}\.[a-z]{2}\])|(arxiv:\d{4}\.\d{4,5})", re.I)


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


def _classify_kind(item: Item, source_name: str = "") -> str:
    """判定条目类型：paper / news / blog。

    依据优先级：URL 域名 > 来源名 > 标题特征 > 兜底 blog。
    判不出来时归为 blog（RSS 订阅源里博客占比最高），不猜测、不编造。
    """
    url = (item.url or "").lower()
    name = (source_name or "").lower()
    title = (item.title or "").lower()

    if any(h in url for h in _PAPER_HOSTS):
        return "paper"
    if any(h in url for h in _NEWS_HOSTS):
        return "news"
    if any(k in name for k in _PAPER_NAME_KEYS):
        return "paper"
    if any(k in name for k in _NEWS_NAME_KEYS):
        return "news"
    if _ARXIV_TITLE_RE.search(title or ""):
        return "paper"
    return "blog"


def _item_to_knowledge(
    item: Item,
    module_name: str = "",
    source_name: str = "",
    fav_ids: set[int] | None = None,
) -> dict[str, Any]:
    """把 Item 转成前端知识卡片。

    优先级：LLM 生成的中文摘要 > 数据库 summary > 正文截断。
    原链接始终附在最后（设计约定：先展示加工过的内容，想深入再跳原链接）。
    """
    llm = _parse_llm_output(item.llm_output)
    ai_summary = (llm.get("summary") or "").strip()
    fallback = (item.summary or "").strip()
    body = (item.raw_content or "").strip()

    # 展示日期：有发布时间用发布时间，否则用入库时间，并标注来源，避免误导
    if item.published_at:
        show_dt, date_source = item.published_at, "published"
    else:
        show_dt, date_source = item.fetched_at, "fetched"

    return {
        "id": item.id,
        "title": item.title or "(无标题)",
        "url": item.url or "",
        "module": module_name,
        "module_id": item.module_id,
        "kind": _classify_kind(item, source_name),
        "source_name": source_name or "",
        "date": show_dt.date().isoformat() if show_dt else None,
        "date_source": date_source,           # published=发布时间 / fetched=入库时间
        "is_favorite": bool(fav_ids and item.id in fav_ids),
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
    used: set[str] = set()  # 每个 category 只命中一次行

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
            if category in used:
                continue
            if category not in updates:
                continue
            if not text.startswith(label):
                continue

            used.add(category)
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
    kind: str | None = None,
    module_key: str | None = None,
    days: int = 7,
    q: str | None = None,
    has_ai: bool = False,
    favorite: bool = False,
    page: int = 1,
    page_size: int = 12,
    session: Session = Depends(get_session),
):
    """知识条目列表（分页）。

    days      默认 7，只返回近 N 天入库的；传 0 表示不限时间（收藏页用）。
    kind      paper / news / blog，不传即全部。
    favorite  true 时只返回已收藏的（此时 days 传 0 才能看到全部收藏）。
    page_size 默认 12，最多 50。
    """
    page = max(1, page)
    page_size = max(1, min(50, page_size))

    stmt = (
        session.query(Item, Module.name, Source.name)
        .outerjoin(Module, Item.module_id == Module.id)
        .outerjoin(Source, Item.source_id == Source.id)
    )
    if module_key:
        stmt = stmt.filter(Module.key == module_key)
    if days and days > 0:
        stmt = stmt.filter(Item.fetched_at >= datetime.now() - timedelta(days=days))
    if favorite:
        stmt = stmt.join(Favorite, Favorite.item_id == Item.id)

    # 上限防御：条目规模可控，但避免一次捞出整个库
    rows = stmt.order_by(desc(Item.id)).limit(5000).all()

    # 收藏集合一次查完，避免 N+1
    fav_ids = {r[0] for r in session.query(Favorite.item_id).all()}

    items = [_item_to_knowledge(it, name or "", sname or "", fav_ids) for it, name, sname in rows]

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

    # 类型计数：在「除类型外的其它筛选」之上统计，保证切换 tab 时数字稳定
    kind_counts: dict[str, int] = {"all": len(items)}
    for k in KIND_ORDER:
        kind_counts[k] = sum(1 for x in items if x["kind"] == k)

    if kind:
        items = [x for x in items if x["kind"] == kind]

    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "days": days,
        "kind": kind,
        "kind_counts": kind_counts,
        "favorite_count": len(fav_ids),
        "items": items[start:start + page_size],
    }


@router.post("/knowledge/{item_id}/favorite")
def toggle_favorite(item_id: int, session: Session = Depends(get_session)):
    """收藏 / 取消收藏。返回操作后的状态。"""
    if not session.query(Item).filter(Item.id == item_id).first():
        raise HTTPException(status_code=404, detail="条目不存在")

    fav = session.query(Favorite).filter(Favorite.item_id == item_id).first()
    if fav:
        session.delete(fav)
        session.commit()
        return {"id": item_id, "favorited": False}

    session.add(Favorite(item_id=item_id))
    session.commit()
    return {"id": item_id, "favorited": True}


@router.get("/knowledge/{item_id}")
def get_knowledge(item_id: int, session: Session = Depends(get_session)):
    """单条知识详情（含正文全文）。"""
    row = (
        session.query(Item, Module.name, Source.name)
        .outerjoin(Module, Item.module_id == Module.id)
        .outerjoin(Source, Item.source_id == Source.id)
        .filter(Item.id == item_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="条目不存在")
    item, name, sname = row
    fav_ids = {r[0] for r in session.query(Favorite.item_id).filter(Favorite.item_id == item_id).all()}
    data = _item_to_knowledge(item, name or "", sname or "", fav_ids)
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

    # 去重：同一 (date, category) 只保留最后一次出现的，防御前端重复提交
    seen: dict[str, int] = {}
    deduped: list[CheckInItem] = []
    for it in payload.items:
        if it.category in seen:
            deduped[seen[it.category]] = it
        else:
            seen[it.category] = len(deduped)
            deduped.append(it)

    for it in deduped:
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