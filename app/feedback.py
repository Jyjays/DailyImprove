"""用户反馈处理：来源评分更新。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Feedback, Source
from app.utils.logger import logger

# 贝叶斯平滑参数
GLOBAL_AVG = 0.5
SMOOTHING_C = 10.0


def smoothed_rating(rating_avg: float, rating_count: int) -> float:
    return (SMOOTHING_C * GLOBAL_AVG + rating_count * rating_avg) / (SMOOTHING_C + rating_count)


def apply_feedback(session: Session, source_id: int | None, feedback_type: str, rating: int | None = None,
                   item_id: int | None = None, module_id: int | None = None) -> Feedback:
    feedback = Feedback(
        source_id=source_id, item_id=item_id, module_id=module_id,
        feedback_type=feedback_type, rating=rating,
    )
    session.add(feedback)
    if source_id is not None:
        source = session.get(Source, source_id)
        if source:
            if feedback_type == "source_rating" and rating is not None:
                old_count = source.rating_count or 0
                old_avg = source.rating_avg or GLOBAL_AVG
                new_count = old_count + 1
                new_avg = (old_avg * old_count + (rating / 5.0)) / new_count
                source.rating_count = new_count
                source.rating_avg = new_avg
                logger.info("来源 %s 评分更新: avg=%.3f count=%d", source.name, new_avg, new_count)
            elif feedback_type == "item_useful":
                source.rating_avg = min(1.0, (source.rating_avg or GLOBAL_AVG) + 0.03)
                source.rating_count = (source.rating_count or 0) + 1
            elif feedback_type == "item_useless":
                source.rating_avg = max(0.0, (source.rating_avg or GLOBAL_AVG) - 0.05)
                source.rating_count = (source.rating_count or 0) + 1
            elif feedback_type == "save":
                source.rating_avg = min(1.0, (source.rating_avg or GLOBAL_AVG) + 0.08)
                source.rating_count = (source.rating_count or 0) + 1
            elif feedback_type == "ignore":
                source.rating_avg = max(0.0, (source.rating_avg or GLOBAL_AVG) - 0.08)
                source.rating_count = (source.rating_count or 0) + 1
    session.commit()
    return feedback


def get_source_effective_rating(source: Source) -> float:
    return smoothed_rating(source.rating_avg or GLOBAL_AVG, source.rating_count or 0)
