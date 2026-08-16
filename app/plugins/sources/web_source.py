from __future__ import annotations

import re

import httpx

from app.plugins.base import RawItem, SourceContext, SourcePlugin
from app.utils.logger import logger


class WebSourcePlugin(SourcePlugin):
    """轻量网页抓取：默认提取页面中所有带标题文本的 <a> 链接。

    适合博客目录页、招聘列表页等简单结构；复杂页面建议改用 api 或 rss。
    可通过 config 配置：
      - link_selector_re: 只提取 href 匹配该正则的链接
      - base_url: 相对链接拼接前缀
    """

    name = "web"

    def fetch(self, source: SourceContext) -> list[RawItem]:
        cfg = source.config or {}
        timeout = int(cfg.get("timeout", 30))
        base_url = cfg.get("base_url") or source.url
        link_re = cfg.get("link_selector_re")

        logger.info("Web 抓取开始: %s (%s)", source.name, source.url)
        resp = httpx.get(source.url, timeout=timeout, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 DailyImprove/0.1"})
        resp.raise_for_status()
        html = resp.text

        items: list[RawItem] = []
        seen = set()
        for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
            href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
            text = re.sub(r"\s+", " ", text).strip()
            if not text or len(text) < 4:
                continue
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            if link_re and not re.search(link_re, href):
                continue
            url = href if href.startswith("http") else httpx.URL(base_url).join(href)
            url = str(url)
            if url in seen:
                continue
            seen.add(url)
            items.append(RawItem(title=text, url=url, extra={"source": source.name}))
        logger.info("Web 抓取完成: %s，共 %d 条", source.name, len(items))
        return items
