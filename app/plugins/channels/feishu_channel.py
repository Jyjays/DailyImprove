from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.plugins.base import ChannelPlugin, Digest, PushResult
from app.utils.logger import logger


class FeishuDocChannel(ChannelPlugin):
    """飞书渠道：创建云文档 + 可选归档到多维表格。"""

    name = "feishu_doc"

    def push(self, digest: Digest, channel_config: dict[str, Any]) -> PushResult:
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            return PushResult(ok=False, channel=self.name, message="飞书凭据未配置，跳过")
        try:
            token = self._get_tenant_token()
            doc_id = self._create_doc(token, digest.title)
            self._write_blocks(token, doc_id, digest)
            doc_url = f"https://feishu.cn/docx/{doc_id}"
            if channel_config.get("archive_to_bitable") and settings.feishu_bitable_app_token and settings.feishu_bitable_table_id:
                self._archive_bitable(token, digest, doc_url)
            logger.info("飞书文档推送成功: %s", doc_url)
            return PushResult(ok=True, channel=self.name, external_id=doc_id, message=doc_url)
        except Exception as e:
            logger.exception("飞书推送失败")
            return PushResult(ok=False, channel=self.name, message=str(e))

    def _get_tenant_token(self) -> str:
        url = f"{settings.feishu_base}/open-apis/auth/v3/tenant_access_token/internal"
        resp = httpx.post(url, json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code")
        if code != 0:
            raise RuntimeError(f"获取飞书 tenant_access_token 失败: {data}")
        return data["tenant_access_token"]

    def _create_doc(self, token: str, title: str) -> str:
        url = f"{settings.feishu_base}/open-apis/docx/v1/documents"
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          json={"title": title}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"创建飞书文档失败: {data}")
        return data["data"]["document"]["document_id"]

    def _write_blocks(self, token: str, doc_id: str, digest: Digest) -> None:
        blocks: list[dict[str, Any]] = [
            {"block_type": 3, "heading1": {"elements": [{"text_run": {"content": digest.title}}]}},
            {"block_type": 22, "divider": {}},
        ]
        for idx, it in enumerate(digest.items, 1):
            blocks.append({"block_type": 4, "heading2": {"elements": [{"text_run": {"content": f"{idx}. {it.title}"}}]}})
            if it.url:
                blocks.append({"block_type": 12, "bullet": {"elements": [{"text_run": {"content": "原文链接：", "text_element_style": {"link": {"url": it.url}}}}]}})
            blocks.append({"block_type": 12, "bullet": {"elements": [{"text_run": {"content": f"来源：{it.source_name}（评分 {it.source_rating:.2f}）"}}]}})
            if it.summary:
                blocks.append({"block_type": 12, "bullet": {"elements": [{"text_run": {"content": f"摘要：{it.summary}"}}]}})
            if it.llm_reason:
                blocks.append({"block_type": 12, "bullet": {"elements": [{"text_run": {"content": f"入选理由：{it.llm_reason}"}}]}})
        url = f"{settings.feishu_base}/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          json={"children": blocks}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"写入飞书文档失败: {data}")

    def _archive_bitable(self, token: str, digest: Digest, doc_url: str) -> None:
        url = f"{settings.feishu_base}/open-apis/bitable/v1/apps/{settings.feishu_bitable_app_token}/tables/{settings.feishu_bitable_table_id}/records"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        for it in digest.items:
            record = {
                "fields": {
                    "标题": it.title,
                    "模块": digest.module_name,
                    "来源": it.source_name,
                    "链接": {"link": it.url, "text": it.title} if it.url else "",
                    "日期": datetime.now().strftime("%Y-%m-%d"),
                    "文档": {"link": doc_url, "text": digest.title},
                }
            }
            resp = httpx.post(url, headers=headers, json={"records": [record]}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("归档 Bitable 失败: %s", data)
