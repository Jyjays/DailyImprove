from __future__ import annotations

from datetime import datetime

import httpx

from app.plugins.base import RawItem, SourceContext, SourcePlugin
from app.utils.logger import logger


class SearchSourcePlugin(SourcePlugin):
    """搜索型来源：调用 Tavily API（也可扩展其他搜索 API）。

    config:
      query: 搜索词
      search_depth: basic|advanced
      max_results: 返回条数上限
    """

    name = "search"

    def fetch(self, source: SourceContext) -> list[RawItem]:
        from app.config import settings

        cfg = source.config or {}
        query = cfg.get("query") or source.url
        if not query:
            raise ValueError("search 来源需要 config.query 或 url 作为搜索词")
        api_key = cfg.get("api_key") or settings.llm_api_key  # 不强制；Tavily 需要 TAVILY_API_KEY
        tavily_key = __import__("os").environ.get("TAVILY_API_KEY", api_key)
        if not tavily_key:
            raise ValueError("search 来源需要 TAVILY_API_KEY")

        logger.info("搜索开始: %s (%s)", source.name, query)
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": query,
                "search_depth": cfg.get("search_depth", "basic"),
                "max_results": int(cfg.get("max_results", 5)),
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items: list[RawItem] = []
        for r in data.get("results", []):
            title = r.get("title", "").strip()
            if not title:
                continue
            items.append(
                RawItem(
                    title=title,
                    url=r.get("url", ""),
                    summary=r.get("content"),
                    published_at=datetime.fromisoformat(r["published_date"]) if r.get("published_date") else None,
                    extra={"source": source.name, "score": r.get("score")},
                )
            )
        logger.info("搜索完成: %s，共 %d 条", source.name, len(items))
        return items
