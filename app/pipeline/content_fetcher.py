"""正文抓取器：从条目 URL 抓取网页并提取正文，供 LLM 深度总结使用。

优先使用 trafilatura（可读性最好的正文提取库），未安装时降级为
「去 HTML 标签 + 压缩空白」的轻量方案。任何失败均返回 None，由调用方静默降级。
"""
from __future__ import annotations

import re

import httpx

from app.utils.logger import logger

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 DailyImprove/0.1"

# 正文过短（字符数）时视为"没有可用正文"，触发网页抓取补全
MIN_CONTENT_LEN = 200
# 抓取正文的最大长度，防止超大网页撑爆 LLM 输入
MAX_EXTRACTED_LEN = 20000


def _strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_full_text(url: str, timeout: int = 20) -> str | None:
    """抓取 url 的正文纯文本。失败返回 None。"""
    if not url:
        return None
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True,
                         headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        html = resp.text
        if not html:
            return None
        try:
            import trafilatura
            text = trafilatura.extract(html, include_comments=False, include_tables=False)
            if text:
                return re.sub(r"\s+", " ", text).strip()[:MAX_EXTRACTED_LEN]
        except ImportError:
            logger.debug("trafilatura 未安装，降级为轻量 HTML 剥离")
        except Exception as e:
            logger.debug("trafilatura 提取失败: %s", e)
        # 降级：剥标签
        text = _strip_html(html)
        return text[:MAX_EXTRACTED_LEN] if len(text) > MIN_CONTENT_LEN else None
    except Exception as e:
        logger.debug("正文抓取失败 %s: %s", url, e)
        return None


def enrich_content(content: str | None, url: str, timeout: int = 20) -> str | None:
    """内容过短时尝试从网页补全正文。返回补全后的正文（或原内容）。"""
    if content and len(content.strip()) >= MIN_CONTENT_LEN:
        return content
    fetched = fetch_full_text(url, timeout)
    if fetched and len(fetched) > len((content or "").strip()):
        return fetched
    return content
