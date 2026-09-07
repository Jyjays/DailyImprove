"""模块编排器：一次模块运行的完整流水线。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.db import SessionLocal
from app.models.models import Item, Module, PushRecord, RunRecord, Source
from app.pipeline.composer import Composer
from app.pipeline.content_fetcher import MIN_CONTENT_LEN, enrich_content
from app.pipeline.cluster import merge_clusters
from app.pipeline.dedup import DedupStore
from app.pipeline.filters import DeterministicFilter
from app.pipeline.interest import learn_top_tags
from app.pipeline.llm_filter import LLMFilter
from app.pipeline.normalizer import normalize
from app.pipeline.ranker import Ranker
from app.pipeline.selector import TopNSelector
from app.plugins.base import SourceContext
from app.plugins.channels import get_channel_plugin
from app.plugins.sources import get_source_plugin
from app.schemas import ModuleCfg, parse_module_cfg
from app.utils.logger import logger


class ModuleRunner:
    def __init__(self, session: Session):
        self.session = session

    def run(self, module_key: str, manual: bool = False) -> RunRecord:
        module = self.session.execute(select(Module).where(Module.key == module_key)).scalar_one_or_none()
        if module is None:
            raise ValueError(f"模块不存在: {module_key}")
        if not module.enabled and not manual:
            logger.info("模块 %s 未启用，跳过", module_key)
            raise ValueError(f"模块 {module_key} 未启用")

        cfg = self._module_cfg(module)
        run = RunRecord(module_id=module.id, status="running")
        self.session.add(run)
        self.session.flush()

        try:
            result = self._run_pipeline(module, cfg, run)
            run.status = "success"
            run.finished_at = datetime.now()
            self.session.commit()
            logger.info("模块 %s 运行成功: 抓取 %d，去重后 %d，过滤后 %d，选中 %d，推送 %d",
                        module_key, run.fetched_count, run.after_dedup_count,
                        run.after_filter_count, run.selected_count, run.pushed_count)
            return run
        except Exception as e:
            logger.exception("模块 %s 运行失败", module_key)
            self.session.rollback()
            # 记录失败运行
            fail_session = SessionLocal()
            try:
                failed = RunRecord(
                    module_id=module.id, status="failed",
                    finished_at=datetime.now(), error_msg=str(e)[:2000],
                )
                fail_session.add(failed)
                fail_session.commit()
            finally:
                fail_session.close()
            raise

    def _run_pipeline(self, module: Module, cfg: ModuleCfg, run: RunRecord) -> None:
        sources = list(self.session.execute(
            select(Source).where(Source.module_id == module.id, Source.is_paused == 0)
        ).scalars())
        if not sources:
            raise ValueError(f"模块 {cfg.key} 没有可用来源")

        dedup = DedupStore(self.session)
        candidates: list[Item] = []
        existing_titles: list[tuple[str, str]] = []

        # 1. 抓取 + 标准化 + 去重
        for source in sources:
            source_cfg = self._source_context(module, cfg, source)
            plugin = get_source_plugin(source.type)
            try:
                raw_items = plugin.fetch(source_cfg)
            except Exception as e:
                source.last_error = str(e)[:500]
                logger.warning("来源 %s 抓取失败: %s", source.name, e)
                continue
            # 每源限流：只保留最近 max_fetch 条，控制候选规模
            max_fetch = int((source_cfg.config or {}).get("max_fetch", 20))
            if len(raw_items) > max_fetch:
                raw_items = raw_items[:max_fetch]
            source.last_fetch_at = datetime.now()
            source.last_error = None
            run.fetched_count += len(raw_items)

            for raw in raw_items:
                try:
                    item = normalize(raw, source_cfg, source, cfg)
                except Exception as e:
                    logger.warning("条目标准化失败: %s", e)
                    continue
                # 正文补全：内容过短且有 URL 时，抓网页正文供 LLM 深度总结
                if item.url and (not item.raw_content or len(item.raw_content.strip()) < MIN_CONTENT_LEN):
                    fetched = enrich_content(item.raw_content, item.url)
                    if fetched and fetched != item.raw_content:
                        item.raw_content = fetched
                        if not item.summary:
                            item.summary = fetched[:2000]
                if dedup.exists(item, cfg):
                    continue
                if dedup.cross_source_duplicate(item, cfg, existing_titles):
                    logger.info("跨源去重命中: %s", item.title[:60])
                    continue
                self.session.add(item)
                candidates.append(item)
                existing_titles.append((item.title, item.url or ""))

        run.after_dedup_count = len(candidates)
        self.session.flush()  # 获得 item.id 供 LLM 使用

        if not candidates:
            run.status = "success"
            run.finished_at = datetime.now()
            logger.info("模块 %s 无新增条目", cfg.key)
            return

        # 2. 确定性过滤
        candidates = DeterministicFilter(cfg).filter(candidates)

        # 2.5 跨源聚类合并：同一内容的多来源合并为一条
        threshold = float((cfg.dedup or {}).get("title_similarity_threshold", 0.85))
        candidates = merge_clusters(candidates, threshold)

        # 3. LLM 单轮筛选（不可用时自动回退）
        candidates = LLMFilter().filter(candidates, cfg)

        run.after_filter_count = len(candidates)
        if not candidates:
            logger.info("模块 %s 过滤后无条目", cfg.key)
            return

        # 4. 排序 + 选材
        interest_tags = learn_top_tags(self.session, module.id)
        candidates = Ranker(cfg, interest_tags).compute_scores(candidates)
        selected = TopNSelector(cfg).select(candidates)
        run.selected_count = len(selected)

        if not selected:
            logger.info("模块 %s 无入选条目", cfg.key)
            return

        # 5. 组装 + 推送
        digest = Composer(cfg).compose(selected)
        channels = cfg.push.channels or ["file"]
        for channel_name in channels:
            try:
                channel = get_channel_plugin(channel_name)
                channel_config = getattr(cfg.push, channel_name, {}) if hasattr(cfg.push, channel_name) else {}
                result = channel.push(digest, channel_config if isinstance(channel_config, dict) else {})
            except KeyError as e:
                logger.warning("渠道不可用，跳过: %s", e)
                continue
            for item in selected:
                self.session.add(PushRecord(
                    item_id=item.id, module_id=module.id, channel=channel_name,
                    status="success" if result.ok else "failed",
                    external_id=result.external_id,
                ))
            if result.ok:
                run.pushed_count += 1
            logger.info("渠道 %s 推送结果: %s", channel_name, result.message or ("成功" if result.ok else "失败"))

        # 6. 更新条目状态
        all_ids = {item.id for item in candidates}
        selected_ids = {item.id for item in selected}
        for item in candidates:
            if item.id in selected_ids:
                item.status = "pushed" if run.pushed_count > 0 else "push_failed"
            else:
                item.status = "filtered_out"

    @staticmethod
    def _module_cfg(module: Module) -> ModuleCfg:
        if module.config_yaml:
            data = yaml.safe_load(module.config_yaml) or {}
            data["key"] = data.get("key", module.key)
            return parse_module_cfg(data)
        return ModuleCfg(
            key=module.key, name=module.name, enabled=bool(module.enabled),
            schedule=module.schedule, timezone=module.timezone,
            lifetime=module.lifetime, max_items_per_run=module.max_items,
        )

    @staticmethod
    def _source_context(module: Module, cfg: ModuleCfg, source: Source) -> SourceContext:
        rating = source.rating_avg if source.rating_avg is not None else 0.5
        multiplier = 0.3 + 1.2 * max(0.0, min(1.0, rating))
        config: dict[str, Any] = {}
        if source.config_json:
            try:
                config = json.loads(source.config_json)
            except json.JSONDecodeError:
                config = {}
        return SourceContext(
            id=source.id,
            name=source.name,
            type=source.type,
            url=source.url,
            module_key=cfg.key,
            module_name=cfg.name,
            lifetime=cfg.lifetime,
            base_weight=source.base_weight or 1.0,
            rating_multiplier=multiplier,
            config=config,
        )


def run_module(module_key: str, manual: bool = False) -> RunRecord:
    session = SessionLocal()
    try:
        return ModuleRunner(session).run(module_key, manual=manual)
    finally:
        session.close()
