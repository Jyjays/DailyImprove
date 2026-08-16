import argparse

from app.models.db import init_db
from app.orchestrator import run_module

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="手动运行信息模块")
    parser.add_argument("module_key", help="模块 key，如 tech-blog")
    args = parser.parse_args()
    init_db()
    run_module(args.module_key, manual=True)
