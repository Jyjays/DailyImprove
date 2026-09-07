"""手动运行一次（或全部）模块，供命令行 / 自动化调用，无需常驻 Web 服务。

用法：
    python scripts/run_daily.py                          # 运行所有启用的模块
    python scripts/run_daily.py agent-memory-papers      # 只跑指定模块（可多个）
    python scripts/run_daily.py --all --summary          # 跑全部并把结果写入 plan/daily/<日期>-sources.md
    python scripts/run_daily.py --list                   # 列出已同步的模块

说明：
    - 本脚本会先同步 modules/*.yaml 到数据库，再依次执行。
    - 单个来源或单个模块失败不影响其他模块，失败会记在最后的汇总里。
    - 摘要文件写入 plan/daily/<日期>-sources.md，供当天日报消费。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.models.db import SessionLocal, init_db  # noqa: E402
from app.models.models import Item, Module, RunRecord  # noqa: E402
from app.module_loader import sync_all_modules  # noqa: E402
from app.orchestrator import ModuleRunner  # noqa: E402


def sync_and_list(session) -> list[str]:
    cfgs = sync_all_modules(session)
    return [c.key for c in cfgs]


def pick_modules(session, wanted: list[str], run_all: bool) -> list[str]:
    rows = list(session.execute(
        select(Module).where(Module.enabled == 1).order_by(Module.id)
    ).scalars())
    keys = [m.key for m in rows]
    if wanted:
        unknown = [k for k in wanted if k not in keys]
        if unknown:
            print(f"[警告] 以下模块不存在或未启用，已跳过: {', '.join(unknown)}")
        return [k for k in keys if k in wanted]
    if run_all:
        return keys
    return keys


def latest_items(session, module_key: str, limit: int = 10):
    module = session.execute(select(Module).where(Module.key == module_key)).scalar_one_or_none()
    if module is None:
        return []
    rows = list(session.execute(
        select(Item).where(Item.module_id == module.id, Item.status.in_(["selected", "pushed"]))
        .order_by(Item.final_score.desc()).limit(limit)
    ).scalars())
    return rows


def render_summary(session, module_keys: list[str], results: dict) -> str:
    now = datetime.now()
    lines = [
        f"# 信息源产出 · {now:%Y-%m-%d %H:%M}",
        "",
        "> 由 `scripts/run_daily.py` 自动生成，供当天日报消费。",
        "",
    ]
    for key in module_keys:
        r = results.get(key)
        name = r["name"] if r else key
        lines.append(f"## {name}（{key}）")
        if not r:
            lines.append("")
            lines.append("未运行。")
            lines.append("")
            continue
        if r["ok"]:
            lines.append(
                f"\n抓取 {r['fetched']} → 去重后 {r['dedup']} → 过滤后 {r['filtered']} "
                f"→ 入选 {r['selected']} → 推送 {r['pushed']}"
            )
        else:
            lines.append(f"\n**运行失败**：{r['error']}")
        items = latest_items(session, key)
        if items:
            lines.append("")
            for it in items:
                score = f"{it.final_score:.1f}" if it.final_score is not None else "-"
                lines.append(f"- **{it.title}**（综合分 {score}）")
                if it.url:
                    lines.append(f"  - 链接：{it.url}")
                meta = {}
                if it.llm_output:
                    try:
                        meta = json.loads(it.llm_output) or {}
                    except Exception:
                        meta = {}
                # 优先用 LLM 生成的中文摘要，没有则回退原始摘要
                summary = (meta.get("summary") or "").strip() or (it.summary or "").strip()
                if summary:
                    lines.append(f"  - 摘要：{summary[:400]}")
                bits = []
                if meta.get("reason"):
                    bits.append(f"入选理由 {meta['reason']}")
                if meta.get("tags"):
                    bits.append("标签 " + "/".join(meta["tags"]))
                if bits:
                    lines.append(f"  - {'；'.join(bits)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="手动运行 DailyImprove 模块")
    ap.add_argument("modules", nargs="*", help="模块 key，留空表示所有启用模块")
    ap.add_argument("--all", action="store_true", help="显式运行所有启用模块")
    ap.add_argument("--list", action="store_true", help="只列出模块，不运行")
    ap.add_argument("--summary", action="store_true", help="把结果写入 plan/daily/<日期>-sources.md")
    args = ap.parse_args()

    init_db()
    session = SessionLocal()
    try:
        keys = sync_and_list(session)
        if args.list:
            for k in keys:
                print(k)
            return 0

        targets = pick_modules(session, args.modules, args.all or not args.modules)
        if not targets:
            print("没有可运行的模块。")
            return 1

        results: dict[str, dict] = {}
        for key in targets:
            module = session.execute(select(Module).where(Module.key == key)).scalar_one_or_none()
            name = module.name if module else key
            print(f"--- 运行模块: {name} ({key}) ---")
            try:
                run: RunRecord = ModuleRunner(session).run(key, manual=True)
                results[key] = {
                    "name": name, "ok": True,
                    "fetched": run.fetched_count, "dedup": run.after_dedup_count,
                    "filtered": run.after_filter_count, "selected": run.selected_count,
                    "pushed": run.pushed_count, "error": "",
                }
                print(f"    抓取 {run.fetched_count} → 入选 {run.selected_count} → 推送 {run.pushed_count}")
            except Exception as e:
                results[key] = {"name": name, "ok": False, "error": str(e)[:300],
                                "fetched": 0, "dedup": 0, "filtered": 0, "selected": 0, "pushed": 0}
                print(f"    失败: {e}")

        if args.summary:
            out_dir = ROOT / "plan" / "daily"
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{datetime.now():%Y-%m-%d}-sources.md"
            out.write_text(render_summary(session, targets, results), encoding="utf-8")
            print(f"\n摘要已写入: {out}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
