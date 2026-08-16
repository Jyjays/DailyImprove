from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.plugins.base import ChannelPlugin, Digest, PushResult
from app.utils.logger import logger


class FileChannel(ChannelPlugin):
    name = "file"

    def push(self, digest: Digest, channel_config: dict[str, Any]) -> PushResult:
        out_dir = Path(channel_config.get("output_dir") or settings.data_dir / "digest")
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = out_dir / f"{digest.module_key}-{datetime.now():%Y%m%d}.md"
        filename.write_text(digest.markdown, encoding="utf-8")
        logger.info("File 推送完成: %s", filename)
        return PushResult(ok=True, channel=self.name, external_id=str(filename), message=str(filename))
