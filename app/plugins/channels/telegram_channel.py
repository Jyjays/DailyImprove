from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.plugins.base import ChannelPlugin, Digest, PushResult
from app.utils.logger import logger


class TelegramChannel(ChannelPlugin):
    name = "telegram"

    def push(self, digest: Digest, channel_config: dict[str, Any]) -> PushResult:
        token = channel_config.get("bot_token") or settings.telegram_bot_token
        chat_id = channel_config.get("chat_id") or settings.telegram_chat_id
        if not token or not chat_id:
            return PushResult(ok=False, channel=self.name, message="Telegram 凭据未配置，跳过")
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = httpx.post(url, json={"chat_id": chat_id, "text": digest.markdown[:4000]}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return PushResult(ok=False, channel=self.name, message=str(data))
            return PushResult(ok=True, channel=self.name, external_id=str(data["result"]["message_id"]))
        except Exception as e:
            logger.exception("Telegram 推送失败")
            return PushResult(ok=False, channel=self.name, message=str(e))
