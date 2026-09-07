"""全局配置：从环境变量 / .env 读取。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path | None = None) -> None:
    """极简 .env 加载器，避免额外依赖。"""
    dotenv_path = path or BASE_DIR / ".env"
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_bool(key: str, default: bool = False) -> bool:
    val = _get(key, str(default)).lower()
    return val in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(_get("DATA_DIR", str(BASE_DIR / "data")))
        self.database_url = _get("DATABASE_URL", f"sqlite:///{self.data_dir / 'dailyimprove.db'}")
        self.modules_dir = Path(_get("MODULES_DIR", str(BASE_DIR / "modules")))

        # LLM（OpenAI 兼容接口）
        self.llm_api_base = _get("LLM_API_BASE", "https://api.openai.com/v1")
        self.llm_api_key = _get("LLM_API_KEY", "")
        self.llm_model = _get("LLM_MODEL", "gpt-4o-mini")
        self.llm_timeout = float(_get("LLM_TIMEOUT", "60"))
        # 推理型模型（如 deepseek-v4 系列）默认会先产出 reasoning token，
        # 对"批量筛选 + 摘要"这类任务没有必要，且会拖慢 3 倍、吃掉输出预算。
        # 设为 true 时请求体带上 thinking:{"type":"disabled"}。
        self.llm_disable_thinking = _get_bool("LLM_DISABLE_THINKING", False)

        # Web 控制台
        self.web_host = _get("WEB_HOST", "127.0.0.1")
        self.web_port = int(_get("WEB_PORT", "8000"))

        # 微信公众号
        self.wechat_app_id = _get("WECHAT_APP_ID", "")
        self.wechat_app_secret = _get("WECHAT_APP_SECRET", "")
        self.wechat_target = _get("WECHAT_TARGET", "draft")  # draft | publish
        self.wechat_thumb_media_id = _get("WECHAT_THUMB_MEDIA_ID", "")

        # 飞书开放平台
        self.feishu_app_id = _get("FEISHU_APP_ID", "")
        self.feishu_app_secret = _get("FEISHU_APP_SECRET", "")
        self.feishu_base = _get("FEISHU_BASE", "https://open.feishu.cn")
        self.feishu_folder_token = _get("FEISHU_FOLDER_TOKEN", "")
        self.feishu_bitable_app_token = _get("FEISHU_BITABLE_APP_TOKEN", "")
        self.feishu_bitable_table_id = _get("FEISHU_BITABLE_TABLE_ID", "")

        # Telegram（可选，便于自测）
        self.telegram_bot_token = _get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = _get("TELEGRAM_CHAT_ID", "")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.modules_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
