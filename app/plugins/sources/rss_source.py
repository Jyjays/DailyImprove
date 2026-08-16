from __future__ import annotations

from datetime import datetime
from typing import Any

import feedparser
import httpx

from app.plugins.base import RawItem, SourceContext, SourcePlugin
from app.utils.logger import logger

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 DailyImprove/0.1"


class RssSourcePlugin(SourcePlugin):
    name = "rss"

    def fetch(self, source: SourceContext) -> list[RawItem]:
        logger.info("RSS 抓取开始: %s (%s)", source.name, source.url)
        timeout = int((source.config or {}).get("timeout", 30))
        resp = httpx.get(source.url, timeout=timeout, follow_redirects=True,
                         headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo:
            logger.warning("RSS 解析警告 %s: %s", source.url, parsed.bozo_exception)

        items: list[RawItem] = []
        for entry in parsed.entries:
            published_at = self._parse_time(entry)
            summary = None
            if entry.get("summary"):
                summary = _strip_html(entry.summary)
            content = None
            if entry.get("content"):
                try:
                    content = entry.content[0].get("value")
                except (IndexError, AttributeError):
                    content = None
            url = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not title:
                continue
            items.append(
                RawItem(
                    title=title,
                    url=url,
                    author=entry.get("author"),
                    summary=summary,
                    content=content,
                    published_at=published_at,
                    extra={"source": source.name},
                )
            )
        logger.info("RSS 抓取完成: %s，共 %d 条", source.name, len(items))
        return items

    @staticmethod
    def _parse_time(entry: Any) -> datetime | None:
        for attr in ("published_parsed", "updated_parsed"):
            try:
                tt = entry.get(attr)
                if tt:
                    return datetime(*tt[:6])
            except Exception:
                continue
        return None


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()
