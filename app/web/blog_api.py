"""个人博客 / 知识库 API —— 本地 md 文档树。

设计取舍：
  - **目录即事实来源**。`blog/` 下的真实目录结构就是唯一的组织方式，不做额外索引
    文件，从根上避免"索引与磁盘不一致"这种经典故障。
  - **元信息写在 YAML front matter 里**（title / tags / item_id），文档本身自解释，
    拷走、换工具、直接用 Obsidian 打开都还能读。
  - **收藏笔记不是另一套东西**。它只是 `blog/收藏笔记/<id>-<slug>.md`，front matter
    里多一个 `item_id`，于是在博客里能反查回知识卡片，在收藏里能一键跳到文档。

路由前缀 /api/study/blog：
  GET    /tree              目录树
  GET    /doc?path=         读单篇（含 front matter 解析 + 关联知识卡片）
  PUT    /doc               写单篇（自动建父目录）
  POST   /folder            新建目录
  POST   /rename            重命名 / 移动
  DELETE /node?path=        删除（目录递归删）
  GET    /note/{item_id}    读某条收藏的笔记（不存在也返回建议路径）
  PUT    /note/{item_id}    写某条收藏的笔记（不存在则按模板创建）
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.db import get_session
from app.models.models import Item, Module, Source
from app.web.study_api import _item_to_knowledge

router = APIRouter(prefix="/api/study/blog", tags=["blog"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOG_ROOT = PROJECT_ROOT / "blog"
NOTE_DIRNAME = "收藏笔记"          # 收藏笔记固定落在这一层，便于识别
NOTE_DIR = BLOG_ROOT / NOTE_DIRNAME

# 「每日计划」虚拟节点：plan/daily/*.md 由日报系统管理，博客侧只读
PLAN_DAILY_ROOT = PROJECT_ROOT / "plan" / "daily"
VIRTUAL_PLAN_PREFIX = "__virtual__:plan_daily__"
VIRTUAL_PLAN_LABEL = "每日计划"

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_ILLEGAL_CHARS = re.compile(r"[\\/:*?\"<>|\r\n\t]")


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------

def _is_virtual_plan(path: str) -> bool:
    return path.startswith(VIRTUAL_PLAN_PREFIX)


def _resolve_virtual(rel: str) -> Path:
    """把虚拟路径解析成 plan/daily 下的绝对路径。"""
    stripped = rel[len(VIRTUAL_PLAN_PREFIX):].lstrip("/")
    if not stripped:
        return PLAN_DAILY_ROOT.resolve()
    return (PLAN_DAILY_ROOT / stripped).resolve()


def _safe_path(rel: str, *, allow_root: bool = False) -> Path:
    """把前端传来的相对路径解析成 BLOG_ROOT 内的绝对路径。

    防目录穿越：解析后必须仍在 BLOG_ROOT 内部，否则 400。
    虚拟节点（plan/daily 下的日报）跳过此检查，由调用方决定是否允许。
    """
    rel = (rel or "").strip().strip("/\\")
    if not rel:
        if allow_root:
            return BLOG_ROOT
        raise HTTPException(status_code=400, detail="路径为空")

    # 虚拟路径：直接解析到 plan/daily，但仍要做路径合法性检查
    if _is_virtual_plan(rel):
        target = _resolve_virtual(rel)
        plan_root = PLAN_DAILY_ROOT.resolve()
        if target != plan_root and plan_root not in target.parents:
            raise HTTPException(status_code=400, detail=f"非法虚拟路径：{rel}")
        return target

    target = (BLOG_ROOT / rel).resolve()
    root = BLOG_ROOT.resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail=f"非法路径：{rel}")
    if target == root and not allow_root:
        raise HTTPException(status_code=400, detail="不能对根目录做此操作")
    return target


def _virtual_only_error(rel: str) -> HTTPException | None:
    """虚拟节点不允许写操作。返回 None 表示不是虚拟路径。"""
    if _is_virtual_plan(rel):
        return HTTPException(
            status_code=403,
            detail="每日计划由日报系统管理，博客侧只读，不允许编辑/删除/重命名",
        )
    return None


def _ensure_blog_root() -> None:
    BLOG_ROOT.mkdir(parents=True, exist_ok=True)
    NOTE_DIR.mkdir(parents=True, exist_ok=True)


def _slug(text: str, limit: int = 36) -> str:
    """把标题压成可用作文件名的短串，中文保留。"""
    s = _ILLEGAL_CHARS.sub("", text or "")
    s = re.sub(r"\s+", "-", s.strip())
    return s[:limit].strip("-") or "untitled"


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """拆出 YAML front matter。没有或解析失败都返回空 dict，不抛异常。"""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[m.end():]


def _dump_front_matter(meta: dict[str, Any]) -> str:
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    if not meta:
        return ""
    body = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{body}\n---\n"


def _norm_tags(tags: Any) -> list[str]:
    if isinstance(tags, str):
        return [t.strip() for t in re.split(r"[,，]", tags) if t.strip()]
    if isinstance(tags, list):
        return [str(t).strip() for t in tags if str(t).strip()]
    return []


def _rel(path: Path) -> str:
    return path.relative_to(BLOG_ROOT).as_posix()


def _read_doc(path: Path) -> tuple[dict[str, Any], str, str]:
    """返回 (meta, body, raw)。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _split_front_matter(raw)
    return meta, body, raw


