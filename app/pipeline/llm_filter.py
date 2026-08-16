"""LLM 单轮筛选器。"""
from __future__ import annotations

import json
from typing import Any

from app.models.models import Item
from app.schemas import ModuleCfg
from app.utils.hashing import title_similarity
from app.utils.llm_client import LLMClient
from app.utils.logger import logger


class LLMFilter:
    """用基础大模型做一轮筛选，不依赖 Agent 能力。"""

    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    @property
    def available(self) -> bool:
        return self.client.available

    def _client_for(self, module_cfg: ModuleCfg) -> LLMClient:
        """模块级 llm.model 优先，否则使用全局模型。"""
        if module_cfg.llm.model:
            return LLMClient(model=module_cfg.llm.model)
        return self.client

    def filter(self, items: list[Item], module_cfg: ModuleCfg) -> list[Item]:
        """返回 relevant=True 且 score>=threshold 的条目；不可用时回退为关键词规则。"""
        if not items:
            return []
        client = self._client_for(module_cfg)
        if not client.available:
            logger.warning("LLM 未配置，回退到关键词评分模式")
            return self._fallback(items, module_cfg)

        results: dict[int, dict[str, Any]] = {}
        batch_size = max(1, module_cfg.llm.batch_size)
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            try:
                batch_results = self._run_batch(batch, module_cfg, client)
                results.update(batch_results)
            except Exception as e:
                logger.error("LLM 批次筛选失败(%d-%d): %s", i, i + len(batch), e)
                # 该批次回退，避免整次运行失败
                for item in batch:
                    item.llm_score = float(module_cfg.llm.threshold)
                    item.llm_output = json.dumps({"relevant": True, "score": module_cfg.llm.threshold, "reason": "llm failed, fallback"}, ensure_ascii=False)
                    results[item.id] = {"relevant": True, "score": module_cfg.llm.threshold}

        kept: list[Item] = []
        for item in items:
            r = results.get(item.id) or {}
            score = float(r.get("score", 0) or 0)
            relevant = bool(r.get("relevant", True))
            item.llm_score = score
            item.llm_output = json.dumps(r, ensure_ascii=False)
            if relevant and score >= module_cfg.llm.threshold:
                kept.append(item)
            else:
                item.status = "filtered_out"
        logger.info("LLM 筛选完成: 输入 %d，保留 %d", len(items), len(kept))
        return kept

    def _run_batch(self, items: list[Item], module_cfg: ModuleCfg, client: LLMClient | None = None) -> dict[int, dict[str, Any]]:
        client = client or self.client
        system = (
            "你是信息筛选助手。根据用户兴趣档案判断每条信息是否相关。"
            "只输出 JSON，不要输出其他文字。"
        )
        source_hints = self._source_hints(items)
        lines = [f"用户兴趣档案：\n{module_cfg.llm.profile or '通用科技与成长内容'}", "", "来源可靠度提示（仅供参考，不是硬过滤）："]
        lines.extend(source_hints if source_hints else ["（无来源评分数据）"])
        lines.append("")
        lines.append("候选信息列表：")
        for idx, item in enumerate(items, 1):
            text = f"{item.title} {item.summary or ''} {item.raw_content or ''}"[:800]
            lines.append(
                f"[{idx}] id={item.id} source={item.source.name if item.source else '?'} url={item.url or ''}\n"
                f"title={item.title}\ncontent={text}\n"
            )
        lines.append("")
        lines.append(
            "请逐条判断，输出 JSON："
            '{"items":[{"id":"...","relevant":true,"score":0,"summary":"<=80字中文摘要","reason":"<=30字","tags":["标签"]}]}'
            " score 为 0-100 相关度打分。"
        )
        user = "\n".join(lines)

        data = client.chat_json(
            system=system,
            user=user,
            temperature=module_cfg.llm.temperature,
            max_tokens=module_cfg.llm.max_tokens,
        )
        items_out = data.get("items") or []
        results: dict[int, dict[str, Any]] = {}
        for i, r in enumerate(items_out):
            item = items[i] if i < len(items) else None
            if item is None:
                continue
            results[item.id] = r
        # 缺失的条目默认保留（避免 LLM 漏返回导致误杀）
        for item in items:
            results.setdefault(item.id, {"relevant": True, "score": module_cfg.llm.threshold, "reason": "llm missed"})
        return results

    @staticmethod
    def _source_hints(items: list[Item]) -> list[str]:
        seen: dict[str, Any] = {}
        for item in items:
            if item.source and item.source.id not in seen:
                seen[item.source.id] = item.source
        hints = []
        for src in seen.values():
            rating = (src.rating_avg or 0.5) * 5
            hints.append(f"- 来源「{src.name}」用户评分 {rating:.1f}/5，权重 {src.base_weight:.2f}")
        return hints

    def _fallback(self, items: list[Item], module_cfg: ModuleCfg) -> list[Item]:
        """无 LLM 时：按关键词命中数给分；无关键词时全部保留。"""
        from app.pipeline.filters import DeterministicFilter

        keywords = module_cfg.filter.keywords_include
        kept: list[Item] = []
        for item in items:
            if keywords:
                hit = DeterministicFilter.keyword_hit_count(item, keywords)
                score = min(100, 55 + hit * 15)
                keep = hit > 0 and score >= module_cfg.llm.threshold
            else:
                score = float(max(module_cfg.llm.threshold, 60))
                keep = True
            item.llm_score = float(score)
            item.llm_output = json.dumps(
                {"relevant": keep, "score": score, "reason": "keyword fallback", "tags": []},
                ensure_ascii=False,
            )
            if keep:
                kept.append(item)
            else:
                item.status = "filtered_out"
        return kept
