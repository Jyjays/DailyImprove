from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.models import Item
from app.schemas import ModuleCfg


class DedupStore:
    """去重器：持久型永久去重，时效型 TTL 去重。"""

    def __init__(self, session):
        self.session = session

    def exists(self, item: Item, module_cfg: ModuleCfg) -> bool:
        query = select(Item.id).where(
            Item.module_id == item.module_id,
            Item.unique_key == item.unique_key,
        )
        if item.lifetime == "ephemeral":
            ttl_days = int((module_cfg.dedup or {}).get("ttl_days", 3))
            cutoff = datetime.now() - timedelta(days=ttl_days)
            query = query.where(Item.lifetime == "ephemeral", Item.fetched_at >= cutoff)
        else:
            query = query.where(Item.lifetime == "persistent")
        return self.session.execute(query.limit(1)).first() is not None

    def cross_source_duplicate(self, item: Item, module_cfg: ModuleCfg, existing_titles: list[tuple[str, str]]) -> bool:
        """跨源去重：标题相似度超过阈值视为重复。"""
        strategy = (module_cfg.dedup or {}).get("cross_source", "")
        if strategy != "title_similarity":
            return False
        threshold = float((module_cfg.dedup or {}).get("title_similarity_threshold", 0.85))
        from app.utils.hashing import title_similarity
        for _title, _ in existing_titles:
            if title_similarity(item.title, _title) >= threshold:
                return True
        return False