def _file_node(path: Path) -> dict[str, Any]:
    meta, body, _ = _read_doc(path)
    stat = path.stat()
    return {
        "type": "file",
        "name": path.name,
        "title": str(meta.get("title") or path.stem),
        "path": _rel(path),
        "tags": _norm_tags(meta.get("tags")),
        "item_id": meta.get("item_id"),
        "source": "blog",
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "size": stat.st_size,
        "excerpt": re.sub(r"\s+", " ", body)[:110],
    }


def _infer_title_from_body(body: str, fallback: str) -> str:
    """从正文首行 `# xxx` 提取标题，日报没有 front matter 时用。"""
    for line in body.splitlines():
        m = re.match(r"#\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _plan_daily_file_node(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _split_front_matter(raw)
    stat = path.stat()
    title = (meta.get("title") if isinstance(meta, dict) else None) or _infer_title_from_body(body, path.stem)
    return {
        "type": "file",
        "name": path.name,
        "title": str(title),
        "path": f"{VIRTUAL_PLAN_PREFIX}/{path.name}",
        "tags": _norm_tags(meta.get("tags")) if isinstance(meta, dict) else [],
        "item_id": None,
        "source": "plan_daily",
        "virtual": True,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "size": stat.st_size,
        "excerpt": re.sub(r"\s+", " ", body)[:110] if body else "",
    }


def _build_plan_daily_tree() -> list[dict[str, Any]]:
    """plan/daily/*.md 作为「每日计划」虚拟目录的子节点。"""
    if not PLAN_DAILY_ROOT.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(PLAN_DAILY_ROOT.glob("*.md"), key=lambda x: x.name.lower()):
        try:
            out.append(_plan_daily_file_node(p))
        except OSError:
            continue
    out.sort(key=lambda n: n["name"], reverse=True)   # 日期倒序
    return out


def _build_tree(dir_path: Path) -> list[dict[str, Any]]:
    """递归构造目录树：目录在前、文件在后，各自按名排序。"""
    out: list[dict[str, Any]] = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return out

    for p in entries:
        if p.name.startswith("."):
            continue
        if p.is_dir():
            out.append({
                "type": "dir",
                "name": p.name,
                "path": _rel(p),
                "children": _build_tree(p),
            })
        elif p.suffix.lower() == ".md":
            out.append(_file_node(p))
    return out


def _linked_item(item_id: Any, session: Session) -> dict[str, Any] | None:
    """取关联的知识卡片；条目不存在或 id 非法都返回 None，不报错。"""
    try:
        iid = int(item_id)
    except (TypeError, ValueError):
        return None
    row = (
        session.query(Item, Module.name, Source.name)
        .outerjoin(Module, Item.module_id == Module.id)
        .outerjoin(Source, Item.source_id == Source.id)
        .filter(Item.id == iid)
        .first()
    )
    if not row:
        return None
    item, mname, sname = row
    return _item_to_knowledge(item, mname or "", sname or "")


# --------------------------------------------------------------------------
# 目录树
# --------------------------------------------------------------------------

@router.get("/tree")
def get_tree():
    _ensure_blog_root()
    tree = _build_tree(BLOG_ROOT)

    # 注入「每日计划」虚拟目录（plan/daily/*.md，只读）
    plan_files = _build_plan_daily_tree()
    if plan_files:
        tree.insert(0, {
            "type": "dir",
            "name": VIRTUAL_PLAN_LABEL,
            "path": VIRTUAL_PLAN_PREFIX,
            "source": "plan_daily",
            "virtual": True,
            "children": plan_files,
        })

    return {
        "root": BLOG_ROOT.name,
        "note_dir": NOTE_DIRNAME,
        "plan_label": VIRTUAL_PLAN_LABEL,
        "tree": tree,
    }


# --------------------------------------------------------------------------
# 单篇文档
# --------------------------------------------------------------------------

@router.get("/doc")
def get_doc(path: str, session: Session = Depends(get_session)):
    virtual = _is_virtual_plan(path)
    p = _safe_path(path)
    if p.is_dir():
        raise HTTPException(status_code=400, detail="这是一个目录")
    if not p.exists():
        raise HTTPException(status_code=404, detail="文档不存在")

    meta, body, raw = _read_doc(p)
    stat = p.stat()
    # 虚拟日报没 front matter 时，从正文首行 `# xxx` 推断标题
    raw_title = meta.get("title")
    if virtual or not raw_title:
        inferred = _infer_title_from_body(body, p.stem)
        if virtual:
            title = inferred
        else:
            title = str(raw_title or inferred)
    else:
        title = str(raw_title)

    return {
        "path": path if virtual else _rel(p),
        "title": title,
        "tags": _norm_tags(meta.get("tags")),
        "item_id": meta.get("item_id") if not virtual else None,
        "content": body,                 # 正文（不含 front matter）
        "raw": raw,                      # 含 front matter 的完整原文
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "item": None if virtual else _linked_item(meta.get("item_id"), session),
        "source": "plan_daily" if virtual else "blog",
        "read_only": virtual,
    }


class DocPayload(BaseModel):
    path: str = Field(..., description="相对 blog/ 的路径，如 ai-infra/cuda.md")
    content: str = ""
    title: str | None = None
    tags: list[str] | str | None = None
    item_id: int | None = None


@router.put("/doc")
def put_doc(payload: DocPayload):
    if (e := _virtual_only_error(payload.path)) is not None:
        raise e
    p = _safe_path(payload.path)
    if p.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="只支持 .md 文档")
    p.parent.mkdir(parents=True, exist_ok=True)

    # 保留已有 front matter 里的其它字段，只覆盖本次传来的
    meta: dict[str, Any] = {}
    if p.exists():
        old_meta, _, _ = _read_doc(p)
        meta.update(old_meta)

    if payload.title is not None:
        meta["title"] = payload.title
    if payload.tags is not None:
        meta["tags"] = _norm_tags(payload.tags)
    if payload.item_id is not None:
        meta["item_id"] = payload.item_id
    meta["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    p.write_text(_dump_front_matter(meta) + payload.content, encoding="utf-8")
    return {"ok": True, "path": _rel(p), "title": meta.get("title") or p.stem}


# --------------------------------------------------------------------------
# 目录 / 重命名 / 删除
# --------------------------------------------------------------------------

class PathPayload(BaseModel):
    path: str


class RenamePayload(BaseModel):
    path: str
    new_path: str


@router.post("/folder")
def create_folder(payload: PathPayload):
    p = _safe_path(payload.path, allow_root=True)
    if p.exists() and not p.is_dir():
        raise HTTPException(status_code=400, detail="同名文件已存在")
    p.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": _rel(p)}


@router.post("/rename")
def rename_node(payload: RenamePayload):
    if (e := _virtual_only_error(payload.path)) is not None:
        raise e
    if (e := _virtual_only_error(payload.new_path)) is not None:
        raise e
    src = _safe_path(payload.path)
    dst = _safe_path(payload.new_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail="源路径不存在")
    if dst.exists():
        raise HTTPException(status_code=400, detail="目标路径已存在")
    if src.suffix.lower() == ".md" and dst.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="文档重命名需保持 .md 后缀")

    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"ok": True, "path": _rel(dst)}


