"""把 roadmap 里的课程导入 courses 表。

所有链接均已核实（2026-09-07）。resources 里的条目若标注"待补"，说明没有把握的公开链接，不编造。
重复运行不会重复插入：按 title 去重。
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000/api/study"

COURSES = [
    # ---------------- Phase 0 基础回填 ----------------
    {
        "title": "CMU 15-213 CS:APP（深入理解计算机系统）",
        "provider": "Carnegie Mellon University",
        "url": "http://csapp.cs.cmu.edu/",
        "description": "只挑三章：Ch5 优化程序性能、Ch6 存储器层次、Ch9 虚拟内存。"
                       "配《深入理解计算机系统》第 3 版，做 Ch6 的 cache 实验。",
        "track": "ai-infra", "phase": "P0", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "课程官网（含实验资料）", "url": "http://csapp.cs.cmu.edu/", "type": "官网"},
            {"name": "Cache Lab / Malloc Lab（Ch6、Ch9 配套实验）", "url": "http://csapp.cs.cmu.edu/3e/labs.html", "type": "实验"},
        ],
    },
    {
        "title": "南京大学 操作系统（蒋炎岩 jyy）",
        "provider": "南京大学",
        "url": "https://jyywiki.cn/",
        "description": "中文最好的 OS 课，前 12 讲够用。讲义与实验代码都在 jyywiki。",
        "track": "ai-infra", "phase": "P0", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "jyywiki 课程主页", "url": "https://jyywiki.cn/", "type": "官网"},
            {"name": "视频：B 站搜索「操作系统 蒋炎岩」（具体链接待补）", "url": "https://jyywiki.cn/", "type": "视频"},
        ],
    },
    {
        "title": "CMU 15-445 数据库系统（可选）",
        "provider": "Carnegie Mellon University",
        "url": "https://15445.courses.cs.cmu.edu/",
        "description": "你有列存经历，只建议看 Buffer Pool / Query Execution 两节做对照，不要全刷。",
        "track": "ai-infra", "phase": "P0", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "课程官网", "url": "https://15445.courses.cs.cmu.edu/", "type": "官网"},
        ],
    },
    # ---------------- Phase 1 GPU 编程 ----------------
    {
        "title": "UIUC ECE 408 Applied Parallel Programming",
        "provider": "UIUC（Wen-mei Hwu）",
        "url": "https://ece.illinois.edu/academics/courses/ece408",
        "description": "最对口的 CUDA 课。作业就是写 CUDA kernel（向量加、矩阵乘、tiling、reduction、scan、卷积、SpMV）。"
                       "教材为《Programming Massively Parallel Processors》。",
        "track": "ai-infra", "phase": "P1", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "课程官网", "url": "https://ece.illinois.edu/academics/courses/ece408", "type": "官网"},
            {"name": "教材：Programming Massively Parallel Processors（第 4 版）", "url": "https://ece.illinois.edu/academics/courses/ece408", "type": "教材"},
        ],
    },
    {
        "title": "CMU 15-418/618 Parallel Computer Architecture and Programming",
        "provider": "Carnegie Mellon University",
        "url": "https://www.cs.cmu.edu/~418/",
        "description": "讲义质量极高，偏体系化理解，GPU 部分讲得深。与 ECE 408 二选一或互补。",
        "track": "ai-infra", "phase": "P1", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "课程官网（含讲义与作业）", "url": "https://www.cs.cmu.edu/~418/", "type": "官网"},
        ],
    },
    # ---------------- Phase 2 深度学习系统 ----------------
    {
        "title": "CMU 10-414/714 Deep Learning Systems（needle）",
        "provider": "Carnegie Mellon University（Zico Kolter / Tianqi Chen）",
        "url": "https://dlsyscourse.org/",
        "description": "从零实现一个深度学习库 needle：autograd → CNN → Transformer → CUDA 后端。"
                       "对你（列存/系统背景）最对口的一门课。",
        "track": "ai-infra", "phase": "P2", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "课程官网", "url": "https://dlsyscourse.org/", "type": "官网"},
            {"name": "作业（HW0-HW4）", "url": "https://dlsyscourse.org/assignments/", "type": "作业"},
            {"name": "官方代码组织 github.com/dlsyscourse", "url": "https://github.com/dlsyscourse", "type": "代码"},
        ],
    },
    # ---------------- Phase 3 分布式与推理 ----------------
    {
        "title": "vLLM 文档与源码（PagedAttention）",
        "provider": "vLLM 社区",
        "url": "https://docs.vllm.ai/",
        "description": "PagedAttention 的官方实现。Phase 3 要求读源码并产出 block 管理流程图。",
        "track": "ai-infra", "phase": "P3", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "官方文档", "url": "https://docs.vllm.ai/", "type": "文档"},
        ],
    },
    {
        "title": "FlashAttention",
        "provider": "Dao-AILab（Tri Dao）",
        "url": "https://github.com/Dao-AILab/flash-attention",
        "description": "IO 感知的精确注意力，必读。配合论文看 CUDA kernel 的 tiling 与 online softmax。",
        "track": "ai-infra", "phase": "P3", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "GitHub 仓库", "url": "https://github.com/Dao-AILab/flash-attention", "type": "代码"},
        ],
    },
]


def main() -> int:
    # 读出已有课程，按 title 去重
    try:
        exist = {c["title"] for c in httpx.get(f"{BASE}/courses", timeout=15).json()["items"]}
    except Exception as e:
        print(f"读取已有课程失败：{e}")
        return 1

    added = 0
    for c in COURSES:
        if c["title"] in exist:
            print(f"  跳过（已存在）：{c['title'][:40]}")
            continue
        r = httpx.post(f"{BASE}/courses", json=c, timeout=15)
        if r.status_code < 300:
            added += 1
            print(f"  + 已导入：{c['title'][:44]}  [{c['phase']}]")
        else:
            print(f"  ! 失败：{c['title'][:40]} -> {r.status_code} {r.text[:100]}")

    total = httpx.get(f"{BASE}/courses", timeout=15).json()["total"]
    print(f"\n完成：新增 {added} 门，课程库共 {total} 门")
    return 0


if __name__ == "__main__":
    sys.exit(main())
