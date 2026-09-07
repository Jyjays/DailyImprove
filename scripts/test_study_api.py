"""学习平台 API 冒烟测试。"""
import json
import time

import httpx

BASE = "http://127.0.0.1:8000"


def wait_up(timeout=40):
    for _ in range(timeout):
        try:
            r = httpx.get(f"{BASE}/api/status", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def show(name, resp):
    ok = 200 <= resp.status_code < 300
    print(f"[{'OK ' if ok else 'ERR'}] {name}  HTTP {resp.status_code}")
    if not ok:
        print("     ", resp.text[:300])
        return None
    try:
        return resp.json()
    except Exception:
        print("      非 JSON 响应")
        return None


if not wait_up():
    print("后端未启动，退出")
    raise SystemExit(1)

print("=" * 60)
print("后端已就绪")
print("=" * 60)

# 1. 知识条目
d = show("GET /api/study/knowledge?limit=5", httpx.get(f"{BASE}/api/study/knowledge?limit=5", timeout=15))
if d:
    print(f"     total={d['total']}  返回 {len(d['items'])} 条")
    for it in d["items"][:3]:
        print(f"     - [{it['id']}] {it['title'][:48]}")
        print(f"       ai摘要: {'有' if it['has_ai_summary'] else '无'} | 标签: {it['tags']} | 分: {it['score']}")
        if it["ai_summary"]:
            print(f"       摘要: {it['ai_summary'][:70]}")

# 2. 今日计划
d = show("GET /api/study/today", httpx.get(f"{BASE}/api/study/today", timeout=15))
if d:
    print(f"     日期={d['date']} 存在={d['exists']} 源文件={d['source_file']}")
    print(f"     打卡项 {len(d['checklist'])} 条:")
    for c in d["checklist"]:
        print(f"       [{c['mark']}] {c['text'][:52]} -> {c['status']}")

# 3. 打卡写入
payload = {
    "date": d["date"] if d else "2026-09-07",
    "items": [
        {"category": "ai-infra", "status": "partial", "note": "E02 复现完成，perf c2c 待补"},
        {"category": "paper", "status": "todo", "note": ""},
    ],
}
d2 = show("POST /api/study/checkin", httpx.post(f"{BASE}/api/study/checkin", json=payload, timeout=15))
if d2:
    print(f"     落库={d2['saved']}  md回写={d2['md_written']} ({d2['md_file']})")

d3 = show("GET /api/study/checkin", httpx.get(f"{BASE}/api/study/checkin", timeout=15))
if d3:
    print(f"     读回 {len(d3['items'])} 条: {[(i['category'], i['status']) for i in d3['items']]}")

# 4. 课程
d4 = show("GET /api/study/courses", httpx.get(f"{BASE}/api/study/courses", timeout=15))
if d4:
    print(f"     课程 {d4['total']} 门")

print("=" * 60)