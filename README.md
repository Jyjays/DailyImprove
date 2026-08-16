# DailyImprove

每日成长系统：按用户兴趣拆分为信息模块，按模块从可靠来源检索信息，用基础大模型做一轮筛选（不依赖 Agent 自主决策），整合为微信公众号 / 飞书文档推送。支持本地化部署与用户反馈闭环。

## 特性

- **模块化零代码扩展**：新增一个信息主题 = 在 `modules/` 目录新增一个 YAML 文件
- **插件化**：来源插件（rss/api/web/search）、推送渠道插件（wechat/feishu_doc/file/telegram）可替换可扩展
- **LLM 单轮筛选**：OpenAI 兼容接口，一次调用完成相关度评分、摘要、理由；LLM 不可用时自动回退关键词规则
- **来源反馈闭环**：本地 Web 控制台对来源评分，高分多推、低分少推（贝叶斯平滑）
- **去重分层持久化**：`persistent` 内容永久去重，`ephemeral` 内容 TTL 去重后自动清理
- **本地化部署**：Docker Compose 一键启动，数据保存在本地 `data/` 目录

## 架构

完整设计见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

```
本地 Web 控制台（FastAPI）
        ↓
SQLite（modules / sources / items / push_records / feedback / runs）
        ↑
APScheduler 定时调度
        ↓
ModuleRunner 编排器
  → SourcePlugin.fetch() → 标准化 → 去重 → 确定性过滤
  → LLM 单轮筛选 → 排序打分 → TopN 选材 → 组装 → ChannelPlugin.push()
```

## 快速开始

### 方式一：本地运行（推荐）

```bash
./start.sh
```

`start.sh` 会自动检查依赖；如果本地 `.deps/` 缺少依赖，会自动安装。不配置任何 API Key 也能运行，系统会回退到关键词筛选，并把抓取结果写入 SQLite 和 `data/digest/`。

也可以使用标准 Python 虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env          # 按需填写 LLM/微信/飞书凭据
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 查看控制台。

### 方式二：Docker

```bash
cp .env.example .env
docker compose up -d
```

### 手动运行一次模块

```bash
.venv/bin/python -c "from app.orchestrator import run_module; run_module('tech-blog')"
```

## 新增一个信息模块

复制 `modules/tech-blog.yaml` 为 `modules/my-topic.yaml`，修改 `key`、`name`、`sources`、`llm.profile` 等内容后重启服务即可（或调用模块同步接口）。

示例：前端面经模块

```yaml
key: frontend-interview
name: 前端面经
enabled: true
schedule: "0 8 * * *"
timezone: Asia/Shanghai
lifetime: persistent          # 面经非时效性，永久去重
max_items_per_run: 5
llm:
  model: deepseek-chat
  threshold: 60
  profile: |
    用户是 3-5 年前端工程师，正在准备大厂面试。
    关注 JS/TS、React/Vue、Node.js、工程化、算法、真实面经。
    不要培训广告和低质量搬运。
filter:
  keywords_include: ["面经", "面试题", "前端", "React", "Vue"]
  keywords_exclude: ["培训", "广告"]
  lookback_hours: 168
sources:
  - name: 某前端面试专栏
    type: rss
    url: https://example.com/rss/interview
    base_weight: 1.0
push:
  channels: [wechat, feishu_doc]
```

## 模块配置字段

| 字段 | 说明 | 默认 |
|---|---|---|
| key | 模块唯一键 | 必填 |
| name | 模块显示名 | key |
| enabled | 是否启用 | true |
| schedule | cron 表达式 | `0 8 * * *` |
| timezone | 时区 | Asia/Shanghai |
| lifetime | `persistent` 永久去重 / `ephemeral` TTL 去重 | persistent |
| max_items_per_run | 每期最多推送条数 | 5 |
| dedup.strategy | persistent / ttl | persistent |
| dedup.ttl_days | ephemeral 去重窗口天数 | 3 |
| dedup.cross_source | `title_similarity` 跨源标题去重 | 空 |
| llm.model | 模型名；留空则使用全局 LLM_MODEL | 空 |
| llm.threshold | LLM 相关度入选阈值 0-100 | 60 |
| llm.profile | 用户兴趣档案，写入筛选 Prompt | 空 |
| filter.keywords_include | 关键词白名单 | [] |
| filter.keywords_exclude | 关键词黑名单 | [] |
| filter.lookback_hours | 只取最近 N 小时内容 | 168 |
| sources | 来源列表 | 必填 |
| source.type | rss / api / web / search | rss |
| source.base_weight | 来源基础权重 | 1.0 |
| push.channels | wechat / feishu_doc / file / telegram | [file] |

## 来源评分与反馈

- 打开 http://127.0.0.1:8000/sources
- 点击星星为来源评分（1-5 星）
- 系统用贝叶斯平滑计算来源生效评分，并影响后续排序：
  `final_score = 0.45*LLM分 + 0.20*来源权重 + 0.15*新鲜度 + 0.10*兴趣 + 0.10*多样性`

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/status | 系统状态 |
| GET | /api/modules | 模块列表 |
| POST | /api/modules/{key}/run | 手动运行模块 |
| PUT | /api/modules/{module_id} | 启停模块 |
| GET | /api/sources | 来源列表 |
| GET | /api/items | 条目列表 |
| GET | /api/runs | 运行记录 |
| POST | /api/feedback | 提交反馈 |
| GET | /docs | Swagger 文档 |

## 项目结构

```
app/
  main.py            # FastAPI 入口
  orchestrator.py    # 模块运行编排器
  scheduler.py       # APScheduler 调度
  module_loader.py   # YAML 模块同步
  feedback.py        # 反馈与来源评分
  pipeline/          # 标准化/去重/过滤/LLM/排序/选材/组装
  plugins/
    sources/         # rss / api / web / search
    channels/        # wechat / feishu_doc / file / telegram
  models/            # SQLAlchemy ORM
  web/               # Web 控制台
modules/             # ★ 信息模块 YAML（零代码扩展）
data/                # SQLite 与输出
```

## 配置项

见 [.env.example](./.env.example)。常用：

| 环境变量 | 说明 |
|---|---|
| LLM_API_BASE | OpenAI 兼容 API 地址，如 `https://api.deepseek.com/v1` |
| LLM_API_KEY | API Key |
| LLM_MODEL | 模型名，如 `deepseek-chat` |
| WECHAT_APP_ID / WECHAT_APP_SECRET | 微信公众号凭据（可在微信开发者平台/公众平台获取） |
| WECHAT_THUMB_MEDIA_ID | 封面缩略图 media_id，用 `scripts/get_wechat_thumb.py` 上传获得 |
| FEISHU_APP_ID / FEISHU_APP_SECRET | 飞书开放平台凭据 |
| TAVILY_API_KEY | 搜索型来源（可选） |

## 测试

```bash
.venv/bin/pytest
```

## 路线图

- [x] M1 骨架 + RSS + 去重 + FileChannel + 调度
- [x] M2 LLM 单轮筛选与排序
- [x] M3 Web 控制台 + 来源反馈
- [x] M4 微信公众号 + 飞书文档渠道
- [x] M5 插件化 + TTL 清理 + 容器化
- [ ] 内容相似度聚类跨源合并（当前为标题相似度去重）
- [ ] 更多来源插件（微信公众号、掘金、Reddit、GitHub Releases）
- [ ] 用户兴趣标签学习（当前仅来源评分）
