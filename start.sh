#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# 优先使用本地 .deps 目录，避免依赖系统 site-packages
if [ -d .deps ]; then
  export PYTHONPATH=".deps:${PYTHONPATH:-}"
fi

# 依赖自检：缺少关键依赖时自动安装到 .deps（仅本地运行使用）
if ! python3 -c "import yaml, fastapi, sqlalchemy, apscheduler, feedparser, httpx, jinja2" >/dev/null 2>&1; then
  echo "[start.sh] 检测到缺少运行依赖，正在安装到 .deps ..." >&2
  pip3 install --target .deps --no-cache-dir --break-system-packages -q \
    fastapi uvicorn sqlalchemy 'apscheduler<4' feedparser httpx python-multipart pyyaml jinja2 markupsafe
fi

exec python3 -m uvicorn app.main:app --host "${WEB_HOST:-127.0.0.1}" --port "${WEB_PORT:-8000}"
