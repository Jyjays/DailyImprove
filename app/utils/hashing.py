"""URL 归一化与内容哈希。"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "share_token", "share_id", "vd_source", "ref", "source",
}


def normalize_url(url: str) -> str:
    """去 hash、去追踪参数、统一协议与尾斜杠。"""
    if not url:
        return ""
    url = url.strip()
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS]
    query_str = urlencode(sorted(query), doseq=True)
    return urlunsplit((scheme, netloc, path, query_str, ""))


def content_hash(title: str, summary: str = "", content: str = "") -> str:
    text = f"{title or ''}\n{summary or ''}\n{content or ''}".strip().lower()
    text = re.sub(r"\s+", " ", text)
    return hashlib.sha1(text.encode("utf-8")).hexdigest() if text else ""


def item_unique_key(module_key: str, url: str, title: str) -> str:
    base = normalize_url(url) if url else (title or "").strip().lower()
    raw = f"{module_key}:{base}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def title_similarity(a: str, b: str) -> float:
    """极简标题相似度：字符 2-gram 的 Dice 系数。"""
    def grams(s: str) -> set[str]:
        s = re.sub(r"[\W_]+", "", s.lower())
        return {s[i:i + 2] for i in range(max(0, len(s) - 1))} if len(s) >= 2 else {s}
    ga, gb = grams(a or ""), grams(b or "")
    if not ga or not gb:
        return 0.0
    return 2 * len(ga & gb) / (len(ga) + len(gb))
