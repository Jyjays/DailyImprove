from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import settings
from app.plugins.base import ChannelPlugin, Digest, PushResult
from app.utils.logger import logger


class WechatChannel(ChannelPlugin):
    """微信公众号渠道：默认写入草稿箱，避免自动发布风险。"""

    name = "wechat"

    def push(self, digest: Digest, channel_config: dict[str, Any]) -> PushResult:
        if not settings.wechat_app_id or not settings.wechat_app_secret:
            return PushResult(ok=False, channel=self.name, message="微信凭据未配置，跳过")
        try:
            token = self._get_access_token()
            articles = self._build_articles(digest, channel_config)
            target = channel_config.get("target") or settings.wechat_target or "draft"
            if target == "publish":
                url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={token}"
                payload = {"articles": [{k: v for k, v in a.items() if k != "author"} for a in articles]}
                resp = httpx.post(url, json=payload, timeout=30)
            else:
                url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
                payload = {"articles": articles}
                resp = httpx.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "errcode" in data and data["errcode"] != 0:
                return PushResult(ok=False, channel=self.name, message=f"微信返回错误: {data}")
            media_id = data.get("media_id") or data.get("publish_id") or str(data)
            logger.info("微信推送成功: %s（%d 条图文）", media_id, len(articles))
            return PushResult(ok=True, channel=self.name, external_id=media_id)
        except Exception as e:
            logger.exception("微信推送失败")
            return PushResult(ok=False, channel=self.name, message=str(e))

    def _get_access_token(self) -> str:
        url = "https://api.weixin.qq.com/cgi-bin/token"
        resp = httpx.get(url, params={
            "grant_type": "client_credential",
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"获取微信 access_token 失败: {data}")
        return data["access_token"]

    @staticmethod
    def _build_articles(digest: Digest, channel_config: dict[str, Any]) -> list[dict[str, Any]]:
        """多图文：头条为日报导读，后续每条内容独立一篇，各自 content_source_url 指向原文。"""
        author = channel_config.get("author") or "DailyImprove"
        thumb = settings.wechat_thumb_media_id
        articles: list[dict[str, Any]] = []

        overview = {
            "title": digest.title,
            "author": author,
            "digest": (digest.items[0].summary or "")[:120] if digest.items else "",
            "content": WechatChannel._build_overview_html(digest),
            "content_source_url": digest.items[0].url if digest.items else "",
        }
        if thumb:
            overview["thumb_media_id"] = thumb
        articles.append(overview)

        # 微信多图文最多 8 条，头条占 1 条，内容最多再 7 条
        for it in digest.items[:7]:
            art = {
                "title": it.title,
                "author": author,
                "digest": (it.summary or "")[:120],
                "content": WechatChannel._build_item_html(it),
                "content_source_url": it.url or "",
            }
            if thumb:
                art["thumb_media_id"] = thumb
            articles.append(art)
        return articles

    @staticmethod
    def _build_overview_html(digest: Digest) -> str:
        parts = [f"<h1>{digest.title}</h1>", "<p>本期精选内容：</p>", "<ol>"]
        for idx, it in enumerate(digest.items, 1):
            parts.append(f"<li><strong>{idx}. {it.title}</strong>")
            if it.summary:
                parts.append(f"<br/>{it.summary}")
            if it.url:
                parts.append(f'<br/>原文：<a href="{it.url}">{it.url}</a>')
            parts.append("</li>")
        parts.append("</ol>")
        parts.append("<p>点击下方各篇阅读详情。</p>")
        return "".join(parts)

    @staticmethod
    def _build_item_html(it) -> str:
        parts = [f"<h2>{it.title}</h2>"]
        if it.summary:
            parts.append(f"<p><strong>摘要：</strong>{it.summary}</p>")
        if it.llm_reason:
            parts.append(f"<p><strong>入选理由：</strong>{it.llm_reason}</p>")
        parts.append(f"<p><strong>来源：</strong>{it.source_name}（评分 {it.source_rating:.2f}）</p>")
        if it.merged_sources:
            parts.append(f"<p><strong>另见来源：</strong>{it.merged_sources}</p>")
        if it.url:
            parts.append(f'<p><a href="{it.url}">阅读原文</a></p>')
            parts.append(f"<p>原文地址：{it.url}</p>")
        return "".join(parts)
