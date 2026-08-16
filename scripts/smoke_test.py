"""端到端冒烟测试：同步模块 -> 运行模块 -> 打印结果。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.db import SessionLocal, init_db
from app.models.models import Item, Module, RunRecord, Source
from app.module_loader import sync_all_modules
from app.orchestrator import run_module


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        cfgs = sync_all_modules(session)
        print(f"已同步 {len(cfgs)} 个模块:")
        for cfg in cfgs:
            print(f"  - {cfg.key}: {cfg.name} ({len(cfg.sources)} 个来源)")
    finally:
        session.close()

    key = os.environ.get("SMOKE_MODULE", "tech-blog")
    print(f"\n开始运行模块: {key}")
    run = run_module(key, manual=True)
    print(f"运行结果: status={run.status}, fetched={run.fetched_count}, "
          f"after_dedup={run.after_dedup_count}, after_filter={run.after_filter_count}, "
          f"selected={run.selected_count}, pushed={run.pushed_count}")

    session = SessionLocal()
    try:
        items = list(session.query(Item).filter(Item.module_id == run.module_id)
                     .order_by(Item.fetched_at.desc()).limit(10).all())
        print(f"\n最近条目（{len(items)}）:")
        for it in items:
            print(f"  [{it.status}] {it.title[:60]} | score={it.final_score} | {it.url}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