@router.delete("/node")
def delete_node(path: str):
    if (e := _virtual_only_error(path)) is not None:
        raise e
    p = _safe_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True, "path": _rel(p)}


# --------------------------------------------------------------------------
# 收藏条目的笔记
# --------------------------------------------------------------------------

class NotePayload(BaseModel):
    content: str = ""


def _note_path(item: Item) -> Path:
    return NOTE_DIR / f"{item.id}-{_slug(item.title)}.md"


def _note_template(item: Item) -> str:
    return (
        f"# 笔记：{item.title}\n\n"
        f"> 来源：{item.url or '（无链接）'}\n\n"
        f"## 一句话概括\n\n\n"
        f"## 我的想法\n\n\n"
        f"## 能怎么用\n\n\n"
    )


@router.get("/note/{item_id}")
def get_note(item_id: int, session: Session = Depends(get_session)):
    """读某条收藏的笔记。不存在时返回 exists=false 和建议路径，供前端决定是否创建。"""
    item = session.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")

    p = _note_path(item)
    if not p.exists():
        return {
            "item_id": item_id,
            "exists": False,
            "path": _rel(p),
            "title": f"笔记：{item.title}",
            "content": "",
            "item": _linked_item(item_id, session),
        }

    meta, body, _ = _read_doc(p)
    return {
        "item_id": item_id,
        "exists": True,
        "path": _rel(p),
        "title": str(meta.get("title") or p.stem),
        "content": body,
        "updated_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        "item": _linked_item(item_id, session),
    }


@router.put("/note/{item_id}")
def put_note(item_id: int, payload: NotePayload, session: Session = Depends(get_session)):
    """写笔记。文件不存在时先按模板创建，再写入。"""
    item = session.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")

    p = _note_path(item)
    NOTE_DIR.mkdir(parents=True, exist_ok=True)

    meta: dict[str, Any] = {}
    if p.exists():
        old, _, _ = _read_doc(p)
        meta.update(old)
    meta.update({
        "title": meta.get("title") or f"笔记：{item.title}",
        "item_id": item_id,
        "source_url": item.url or "",
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

    content = payload.content if payload.content.strip() else _note_template(item)
    p.write_text(_dump_front_matter(meta) + content, encoding="utf-8")
    return {"ok": True, "path": _rel(p), "item_id": item_id}
