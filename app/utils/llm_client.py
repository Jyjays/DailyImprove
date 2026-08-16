"""OpenAI 兼容 LLM 客户端。"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings
from app.utils.logger import logger


class LLMClient:
    def __init__(self, api_base: str | None = None, api_key: str | None = None, model: str | None = None):
        self.api_base = (api_base or settings.llm_api_base).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = settings.llm_timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat_json(self, system: str, user: str, temperature: float = 0.1, max_tokens: int = 2000) -> Any:
        """单轮调用，尽量要求 JSON 输出。失败抛异常。"""
        if not self.available:
            raise RuntimeError("LLM API key 未配置")
        url = f"{self.api_base}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # 部分服务商不支持 response_format，失败后自动重试一次不带该参数
        for attempt in (1, 2):
            try:
                if attempt == 1:
                    payload["response_format"] = {"type": "json_object"}
                else:
                    payload.pop("response_format", None)
                logger.info("LLM 调用: model=%s, attempt=%d", self.model, attempt)
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return self._parse_json(content)
            except httpx.HTTPStatusError as e:
                if attempt == 1 and e.response.status_code in (400, 404):
                    continue
                raise
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                if attempt == 1:
                    continue
                raise RuntimeError(f"LLM 返回解析失败: {e}") from e
        raise RuntimeError("LLM 调用失败")

    @staticmethod
    def _parse_json(content: str) -> Any:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 提取 ```json ... ``` 代码块
            m = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
            if m:
                return json.loads(m.group(1).strip())
            # 提取第一个 { ... } 块
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start:end + 1])
            raise
