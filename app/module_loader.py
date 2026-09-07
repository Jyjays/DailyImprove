"""模块 YAML 加载与数据库同步。"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Module, Source
from app.schemas import ModuleCfg, parse_module_cfg
from app.utils.logger import logger


def list_module_files(modules_dir: Path | None = None) -> list[Path]:
    root = modules_dir or settings.modules_dir
    if not root.exists():
        return []
    return sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))


def load_module_yaml(path: Path) -> ModuleCfg:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "key" not in data:
        raise ValueError(f"{path.name} 缺少 key 字段")
    cfg = parse_module_cfg(data)
    return cfg


def sync_module_file(session: Session, path: Path) -> Module:
    cfg = load_module_yaml(path)
    module = session.execute(select(Module).where(Module.key == cfg.key)).scalar_one_or_none()
    if module is None:
        module = Module(key=cfg.key, name=cfg.name)
        session.add(module)
        logger.info("新增模块: %s", cfg.key)
    module.name = cfg.name
    module.enabled = 1 if cfg.enabled else 0
    module.schedule = cfg.schedule
    module.timezone = cfg.timezone
    module.lifetime = cfg.lifetime
    module.max_items = cfg.max_items_per_run
    module.config_yaml = path.read_text(encoding="utf-8")
    session.flush()

    # 同步来源：保留已有评分的来源记录
    existing = {s.url: s for s in session.execute(select(Source).where(Source.module_id == module.id)).scalars()}
    for src_cfg in cfg.sources:
        source = existing.get(src_cfg.url)
        if source is None:
            source = Source(module_id=module.id, name=src_cfg.name, url=src_cfg.url)
            session.add(source)
            logger.info("模块 %s 新增来源: %s", cfg.key, src_cfg.name)
        source.name = src_cfg.name
        source.type = src_cfg.type
        source.url = src_cfg.url
        source.base_weight = src_cfg.base_weight
        config = dict(src_cfg.config or {})
        config.setdefault("max_fetch", src_cfg.max_fetch)
        source.config_json = json.dumps(config, ensure_ascii=False)
    session.flush()
    return module


def sync_all_modules(session: Session, modules_dir: Path | None = None) -> list[ModuleCfg]:
    files = list_module_files(modules_dir)
    cfgs: list[ModuleCfg] = []
    for path in files:
        try:
            module = sync_module_file(session, path)
            session.commit()
            cfgs.append(load_module_yaml(path))
        except Exception as e:
            session.rollback()
            logger.error("模块配置加载失败 %s: %s", path, e)
    logger.info("模块同步完成，共 %d 个", len(cfgs))
    return cfgs
