from __future__ import annotations

import math
from datetime import datetime

from app.models.models import Item, Source
from app.schemas import ModuleCfg
from app.utils.logger import logger


class Ranker:
    """条目打分：来源权重 × LLM 分 × 新鲜度 × 兴趣。"""

    def __init__(self, module_cfg: ModuleCfg):
        self.module_cfg = module_cfg
        self.half_life_hours = float((module_cfg.dedup or {}).get("freshness_half_life_hours", 48))

    def compute_scores(self, items: list[Item]) -> list[Item]:
        if not items:
            return items
        weights = [self._source_weight(item) for item in items]
        max_w = max(weights) or 1.0
        for item, w in zip(items, weights):
            llm_score = (item.llm_score or 50) / 100.0
            source_norm = w / max_w
            freshness = self._freshness(item)
            interest = self._interest(item)
            item.final_score = (
                0.45 * llm_score
                + 0.20 * source_norm
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

    def _freshness(self, item: Item) -> float:
        age_hours = 0.0
        ref = item.published_at or item.fetched_at or datetime.now()
        if ref:
            age_hours = max(0.0, (datetime.now() - ref).total_seconds() / 3600.0)
        return math.exp(-age_hours / self.half_life_hours)

    def _interest(self, item: Item) -> float:
        from app.pipeline.filters import DeterministicFilter
        hit = DeterministicFilter.keyword_hit_count(item, self.module_cfg.filter.keywords_include)
        total = len(self.module_cfg.filter.keywords_include) or 1
        return min(1.0, hit / total)
