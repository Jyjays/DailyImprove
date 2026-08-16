from __future__ import annotations

from app.models.models import Item
from app.schemas import ModuleCfg
from app.utils.logger import logger


class TopNSelector:
    """TopN 选择 + 来源多样性 + 跨源去重。"""

    def __init__(self, module_cfg: ModuleCfg):
        self.module_cfg = module_cfg

    def select(self, ranked_items: list[Item]) -> list[Item]:
        max_items = self.module_cfg.max_items_per_run
        max_per_source = int((self.module_cfg.dedup or {}).get("max_per_source", 2))
        cross_source = (self.module_cfg.dedup or {}).get("cross_source", "")
        sim_threshold = float((self.module_cfg.dedup or {}).get("title_similarity_threshold", 0.85))

        selected: list[Item] = []
        selected_titles: list[str] = []
        source_counts: dict[int, int] = {}

        for item in ranked_items:
            if len(selected) >= max_items:
                break
            if source_counts.get(item.source_id, 0) >= max_per_source:
                continue
            if cross_source == "title_similarity" and self._is_dup(item.title, selected_titles, sim_threshold):
                continue
            selected.append(item)
            selected_titles.append(item.title)
            source_counts[item.source_id] = source_counts.get(item.source_id, 0) + 1

        logger.info("TopN 选择: 候选 %d，选中 %d", len(ranked_items), len(selected))
        return selected

    @staticmethod
    def _is_dup(title: str, selected_titles: list[str], threshold: float) -> bool:
        from app.utils.hashing import title_similarity
        for t in selected_titles:
            if title_similarity(title, t) >= threshold:
                return True
        return False
