# -*- coding: utf-8 -*-
"""
把本地 DailyImprove 的 md 资产同步到云端资料库（单向：本地 → 云端）。

设计约定
- 云端是**只读快照**：本地改了跑一次脚本才上来；手机上在云端勾的 checkbox 不会回写本地。
- 「已存在 id」的文档走**全量覆盖**（create_doc.py --confirm-overwrite），
  所以云端对同名文档的手动修改会在下次同步时被本地覆盖 —— 要改就改本地。
- 新出现的日报文件自动创建，并把新 id 回写进映射表。

用法
    # 由助手/自动化调用：先通过 connect_open_platform 取 token，再传入
    python scripts/sync_to_cloud.py --token <op_xxx>
    python scripts/sync_to_cloud.py --token-stdin      # token 从 stdin 首行读

    python scripts/sync_to_cloud.py --token <op_xxx> --only daily   # 只同步日报
    python scripts/sync_to_cloud.py --dry-run                       # 不联网，只打印计划

依赖
    资料库 skill 的 create_doc.py。路径按优先级：
    环境变量 WORK_BUDDY_LIBRARY_DIR > 默认安装路径。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / ".workbuddy" / "cloud-sync-map.json"

DEFAULT_LIBRARY_DIR = Path(
    r"D:/Tools/WorkBuddy/resources/app.asar.unpacked"
    r"/resources/plugins/workbuddy-builtin/skills/library"
)


def library_dir() -> Path:
    env = os.environ.get("WORK_BUDDY_LIBRARY_DIR")
    return Path(env) if env else DEFAULT_LIBRARY_DIR


def load_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def save_map(m: dict) -> None:
    MAP_PATH.write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_create_doc(token: str, *, title: str, content_file: Path, space_id: str,
                   parent_id: str | None = None, node_block_id: str | None = None,
                   dry_run: bool = False) -> tuple[bool, str]:
    """调资料库 create_doc.py。返回 (是否成功, 人类可读结果)。"""
    script = library_dir() / "doc" / "create_doc.py"
    if not script.exists():
        return False, f"找不到 create_doc.py：{script}"

    cmd = [sys.executable, str(script), "--token-stdin",
           "--space-id", space_id, "--title", title,
           "--content-file", str(content_file)]
    if node_block_id:
        cmd += ["--node-block-id", node_block_id, "--confirm-overwrite"]
    else:
        cmd += ["--parent-id", parent_id]

    if dry_run:
        return True, f"[dry-run] {'覆盖' if node_block_id else '新建'}《{title}》"

    proc = subprocess.run(cmd, input=token, capture_output=True, text=True,
                          encoding="utf-8")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, f"退出码 {proc.returncode}：{out.strip()[:300]}"
    if out.strip().startswith("{"):                      # {"error": ...}
        return False, f"接口报错：{out.strip()[:300]}"
    m = re.search(r"https://\S+", out)
    return True, (m.group(0) if m else out.strip()[:200])


def sync_fixed(token: str, m: dict, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for d in m["docs"]:
        local = ROOT / d["path"]
        if not local.exists():
            print(f"  [跳过] 本地不存在：{d['path']}")
            fail += 1
            continue
        good, msg = run_create_doc(
            token, title=d["title"], content_file=local,
            space_id=m["space_id"], parent_id=m["folders"][d["parent"]],
            node_block_id=d.get("id"), dry_run=dry_run,
        )
        print(f"  [{'OK' if good else 'FAIL'}] {d['title']} → {msg}")
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
    return ok, fail


def sync_daily(token: str, m: dict, dry_run: bool) -> tuple[int, int]:
    cfg = m["daily"]
    d = ROOT / cfg["dir"]
    known: dict = cfg.setdefault("known", {})
    ok = fail = 0
    for f in sorted(d.glob("*.md")):
        if any(f.name.endswith(s) for s in cfg["exclude_suffix"]):
            continue
        date = f.stem                                    # 2026-09-09 或 2026-09-09-2
        title = cfg["title_tpl"].format(date=date)
        nid = known.get(f.name)
        good, msg = run_create_doc(
            token, title=title, content_file=f,
            space_id=m["space_id"], parent_id=m["folders"][cfg["parent"]],
            node_block_id=nid, dry_run=dry_run,
        )
        print(f"  [{'OK' if good else 'FAIL'}] {title} → {msg}")
        if good and not nid and not dry_run:
            url_m = re.search(r"/space/d/([A-Za-z0-9]+)", msg)
            if url_m:
                known[f.name] = url_m.group(1)
                save_map(m)
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
    return ok, fail


def sync_nav(token: str, m: dict, dry_run: bool) -> tuple[int, int]:
    nav = m["nav"]
    local = ROOT / nav["local_md"]
    if not local.exists():
        print("  [跳过] 导航页本地文件不存在")
        return 0, 0
    good, msg = run_create_doc(
        token, title=nav["title"], content_file=local,
        space_id=m["space_id"], parent_id=m["folders"]["root"],
        node_block_id=nav.get("id"), dry_run=dry_run,
    )
    print(f"  [{'OK' if good else 'FAIL'}] {nav['title']} → {msg}")
    return (1, 0) if good else (0, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token")
    ap.add_argument("--token-stdin", action="store_true")
    ap.add_argument("--only", choices=["docs", "daily", "nav"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = args.token or ""
    if args.token_stdin and not token:
        token = sys.stdin.readline().strip()
    if not token and not args.dry_run:
        print("缺少 token：用 --token 或 --token-stdin（由 connect_open_platform 取得）")
        return 2

    m = load_map()
    total_ok = total_fail = 0

    if args.only in (None, "docs"):
        print("== 固定文档 ==")
        o, f = sync_fixed(token, m, args.dry_run); total_ok += o; total_fail += f
    if args.only in (None, "daily"):
        print("== 日报 ==")
        o, f = sync_daily(token, m, args.dry_run); total_ok += o; total_fail += f
    if args.only in (None, "nav"):
        print("== 导航页 ==")
        o, f = sync_nav(token, m, args.dry_run); total_ok += o; total_fail += f

    print(f"\n完成：成功 {total_ok} · 失败 {total_fail}")
    print(f"云端根目录：https://www.workbuddy.cn/space/d/{m['folders']['root']}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
