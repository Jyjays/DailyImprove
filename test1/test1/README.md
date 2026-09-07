# DailyImprove 学习台 · Study Desk

DailyImprove 的前端学习台：把每日抓取的论文与博客加工成可读的知识卡片，配上课程资料、每日打卡与面经练习。

后端由仓库根目录的 DailyImprove（FastAPI，默认 `127.0.0.1:8000`）提供，负责抓取、LLM 摘要、去重与落库；本目录只负责展示与交互。

## 四个页面

| 页面 | 内容 |
| --- | --- |
| **今日** | 从 `plan/daily/` 最新日报解析出「昨日承诺 / 昨日结果 / 今日三件事 / 打卡清单 / 明日预告」。打卡四档：`[x]` 已完成、`[!]` 部分完成、`[ ]` 未做、`[?]` 卡住；保存后写入数据库并回写日报 md |
| **知识** | 论文与博客卡片流。正文是 LLM 生成的中文摘要与判断理由，标签与评分，**原文链接附在最后**——先读加工过的内容，想深入再跳原文 |
| **课程** | 按主线（track）与阶段（phase）分组的课程资料：课程主页、介绍、课件 / 作业 / 代码 |
| **练习** | 面经自测：选题 → 提交 → 看解析 |

## 快速开始

前置：Node.js >= 18、Python >= 3.10。

**1. 启动后端**（仓库根目录）

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .          # Windows
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**2. 启动前端**（本目录）

```bash
npm install
npm run dev            # http://127.0.0.1:4173
```

Windows 下也可以双击本目录的 `启动学习平台.bat`；仓库根目录的 `启动学习台.bat` 会一次性拉起前后端并打开浏览器。

## 配置说明

- 前端通过 vite proxy 把 `/api` 转发到 `127.0.0.1:8000`，配置见 `vite.config.ts`
- **若系统设置了 `HTTP_PROXY`，启动前端前必须设 `NO_PROXY=127.0.0.1,localhost`**，否则 vite 的转发会走系统代理、被拒后返回 502
- **vite 优先读取 `vite.config.js`**（`tsc -b` 的产物）而非 `.ts`。改配置时两个文件要同步，或把 `.js` 加进 `.gitignore` 让它回退到 `.ts`
- 所有路径均使用相对路径，不依赖任何机器相关的绝对路径

## 数据落盘

| 数据 | 存放位置 |
| --- | --- |
| 打卡记录 | 后端 SQLite `checkins` 表，同时回写 `plan/daily/<日期>.md` |
| 知识条目 | 后端 SQLite `items` 表，摘要取 `llm_output` 中 LLM 生成的内容 |
| 课程资料 | 后端 SQLite `courses` 表（可用 `scripts/seed_courses.py` 导入） |
| 练习进度 | 浏览器 `localStorage`，键名 `dailyimprove-study-progress-v1` |

抓取失败时前端会明确标注，不会编造内容。

## 开发

```bash
npm run lint      # tsc -b 类型检查
npm run build     # 生产构建
```

目录结构：

```
src/App.tsx                 四个页面
src/lib/api.ts              后端接口封装
src/lib/pythonRunner.ts     Pyodide 浏览器端 Python 执行器（可选启用）
src/lib/sqlRunner.ts        DuckDB-Wasm 浏览器端 SQL 执行器（可选启用）
src/components/Markdown.tsx markdown 渲染（marked + GFM + 消毒）
src/data/interview.ts       面经题目种子数据
```
