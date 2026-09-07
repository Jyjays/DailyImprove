from __future__ import annotations

import json
from datetime import datetime

from app.models.models import Item
from app.plugins.base import Digest, DigestItem
from app.schemas import ModuleCfg


class Composer:
    def __init__(self, module_cfg: ModuleCfg):
        self.module_cfg = module_cfg

    def compose(self, items: list[Item]) -> Digest:
        digest_items: list[DigestItem] = []
        for item in items:
            llm_data = {}
            try:
                llm_data = json.loads(item.llm_output or "{}")
            except json.JSONDecodeError:
                pass
            source_rating = item.source.rating_avg if item.source else 0.5
            digest_items.append(
                DigestItem(
                    title=item.title,
                    url=item.url or "",
                    source_name=item.source.name if item.source else "未知来源",
                    source_rating=source_rating,
                    summary=llm_data.get("summary") or item.summary or "",
                    llm_reason=llm_data.get("reason", ""),
                    llm_score=item.llm_score,
                    final_score=item.final_score,
                    tags=llm_data.get("tags", []),
                    merged_sources=item.merged_sources or "",
                    published_at=item.published_at,
                )
            )
        title = f"【{self.module_cfg.name}】日报 {datetime.now():%Y-%m-%d}"
        return Digest(
            module_key=self.module_cfg.key,
            module_name=self.module_cfg.name,
            title=title,
            generated_at=datetime.now(),
            lifetime=self.module_cfg.lifetime,
            items=digest_items,
        )
