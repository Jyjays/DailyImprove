"""清空指定模块的抓取/推送记录，便于重新测试推送。

用法:
    PYTHONPATH=.deps:. python3 scripts/reset_module.py tech-blog
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.models.db import SessionLocal, init_db
from app.models.models import Item, Module, PushRecord


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python3 scripts/reset_module.py <module_key>")
        sys.exit(1)
    key = sys.argv[1]
    init_db()
    session = SessionLocal()
    try:
        module = session.execute(select(Module).where(Module.key == key)).scalar_one_or_none()
        if module is None:
            print(f"模块不存在: {key}")
            sys.exit(1)
        item_ids = list(session.execute(select(Item.id).where(Item.module_id == module.id)).scalars())
        if item_ids:
            for pid in list(session.execute(select(PushRecord.id).where(PushRecord.module_id == module.id)).scalars()):
                pr = session.get(PushRecord, pid)
                if pr:
                    session.delete(pr)
            for iid in item_ids:
                item = session.get(Item, iid)
                if item:
                    session.delete(item)
        session.commit()
        print(f"已清空模块 {key} 的 {len(item_ids)} 条记录，可以重新测试推送")
    finally:
        session.close()


if __name__ == "__main__":
    main()
