"""跨源聚类合并：把同一事件/内容的多来源条目合并为一条。

与 DedupStore.cross_source_duplicate（直接丢弃重复项）不同，这里做的是「聚类」：
- 标题相似度 >= 阈值的条目归为一簇（连通分量）
- 每簇保留「来源权重最高 / 正文最全」的一条作为代表
- 其余条目标记 filtered_out，并把来源名记录到代表条目的 merged_sources
"""
from __future__ import annotations

from app.models.models import Item
from app.utils.hashing import title_similarity
from app.utils.logger import logger


def _source_weight(item: Item) -> float:
    if not item.source:
        return 1.0
    rating = item.source.rating_avg if item.source.rating_avg is not None else 0.5
    multiplier = 0.3 + 1.2 * max(0.0, min(1.0, rating))
    return (item.source.base_weight or 1.0) * multiplier


def _content_len(item: Item) -> int:
    return len(item.raw_content or "") + len(item.summary or "")


def merge_clusters(items: list[Item], threshold: float = 0.85) -> list[Item]:
    """返回聚类后的代表条目列表；被合并条目会被原地标记为 filtered_out。"""
    if not items:
        return []

    clusters: list[list[Item]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            if any(title_similarity(item.title, other.title) >= threshold for other in cluster):
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    representatives: list[Item] = []
    for cluster in clusters:
        if len(cluster) == 1:
            representatives.append(cluster[0])
            continue
        # 选代表：来源权重优先，正文更全者优先
        rep = max(cluster, key=lambda it: (_source_weight(it), _content_len(it)))
        merged_names = [it.source.name for it in cluster if it.source and it.id != rep.id]
        if merged_names:
            rep.merged_sources = " / ".join(sorted(set(merged_names)))
        for it in cluster:
            if it.id != rep.id:
                it.status = "filtered_out"
        representatives.append(rep)
        logger.info("跨源聚类合并: 「%s」%d 条来源合并", rep.title[:40], len(cluster))

    return representatives
