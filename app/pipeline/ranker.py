from __future__ import annotations

import math
from datetime import datetime

from app.models.models import Item, Source
from app.schemas import ModuleCfg
from app.utils.logger import logger


class Ranker:
    """条目打分：来源权重 × LLM 分 × 新鲜度 × 兴趣。"""

    def __init__(self, module_cfg: ModuleCfg, interest_tags: dict[str, float] | None = None):
        self.module_cfg = module_cfg
        self.interest_tags = interest_tags or {}
        self.half_life_hours = float((module_cfg.dedup or {}).get("freshness_half_life_hours", 48))

    def compute_scores(self, items: list[Item]) -> list[Item]:
        if not items:
            return items
        weights = [self._source_weight(item) for item in items]
        max_w = max(weights) or 1.0
        for item, w in zip(items, weights):
            llm_score = (item.llm_score or 50) / 100.0
            value = self._value(item)
            source_norm = w / max_w
            freshness = self._freshness(item)
            interest = self._interest(item)
            item.final_score = (
                0.35 * value
                + 0.25 * llm_score
                + 0.15 * source_norm
                + 0.15 * freshness
                + 0.10 * interest
            )
        items.sort(key=lambda x: x.final_score or 0, reverse=True)
        logger.info("排序完成，Top5 分数: %s", [round(i.final_score or 0, 3) for i in items[:5]])
        return items

    def _source_weight(self, item: Item) -> float:
        if not item.source:
            return 1.0
        rating = item.source.rating_avg if item.source.rating_avg is not None else 0.5
        multiplier = 0.3 + 1.2 * max(0.0, min(1.0, rating))
        return (item.source.base_weight or 1.0) * multiplier

    @staticmethod
    def _value(item: Item) -> float:
        """从 LLM 输出解析价值分（0-100 归一化到 0-1）。缺失时回退到相关度分。"""
        import json
        try:
            data = json.loads(item.llm_output or "{}")
        except json.JSONDecodeError:
            data = {}
        raw = data.get("value", data.get("score", item.llm_score or 50))
        try:
            return max(0.0, min(1.0, float(raw) / 100.0))
        except (TypeError, ValueError):
            return (item.llm_score or 50) / 100.0

    def _freshness(self, item: Item) -> float:
        age_hours = 0.0
        ref = item.published_at or item.fetched_at or datetime.now()
        if ref:
            age_hours = max(0.0, (datetime.now() - ref).total_seconds() / 3600.0)
        return math.exp(-age_hours / self.half_life_hours)

    def _interest(self, item: Item) -> float:
        from app.pipeline.filters import DeterministicFilter
        from app.pipeline.interest import item_tags

        keywords = self.module_cfg.filter.keywords_include
        total = len(keywords) or 1
        hit = DeterministicFilter.keyword_hit_count(item, keywords)
        kw_score = min(1.0, hit / total) if keywords else 0.0

        tag_score = 0.0
        if self.interest_tags:
            hits = [self.interest_tags.get(t, 0.0) for t in item_tags(item)]
            tag_score = max(hits) if hits else 0.0

        return min(1.0, 0.6 * kw_score + 0.4 * tag_score)
