"""清理过期 ephemeral 条目。可加入 cron 每日执行。"""
from datetime import datetime, timedelta

from app.models.db import SessionLocal, init_db
from app.models.models import Item, PushRecord


def purge() -> None:
    init_db()
    session = SessionLocal()
    try:
        now = datetime.now()
        for module in session.query(Item.module_id).filter(Item.lifetime == "ephemeral").distinct():
            pass
        # 简化策略：删除 fetched_at 超过 7 天的所有 ephemeral 条目（去重窗口默认 3 天）
        cutoff = now - timedelta(days=7)
        items = session.query(Item).filter(Item.lifetime == "ephemeral", Item.fetched_at < cutoff).all()
        ids = [it.id for it in items]
        if ids:
            session.query(PushRecord).filter(PushRecord.item_id.in_(ids)).delete(synchronize_session=False)
            for it in items:
                session.delete(it)
            session.commit()
            print(f"清理 {len(ids)} 条过期 ephemeral 条目")
        else:
            print("无过期条目")
    finally:
        session.close()


if __name__ == "__main__":
    purge()
