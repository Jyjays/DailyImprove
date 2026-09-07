"""OpenAI 兼容 LLM 客户端。"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings
from app.utils.logger import logger


class EmptyContentError(Exception):
    """模型返回了空正文（常见于推理型模型预算耗尽）。"""


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
        """单轮调用，要求 JSON 输出。失败抛异常。

        重试序列（针对两类常见故障）：
        1. 服务商不支持 response_format → 去掉该参数重试；
        2. 推理型模型把 max_tokens 预算耗在 reasoning 上，导致 content 为空
           → 自动把预算放大 3 倍再试一次。
        """
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
        if settings.llm_disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        plans = [
            (True, max_tokens),
            (False, max_tokens),
            (False, max(4000, max_tokens * 3)),
        ]
        for attempt, (use_json_mode, budget) in enumerate(plans, 1):
            try:
                if use_json_mode:
                    payload["response_format"] = {"type": "json_object"}
                else:
                    payload.pop("response_format", None)
                payload["max_tokens"] = budget
                logger.info("LLM 调用: model=%s, attempt=%d, max_tokens=%d, json_mode=%s",
                            self.model, attempt, budget, use_json_mode)
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                content = (message.get("content") or "").strip()
                if not content:
                    # 推理型模型常见：预算被 reasoning_content 占满，正文为空
                    raise EmptyContentError(
                        f"模型返回空正文（可能推理消耗了全部 max_tokens={budget} 预算）"
                    )
                return self._parse_json(content)
            except httpx.HTTPStatusError as e:
                if attempt < len(plans) and e.response.status_code in (400, 404, 422):
                    continue
                raise
            except EmptyContentError:
                if attempt < len(plans):
                    continue
                raise RuntimeError(
                    f"LLM 返回空正文：模型 {self.model} 可能是推理型，"
                    f"请把模块 YAML 的 llm.max_tokens 提到 8000 以上，或改用非推理模型"
                ) from None
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                if attempt < len(plans):
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
