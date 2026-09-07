"""配置/数据结构定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceCfg:
    name: str
    type: str
    url: str = ""
    base_weight: float = 1.0
    max_fetch: int = 20
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class LlmCfg:
    model: str = ""
    temperature: float = 0.1
    batch_size: int = 10
    max_tokens: int = 2000
    threshold: int = 60
    profile: str = ""


@dataclass
class FilterCfg:
    keywords_include: list[str] = field(default_factory=list)
    keywords_exclude: list[str] = field(default_factory=list)
    min_content_length: int = 0
    lookback_hours: int = 168


@dataclass
class PushCfg:
    channels: list[str] = field(default_factory=list)
    wechat: dict[str, Any] = field(default_factory=dict)
    feishu_doc: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleCfg:
    key: str
    name: str
    enabled: bool = True
    schedule: str = "0 8 * * *"
    timezone: str = "Asia/Shanghai"
    lifetime: str = "persistent"
    max_items_per_run: int = 5
    dedup: dict[str, Any] = field(default_factory=dict)
    llm: LlmCfg = field(default_factory=LlmCfg)
    filter: FilterCfg = field(default_factory=FilterCfg)
    push: PushCfg = field(default_factory=PushCfg)
    sources: list[SourceCfg] = field(default_factory=list)


def parse_module_cfg(data: dict[str, Any]) -> ModuleCfg:
    """把 YAML 配置解析为 ModuleCfg，并补默认值。"""
    llm_data = data.get("llm") or {}
    filter_data = data.get("filter") or {}
    push_data = data.get("push") or {}
    dedup_data = data.get("dedup") or {}

    sources = []
    for src in data.get("sources") or []:
        sources.append(
            SourceCfg(
                name=src.get("name", src.get("url", "unnamed")),
                type=src.get("type", "rss"),
                url=src.get("url", ""),
                base_weight=float(src.get("base_weight", 1.0)),
                max_fetch=int(src.get("max_fetch", 20)),
                config=src.get("config") or {},
            )
        )

    return ModuleCfg(
        key=data["key"],
        name=data.get("name", data["key"]),
        enabled=bool(data.get("enabled", True)),
        schedule=data.get("schedule", "0 8 * * *"),
        timezone=data.get("timezone", "Asia/Shanghai"),
        lifetime=data.get("lifetime", "persistent"),
        max_items_per_run=int(data.get("max_items_per_run", 5)),
        dedup=dedup_data,
        llm=LlmCfg(
            model=llm_data.get("model", ""),
            temperature=float(llm_data.get("temperature", 0.1)),
            batch_size=int(llm_data.get("batch_size", 10)),
            max_tokens=int(llm_data.get("max_tokens", 2000)),
            threshold=int(llm_data.get("threshold", 60)),
            profile=llm_data.get("profile", ""),
        ),
        filter=FilterCfg(
            keywords_include=filter_data.get("keywords_include", []),
            keywords_exclude=filter_data.get("keywords_exclude", []),
            min_content_length=int(filter_data.get("min_content_length", 0)),
            lookback_hours=int(filter_data.get("lookback_hours", 168)),
        ),
        push=PushCfg(
            channels=push_data.get("channels", []),
            wechat=push_data.get("wechat", {}),
            feishu_doc=push_data.get("feishu_doc", {}),
        ),
        sources=sources,
    )
