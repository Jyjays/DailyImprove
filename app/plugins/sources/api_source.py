from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.plugins.base import RawItem, SourceContext, SourcePlugin
from app.utils.logger import logger


def _get_path(data: Any, path: str) -> Any:
    """从 JSON 中按点路径取值，如 data.items 或 data.0.title。"""
    cur = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


class ApiSourcePlugin(SourcePlugin):
    name = "api"

    def fetch(self, source: SourceContext) -> list[RawItem]:
        cfg = source.config or {}
        method = (cfg.get("method") or "GET").upper()
        headers = cfg.get("headers") or {}
        params = cfg.get("params") or {}
        body = cfg.get("body") or None
        timeout = int(cfg.get("timeout", 30))

        logger.info("API 抓取开始: %s (%s %s)", source.name, method, source.url)
        resp = httpx.request(method, source.url, headers=headers, params=params, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        items_path = cfg.get("items_path") or "items"
        items_data = _get_path(data, items_path)
        if not isinstance(items_data, list):
            raise ValueError(f"items_path '{items_path}' 不是列表: {type(items_data)}")

        title_field = cfg.get("title_field") or "title"
        url_field = cfg.get("url_field") or "url"
        time_field = cfg.get("time_field") or "published_at"
        summary_field = cfg.get("summary_field") or "summary"
        author_field = cfg.get("author_field") or "author"
        content_field = cfg.get("content_field") or "content"

        items: list[RawItem] = []
        for row in items_data:
            if not isinstance(row, dict):
                continue
            title = str(_get_path(row, title_field) or "").strip()
            if not title:
                continue
            url = str(_get_path(row, url_field) or "")
            published_at = self._parse_time(_get_path(row, time_field))
            items.append(
                RawItem(
                    title=title,
                    url=url,
                    author=_get_path(row, author_field),
                    summary=_get_path(row, summary_field),
                    content=_get_path(row, content_field),
                    published_at=published_at,
                    extra={"source": source.name},
                )
            )
        logger.info("API 抓取完成: %s，共 %d 条", source.name, len(items))
        return items

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except Exception:
                return None
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
