"""兴趣标签学习：从用户反馈中统计高频兴趣标签，用于后续排序加权。"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Feedback, Item
from app.utils.logger import logger

# 反馈类型权重：收藏 > 有用 > 普通
_FEEDBACK_WEIGHT = {
    "save": 2.0,
    "item_useful": 1.0,
}


def item_tags(item: Item) -> list[str]:
    """从 LLM 输出中解析标签。"""
    try:
        data = json.loads(item.llm_output or "{}")
    except json.JSONDecodeError:
        return []
    tags = data.get("tags") or []
    return [str(t) for t in tags if t]


def learn_top_tags(session: Session, module_id: int | None = None, top_k: int = 10) -> dict[str, float]:
    """统计用户正反馈（收藏/有用）条目的高频标签，返回 {tag: 0~1 权重}。"""
    q = select(Feedback).where(
        Feedback.feedback_type.in_(["save", "item_useful"]),
        Feedback.item_id.isnot(None),
    )
    if module_id is not None:
        q = q.where(Feedback.module_id == module_id)
    feedbacks = list(session.execute(q).scalars())
    if not feedbacks:
        return {}

    item_ids = [fb.item_id for fb in feedbacks]
    type_by_item: dict[int, str] = {fb.item_id: fb.feedback_type for fb in feedbacks}
    items = list(session.execute(select(Item).where(Item.id.in_(item_ids))).scalars())

    weights: dict[str, float] = {}
    for it in items:
        w = _FEEDBACK_WEIGHT.get(type_by_item.get(it.id, ""), 1.0)
        for tag in item_tags(it):
            weights[tag] = weights.get(tag, 0.0) + w

    if not weights:
        return {}
    top = sorted(weights.items(), key=lambda x: -x[1])[:top_k]
    max_w = top[0][1] or 1.0
    result = {t: w / max_w for t, w in top}
    logger.info("兴趣标签学习: %s", result)
    return result
