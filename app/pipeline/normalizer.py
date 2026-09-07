from __future__ import annotations

from datetime import datetime

from app.models.models import Item, Source
from app.plugins.base import RawItem, SourceContext
from app.schemas import ModuleCfg
from app.utils.hashing import content_hash, item_unique_key


def normalize(raw: RawItem, source_ctx: SourceContext, source: Source, module_cfg: ModuleCfg) -> Item:
    """RawItem -> 待入库 Item（未提交）。"""
    summary = (raw.summary or raw.content or "")[:2000]
    content = raw.content or ""
    title = raw.title.strip()
    published_at = raw.published_at or datetime.now()

    item = Item(
        module_id=source.module_id,
        source_id=source.id,
        unique_key=item_unique_key(module_cfg.key, raw.url, title),
        content_hash=content_hash(title, summary, content),
        title=title,
        url=raw.url or None,
        author=raw.author,
        summary=summary or None,
        raw_content=content[:20000] or None,
        lifetime=module_cfg.lifetime,
        status="new",
        published_at=published_at,
        fetched_at=datetime.now(),
    )
    return item
