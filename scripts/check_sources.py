"""体检所有模块的 RSS/API 来源，输出可达性、条目数与最新条目时间。

用法：
    python scripts/check_sources.py              # 体检所有启用模块
    python scripts/check_sources.py --all        # 包含停用模块
    python scripts/check_sources.py ai-infra     # 只体检指定模块

判读：
    OK      正常，条目数 > 0
    空源    能连通但没有条目（可能源已改版或查询条件过严）
    失败    连不通（网络受限 / 源下线 / 需要代理）
    —— 注意：本脚本所在环境若走了代理，失败不代表源真的失效，换台机器再验一次。

建议每月跑一次，或发现某模块长期没有新内容时跑。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import feedparser  # noqa: E402
import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.module_loader import list_module_files, load_module_yaml  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 DailyImprove/0.1"
TIMEOUT = 25


def check(url: str) -> tuple[str, int, str]:
    """返回 (状态, 条目数, 说明)。"""
    try:
        resp = httpx.get(url, timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": UA})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        n = len(parsed.entries)
        latest = ""
        for e in parsed.entries[:1]:
            for attr in ("published_parsed", "updated_parsed"):
                tt = e.get(attr)
                if tt:
                    try:
                        latest = datetime(*tt[:6]).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                    break
        if n == 0:
            return "空源", 0, f"HTTP {resp.status_code} 但解析不到条目（源可能已改版）"
        return "OK", n, f"HTTP {resp.status_code}，最新 {latest or '未知'}"
    except Exception as e:
        return "失败", 0, f"{type(e).__name__}: {str(e)[:70]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="体检 DailyImprove 信息源")
    ap.add_argument("modules", nargs="*", help="模块 key，留空表示全部")
    ap.add_argument("--all", action="store_true", help="包含停用模块")
    args = ap.parse_args()

    files = list_module_files(settings.modules_dir)
    bad_total = 0
    for path in files:
        try:
            cfg = load_module_yaml(path)
        except Exception as e:
            print(f"\n[{path.name}] 配置加载失败: {e}")
            continue
        if args.modules and cfg.key not in args.modules:
            continue
        if not cfg.enabled and not args.all:
            continue
        print(f"\n=== {cfg.name} ({cfg.key}) {'[停用]' if not cfg.enabled else ''} ===")
        for src in cfg.sources:
            status, n, note = check(src.url)
            if status != "OK":
                bad_total += 1
            print(f"  [{status}] {src.name:28s} 条目={n:4d}  {note}")
    print(f"\n体检完成，异常源 {bad_total} 个。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
