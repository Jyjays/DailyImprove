"""确定性过滤器。"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.models import Item
from app.schemas import ModuleCfg


class DeterministicFilter:
    def __init__(self, module_cfg: ModuleCfg):
        self.cfg = module_cfg.filter

    def filter(self, items: list[Item]) -> list[Item]:
        kept: list[Item] = []
        lookback = self.cfg.lookback_hours
        cutoff = datetime.now() - timedelta(hours=lookback) if lookback > 0 else None
        for item in items:
            if not self._pass_keywords(item):
                item.status = "filtered_out"
                continue
            if self.cfg.min_content_length and (len(item.raw_content or "") + len(item.summary or "")) < self.cfg.min_content_length:
                item.status = "filtered_out"
                continue
            if cutoff and item.published_at and item.published_at < cutoff:
                item.status = "filtered_out"
                continue
            kept.append(item)
        return kept

    def _pass_keywords(self, item: Item) -> bool:
        text = f"{item.title} {item.summary or ''} {item.raw_content or ''}".lower()
        if self.cfg.keywords_include:
            if not any(kw.lower() in text for kw in self.cfg.keywords_include):
                return False
        if self.cfg.keywords_exclude:
            if any(kw.lower() in text for kw in self.cfg.keywords_exclude):
                return False
        return True

    @staticmethod
    def keyword_hit_count(item: Item, keywords: list[str]) -> int:
        if not keywords:
            return 0
        text = f"{item.title} {item.summary or ''} {item.raw_content or ''}".lower()
        return sum(1 for kw in keywords if kw.lower() in text)
