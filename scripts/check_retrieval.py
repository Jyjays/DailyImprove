"""检查各模块来源能否正常抓取，验证检索链路。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.models.db import SessionLocal, init_db
from app.models.models import Source
from app.plugins.base import SourceContext
from app.plugins.sources import get_source_plugin


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        sources = list(session.execute(select(Source)).scalars())
        if not sources:
            print("没有来源，请先在 modules/ 配置模块并同步")
            return
        for s in sources:
            ctx = SourceContext(
                id=s.id, name=s.name, type=s.type, url=s.url,
                module_key=s.module.key, module_name=s.module.name,
                lifetime=s.module.lifetime, base_weight=s.base_weight,
            )
            try:
                plugin = get_source_plugin(s.type)
                items = plugin.fetch(ctx)
                print(f"✅ {s.name} [{s.type}] 抓取成功：{len(items)} 条")
                for it in items[:3]:
                    print(f"   - {it.title[:70]}")
            except Exception as e:
                print(f"❌ {s.name} [{s.type}] 抓取失败：{e}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
