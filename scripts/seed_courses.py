"""把 roadmap 里的课程导入 courses 表。

用法：
    python scripts/seed_courses.py            # 只新增缺失的课程（默认，安全）
    python scripts/seed_courses.py --sync     # 同时对齐已有课程的 phase / 描述 / 资源

--sync 只覆盖课程元信息（provider / url / description / track / phase / resources），
**不动 status 与 progress** —— 进度是用户数据，不能被导入脚本冲掉。

链接可信度：绝大多数已核实（2026-09-07/08）。标注「待核实」的条目需回官方渠道确认，
写进简历或对外引用前请再核一遍。resources 里标"待补"= 没有把握的公开链接，不编造。
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

BASE = "http://127.0.0.1:8000/api/study"

COURSES = [
    # ---------------- Phase 0 基础回填 + Linux 存储栈（主线 A）----------------
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
    {
        "title": "《Linux/UNIX 系统编程手册》（TLPI）· 主线 A",
        "provider": "Michael Kerrisk",
        "url": "https://man7.org/tlpi/",
        "description": "主线 A 的基本功。精读 Ch13 文件 IO、Ch49 内存映射、Ch14 文件系统。"
                       "目标是能画出 VFS → Page Cache → 文件系统 → Block Layer → 设备的完整路径。",
        "track": "ai-infra", "phase": "P0", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "官方主页（含示例代码下载）", "url": "https://man7.org/tlpi/", "type": "官网"},
        ],
    },
    {
        "title": "fio + io_uring 官方文档 · 主线 A",
        "provider": "Jens Axboe / Linux 社区",
        "url": "https://fio.readthedocs.io/",
        "description": "E17/E18 的直接依据。fio 出 IOPS / 带宽 / p99 三个数字；"
                       "io_uring 搞清提交完成队列为什么能做到接近零系统调用。",
        "track": "ai-infra", "phase": "P0", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "fio 文档", "url": "https://fio.readthedocs.io/", "type": "文档"},
            {"name": "fio 仓库（含 examples 与 HOWTO）", "url": "https://github.com/axboe/fio", "type": "代码"},
            {"name": "io_uring(7) 手册页", "url": "https://man7.org/linux/man-pages/man7/io_uring.7.html", "type": "文档"},
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
    # ---------------- Phase 2 训推框架源码（主线 B）----------------
    {
        "title": "Megatron-LM 源码 · 主线 B",
        "provider": "NVIDIA",
        "url": "https://github.com/NVIDIA/Megatron-LM",
        "description": "v2 要求从「读论文」升级为「读源码 + 改一处」。重点：TP 在哪个模块切分、"
                       "通信点在哪一行；跑通 2 卡 TP（只有 1 卡时走降级方案，不要谎称跑过多卡）。",
        "track": "ai-infra", "phase": "P2", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "GitHub 仓库", "url": "https://github.com/NVIDIA/Megatron-LM", "type": "代码"},
        ],
    },
    {
        "title": "SGLang（RadixAttention）· 主线 B",
        "provider": "SGLang 社区",
        "url": "https://github.com/sgl-project/sglang",
        "description": "与 vLLM 的 PagedAttention 对照读：基数树 vs 页表，两种 KV Cache 复用思路的差别。",
        "track": "ai-infra", "phase": "P2", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "GitHub 仓库", "url": "https://github.com/sgl-project/sglang", "type": "代码"},
        ],
    },
    {
        "title": "vLLM 文档与源码（PagedAttention）",
        "provider": "vLLM 社区",
        "url": "https://docs.vllm.ai/",
        "description": "PagedAttention 的官方实现。要求读源码并产出 block 管理流程图（E15），"
                       "另做一份含 MFU 与显存的 benchmark（E16）。",
        "track": "ai-infra", "phase": "P2", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "官方文档", "url": "https://docs.vllm.ai/", "type": "文档"},
            {"name": "GitHub 仓库", "url": "https://github.com/vllm-project/vllm", "type": "代码"},
        ],
    },
    # ---------------- Phase 3 存储交叉项目（主线 A）----------------
    {
        "title": "LMCache（KV Cache 卸载与复用）· 主线 A",
        "provider": "LMCache 社区",
        "url": "https://github.com/LMCache/LMCache",
        "description": "E21 的直接对象：把 KV Cache 卸载到 CPU 内存与磁盘并跨请求复用。"
                       "测 TTFT / 吞吐随「冷启动率」的变化，找分层边界拐点。",
        "track": "ai-infra", "phase": "P3", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "GitHub 仓库", "url": "https://github.com/LMCache/LMCache", "type": "代码"},
        ],
    },
    {
        "title": "Mooncake（KV Cache 分离式推理）· 主线 A",
        "provider": "Moonshot AI / 清华 MADSys（**出处待核实**）",
        "url": "",
        "description": "以 KV Cache 为中心的分离式架构，用闲置 CPU/DRAM/SSD 资源池存 KV Cache。"
                       "⚠️ 出处与仓库地址待核实，引用前回官方渠道确认。",
        "track": "ai-infra", "phase": "P3", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "仓库地址待核实（暂不填，避免假链接）", "url": "", "type": "待核实"},
        ],
    },
    {
        "title": "3FS（Fire-Flyer File System）· 主线 A",
        "provider": "DeepSeek（**出处待核实**）",
        "url": "https://github.com/deepseek-ai/3FS",
        "description": "面向 AI 训练的高性能分布式文件系统。⚠️ 出处待核实，引用前回官方渠道确认。",
        "track": "ai-infra", "phase": "P3", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "GitHub 仓库（待核实）", "url": "https://github.com/deepseek-ai/3FS", "type": "代码"},
        ],
    },
    # ---------------- Phase 1 GPU 编程（FlashAttention 归到这里）----------------
    {
        "title": "FlashAttention",
        "provider": "Dao-AILab（Tri Dao）",
        "url": "https://github.com/Dao-AILab/flash-attention",
        "description": "IO 感知的精确注意力，必读。v2 的要求是能从 **IO 角度** 解释它为什么快"
                       "（而不是算力角度）—— 这条直接连回主线 A，是面试加分回答。",
        "track": "ai-infra", "phase": "P1", "status": "未开始", "progress": 0,
        "resources": [
            {"name": "GitHub 仓库", "url": "https://github.com/Dao-AILab/flash-attention", "type": "代码"},
        ],
    },
]


# --sync 时会被覆盖的字段；status / progress 永远不动（那是用户的学习进度）
SYNC_FIELDS = ("provider", "url", "description", "track", "phase", "resources")


def main() -> int:
    ap = argparse.ArgumentParser(description="把 roadmap 里的课程导入 courses 表")
    ap.add_argument(
        "--sync", action="store_true",
        help="对齐已有课程的元信息（phase / 描述 / 资源），不动 status 与 progress",
    )
    args = ap.parse_args()

    try:
        exist_map = {c["title"]: c for c in httpx.get(f"{BASE}/courses", timeout=15).json()["items"]}
    except Exception as e:
        print(f"读取已有课程失败：{e}\n（需要先启动后端：uvicorn app.main:app --host 127.0.0.1 --port 8000）")
        return 1

    added = synced = 0

    for c in COURSES:
        old = exist_map.get(c["title"])

        if old is None:
            r = httpx.post(f"{BASE}/courses", json=c, timeout=15)
            if r.status_code < 300:
                added += 1
                print(f"  + 已导入：{c['title'][:44]}  [{c['phase']}]")
            else:
                print(f"  ! 失败：{c['title'][:40]} -> {r.status_code} {r.text[:100]}")
            continue

        # 已存在：默认跳过；--sync 时只对齐元信息
        diffs = [f for f in SYNC_FIELDS if old.get(f) != c.get(f)]
        if not diffs:
            print(f"  · 无变化：{c['title'][:40]}")
            continue
        if not args.sync:
            print(f"  · 已存在但有差异（{', '.join(diffs)}），加 --sync 可对齐：{c['title'][:32]}")
            continue

        body = dict(old)
        body.update({f: c[f] for f in SYNC_FIELDS})
        r = httpx.put(f"{BASE}/courses/{old['id']}", json=body, timeout=15)
        if r.status_code < 300:
            synced += 1
            print(f"  ~ 已对齐（{', '.join(diffs)}）：{c['title'][:36]}")
        else:
            print(f"  ! 同步失败：{c['title'][:36]} -> {r.status_code} {r.text[:100]}")

    total = httpx.get(f"{BASE}/courses", timeout=15).json()["total"]
    print(f"\n完成：新增 {added} 门，对齐 {synced} 门，课程库共 {total} 门")
    return 0


if __name__ == "__main__":
    sys.exit(main())
