"""练习领域：来源、精选种子与面向 AI 的进度摘要。"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.models.models import PracticeAttempt, PracticeQuestion, PracticeReview, PracticeSource, PracticeTopic
from app.practice_seed import QUESTIONS, TOPICS
from app.utils.hashing import normalize_url


def now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def today() -> date:
    return now().date()


def public_url(value: str, optional: bool = False) -> str:
    value = value.strip()
    if optional and not value:
        return ""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        raise ValueError("链接格式不正确")
    if (len(value) > 2000 or parts.scheme not in ("https", "http") or not host
            or parts.username or parts.password or port not in (None, 80, 443)
            or any(c in value for c in ("\\", "\r", "\n", "\t"))):
        raise ValueError("请使用公开网页的 http/https 链接")
    if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")) or "." not in host:
        raise ValueError("请使用公开网页链接")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("不能使用本机或内网地址")
    return value


def canonical_key(kind: str, title: str, url: str = "") -> str:
    p = urlsplit(url)
    match = re.search(r"/problems/([\w-]+)", p.path)
    if p.hostname in {"leetcode.com", "www.leetcode.com", "leetcode.cn", "www.leetcode.cn"} and match:
        return "leetcode:" + match.group(1).lower()
    normalized = re.sub(r"[\W_]+", "", title).lower()
    return kind + ":" + hashlib.sha256(normalized.encode()).hexdigest()


def initialize_practice(session: Session) -> None:
    for key, name, description, title, url, example in TOPICS:
        if session.get(PracticeTopic, key) is None:
            session.add(PracticeTopic(key=key, name=name, description=description,
                                      material_title=title, material_url=url, example=example))
    for spec in QUESTIONS:
        if session.get(PracticeQuestion, spec["id"]) is not None:
            continue
        key = spec.get("key") or canonical_key(spec["kind"], spec["title"], spec["url"])
        # 用户此前导入过同一原题时，不创建第二份，也不覆盖用户内容。
        if session.query(PracticeQuestion).filter_by(canonical_key=key).first():
            continue
        session.add(PracticeQuestion(id=spec["id"], canonical_key=key, title=spec["title"], kind=spec["kind"],
                                    origin=spec["origin"], prompt=spec["prompt"], reference_notes=spec["reference"],
                                    followups_json=json.dumps(spec["followups"], ensure_ascii=False),
                                    topics_json=json.dumps(spec["topics"]), roles_json=json.dumps(["数据库/存储", "系统开发"]), created_at=now()))
        session.flush()
        note = "2026-10-24 核验原始页面；参考要点为系统整理，并非官方答案。"
        if spec["source_type"] == "interview":
            note = "据本会话早前核验的作者自述整理；2023 年旧面经，不代表近期高频；当前网站可能只返回导航。"
        session.add(PracticeSource(question_id=spec["id"], source_type=spec["source_type"], title=spec["source_title"],
                                   url=spec["url"], normalized_url=normalize_url(spec["url"]),
                                   published_on=date.fromisoformat(spec["published_on"]) if spec.get("published_on") else None,
                                   captured_at=now(), verification=spec["verification"], note=note,
                                   company="百度" if spec["source_type"] == "interview" else "",
                                   position="数据库内核" if spec["source_type"] == "interview" else "",
                                   hiring_type="实习" if spec["source_type"] == "interview" else ""))
    session.commit()


def practice_overview(session: Session) -> dict:
    cutoff = now() - timedelta(days=7)
    rows = session.query(PracticeAttempt, PracticeQuestion).join(PracticeQuestion).order_by(PracticeAttempt.id.desc()).limit(100).all()
    recent = [{"id": a.id, "question_id": q.id, "title": q.title, "date": a.created_at.isoformat(),
               "mode": a.mode, "result": a.result, "note": a.note, "topics": json.loads(q.topics_json)} for a, q in rows[:10]]
    count = session.query(PracticeAttempt).filter(PracticeAttempt.created_at >= cutoff).count()
    active = [{"key": t.key, "name": t.name, "status": t.status, "note": t.note}
              for t in session.query(PracticeTopic).filter(PracticeTopic.status != "candidate").all()]
    return {"attempts_last_7_days": count, "recent_attempts": recent, "topic_choices": active,
            "note": "结果为用户自评，不等于能力认证；没有尝试记录表示未知，不是未学习。"}


FETCH_HOSTS = {"leetcode.com", "www.leetcode.com", "leetcode.cn", "www.leetcode.cn", "www.nowcoder.com", "nowcoder.com",
               "man7.org", "www.postgresql.org", "isocpp.github.io", "docs.vllm.ai", "docs.lmcache.ai",
               "pages.cs.wisc.edu", "www.kernel.org", "docs.kernel.org"}


def _fetchable(url: str) -> str:
    public_url(url)
    p = urlsplit(url)
    if p.scheme != "https" or p.hostname not in FETCH_HOSTS or p.port not in (None, 443):
        raise ValueError("此站暂不支持自动读取；可以保留链接并手动整理。")
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("网页地址未通过公开地址校验")
    return url


class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.in_title = False
        self.title: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer", "header"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "header"}:
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data.strip())
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def preview_source(url: str) -> dict:
    """只应在用户点击读取后调用；不自动将可读正文当作已核验题目。"""
    try:
        current = _fetchable(url)
        with httpx.Client(timeout=12, follow_redirects=False, trust_env=False) as client:
            for _ in range(4):
                with client.stream("GET", current, headers={"User-Agent": "DailyImprove/0.2 (manual link preview)"}) as response:
                    if response.is_redirect:
                        current = _fetchable(urljoin(current, response.headers.get("location", "")))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml")):
                        raise ValueError("此格式请在原站阅读，再手动整理。")
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 512000:
                            raise ValueError("页面过大，请在原站阅读后手动整理。")
                    raw = chunks.decode(response.encoding or "utf-8", errors="replace")
                    parsed = _ReadableHTML()
                    parsed.feed(raw)
                    try:
                        import trafilatura
                        body = trafilatura.extract(raw, include_comments=False) or ""
                    except Exception:
                        body = " ".join(parsed.parts)
                    title = " ".join(parsed.title)[:300]
                    challenge = any(token in (title + " " + body[:500]).lower() for token in ("captcha", "access denied", "verify you are human", "安全验证", "人机验证"))
                    if len(body.strip()) < 300 or challenge:
                        raise ValueError("没有取得足够正文，可能需要登录或页面动态加载；请手动整理。")
                    return {"readable": True, "title": title, "excerpt": re.sub(r"\s+", " ", body).strip()[:350],
                            "url": current, "verification": "unverified", "message": "已读取短摘录，请核对原文后自行确认；未自动提取或核验题目。"}
            raise ValueError("页面跳转过多，请手动整理。")
    except (ValueError, OSError, httpx.HTTPError, LookupError):
        return {"readable": False, "title": "", "excerpt": "", "url": url, "verification": "unverified",
                "message": "暂未取得可核验正文。链接可以照常保存，已有题目和练习不受影响。"}
