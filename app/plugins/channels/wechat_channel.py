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
            article = {
                "title": digest.title,
                "author": channel_config.get("author") or "DailyImprove",
                "digest": digest.items[0].summary if digest.items else "",
                "content": self._build_html(digest),
                "content_source_url": digest.items[0].url if digest.items else "",
            }
            if settings.wechat_thumb_media_id:
                article["thumb_media_id"] = settings.wechat_thumb_media_id
            target = channel_config.get("target") or settings.wechat_target or "draft"
            if target == "publish":
                url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={token}"
                payload = {"articles": {k: v for k, v in article.items() if k != "author"}}
                resp = httpx.post(url, json=payload, timeout=30)
            else:
                url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
                payload = {"articles": [article]}
                resp = httpx.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "errcode" in data and data["errcode"] != 0:
                return PushResult(ok=False, channel=self.name, message=f"微信返回错误: {data}")
            media_id = data.get("media_id") or data.get("publish_id") or str(data)
            logger.info("微信推送成功: %s", media_id)
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
    def _build_html(digest: Digest) -> str:
        parts = [f"<h1>{digest.title}</h1>"]
        for idx, it in enumerate(digest.items, 1):
            parts.append(f"<h2>{idx}. {it.title}</h2>")
            if it.url:
                parts.append(f"<p><a href=\"{it.url}\">原文链接</a></p>")
            parts.append(f"<p><strong>来源：</strong>{it.source_name}（评分 {it.source_rating:.2f}）</p>")
            if it.summary:
                parts.append(f"<p>{it.summary}</p>")
            if it.llm_reason:
                parts.append(f"<p>入选理由：{it.llm_reason}</p>")
            parts.append("<hr/>")
        return "".join(parts)
