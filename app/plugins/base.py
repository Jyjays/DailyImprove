"""插件接口定义。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawItem:
    title: str
    url: str = ""
    author: str | None = None
    content: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceContext:
    """抓取时的来源上下文。"""
    id: int
    name: str
    type: str
    url: str
    module_key: str
    module_name: str
    lifetime: str
    base_weight: float = 1.0
    rating_multiplier: float = 1.0
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class DigestItem:
    title: str
    url: str
    source_name: str
    source_rating: float
    summary: str = ""
    llm_reason: str = ""
    llm_score: float | None = None
    final_score: float | None = None
    tags: list[str] = field(default_factory=list)
    merged_sources: str = ""
    published_at: datetime | None = None


@dataclass
class Digest:
    module_key: str
    module_name: str
    title: str
    generated_at: datetime
    lifetime: str
    items: list[DigestItem] = field(default_factory=list)

    @property
    def markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        for idx, it in enumerate(self.items, 1):
            lines.append(f"## {idx}. {it.title}")
            if it.url:
                lines.append(f"链接：{it.url}")
            lines.append(f"来源：{it.source_name}（评分 {it.source_rating:.2f}）")
            if it.summary:
                lines.append(f"摘要：{it.summary}")
            if it.llm_reason:
                lines.append(f"入选理由：{it.llm_reason}")
            if it.merged_sources:
                lines.append(f"另见来源：{it.merged_sources}")
            if it.tags:
                lines.append(f"标签：{' / '.join(it.tags)}")
            lines.append("")
        return "\n".join(lines)


@dataclass
class PushResult:
    ok: bool
    channel: str
    external_id: str | None = None
    message: str = ""


class SourcePlugin(ABC):
    """来源插件：只负责抓取原始条目。"""
    plugin_type = "source"
    name = "base_source"

    @abstractmethod
    def fetch(self, source: SourceContext) -> list[RawItem]:
        """抓取一个来源，返回原始条目列表。"""

    def validate(self, source: SourceContext) -> bool:
        return True


class ChannelPlugin(ABC):
    """推送渠道插件。"""
    plugin_type = "channel"
    name = "base_channel"

    @abstractmethod
    def push(self, digest: Digest, channel_config: dict[str, Any]) -> PushResult:
        """把 Digest 推送到目标渠道。"""
