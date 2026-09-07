"""清空抓取产物，恢复"从未运行过"的状态，保留模块与来源配置（含来源评分）。

用途：
    手动试跑会把条目标记为 pushed，persistent 模块会**永久去重**——
    这些条目以后再也不会出现在推送里。试跑之后用它清干净即可。

用法：
    python scripts/reset_items.py            # 清空 items / push_records / feedback / runs
    python scripts/reset_items.py --runs      # 只清空运行日志
    python scripts/reset_items.py --yes       # 跳过确认

注意：来源评分（sources.rating_avg / rating_count）不会被清除。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.models.db import SessionLocal, init_db  # noqa: E402

TABLES = ["items", "push_records", "feedback", "runs"]


def main() -> int:
    ap = argparse.ArgumentParser(description="清空 DailyImprove 抓取产物")
    ap.add_argument("--runs", action="store_true", help="只清空运行日志")
    ap.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    args = ap.parse_args()

    targets = ["runs"] if args.runs else TABLES
    if not args.yes:
        print("即将清空以下表的数据：", ", ".join(targets))
        ans = input("确认请输入 y（其它任意键取消）: ").strip().lower()
        if ans != "y":
            print("已取消。")
            return 1

    init_db()
    session = SessionLocal()
    try:
        for t in targets:
            n = session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            session.execute(text(f"DELETE FROM {t}"))
            print(f"  {t:14s} 删除 {n} 行")
        session.commit()
        print("完成。来源配置与评分已保留。")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
