# DailyImprove 架构方案

> 版本：v0.1（实现依据）
> 定位：每日成长系统 —— 按用户兴趣拆分为信息模块，按模块从可靠来源检索信息，用基础大模型做一轮筛选（不依赖 Agent 自主决策），整合为微信公众号 / 飞书文档推送；用户反馈来源质量，高分多推、低分少推；内容去重与分层持久化。

---

## 1. 设计目标与原则

### 1.1 目标

| 编号 | 目标 | 验收标准 |
|---|---|---|
| G1 | 每日定时运行 | 按模块 cron 触发，失败可重试，运行日志可查 |
| G2 | 模块化插件化 | 新增一个信息主题只需新增 YAML 配置，不改核心代码；新来源类型/推送渠道可插拔 |
| G3 | 多源可靠检索 | 每个模块可挂多个来源；来源信息在推送中显式标注 |
| G4 | LLM 单轮筛选 | 基础模型完成相关度评分、摘要、理由，单轮调用，无 Agent 循环 |
| G5 | 微信/飞书推送 | 支持微信公众号草稿/发布、飞书文档 + 多维表格归档 |
| G6 | 来源反馈闭环 | 本地 Web UI 对来源/条目评分，评分影响后续来源权重与选材 |
| G7 | 去重持久化 | 非时效性内容已推不再推；时效性内容按 TTL 自动清理，不保证永久去重 |
| G8 | 本地化部署 | Docker Compose 一键启动，数据保存在本地卷，无强制云依赖 |

### 1.2 设计原则

1. **配置优先于代码**：模块 = 目录里的一个 YAML 文件，核心流程零代码扩展。
2. **确定性优先，LLM 作为过滤器而非决策者**：抓取、去重、排期、推送由确定性规则完成；LLM 只做“相关度打分 + 摘要 + 理由”，单轮调用，结构体输出。
3. **管道化（Pipeline）**：抓取 → 标准化 → 去重 → 过滤 → 评分 → 选材 → 组装 → 推送，每段可替换。
4. **插件接口极窄**：`Source`、`Channel`、`Filter` 三类插件接口，每个插件实现 1~3 个方法。
5. **评分有贝叶斯平滑**：来源评分避免小样本误判；用户反馈影响来源权重，而不是直接封杀。
6. **本地优先**：SQLite 起步，数据文件本地可备份；外部依赖仅 RSS/API、LLM API 和微信/飞书 API。

---

## 2. 总体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         本地 Web 控制台 (FastAPI)                     │
│   模块管理 │ 来源管理 │ 今日 Digest │ 历史 │ 反馈评分 │ 运行日志          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ 读写配置/评分/反馈
┌───────────────────────────────▼─────────────────────────────────────┐
│                       SQLite 持久化层 (SQLAlchemy)                    │
│  modules │ sources │ items │ push_records │ feedback │ runs │ settings │
└───────────────────────────────▲─────────────────────────────────────┘
                                │ 写入
┌───────────────────────────────┴─────────────────────────────────────┐
│                        定时调度器 (APScheduler)                       │
│                 每个模块一条 cron 任务，可暂停/恢复/手动触发              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ 触发 module.run()
┌───────────────────────────────▼─────────────────────────────────────┐
│                        模块编排器 ModuleRunner                        │
│                                                                      │
│  1 加载模块配置     → config loader                                   │
│  2 抓取           → SourcePlugin.fetch(module) → RawItem[]           │
│  3 标准化         → Normalizer → Item（含 source_id、来源名、URL、hash） │
│  4 去重           → DedupStore（持久型永久去重 / 时效型 TTL 去重）      │
│  5 确定性过滤     → KeywordFilter / TimeWindowFilter / LengthFilter    │
│  6 LLM 单轮筛选   → LLMFilter.batch() → {relevant, score, summary, ...}│
│  7 排序打分       → Ranker（来源权重 × LLM 分 × 新鲜度 × 用户兴趣）     │
│  8 选材           → TopNSelector（N 条 + 来源多样性 + 跨源去重）        │
│  9 组装           → Composer → 微信/飞书/通用 Digest 文档结构            │
│ 10 推送           → ChannelPlugin.push(digest) → PushRecord            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────────┐
        ▼                       ▼                           ▼
  SourcePlugin             FilterPlugin                ChannelPlugin
  ┌────────────┐       ┌────────────────┐       ┌────────────────────┐
  │ RSSPlugin  │       │ KeywordFilter  │       │ WechatChannel      │
  │ APIPlugin  │       │ LLMFilter      │       │ FeishuDocChannel   │
  │ WebPlugin  │       │ (可替换)       │       │ FileChannel        │
  │ SearchPlg  │       └────────────────┘       │ TelegramChannel    │
  └────────────┘                                └────────────────────┘
```

### 2.2 核心概念

| 概念 | 说明 | 实现形式 |
|---|---|---|
| **Module（模块）** | 一个信息主题，如“前端面经”“AI 技术博客” | `modules/*.yaml` + `modules` 表 |
| **Source（来源）** | 模块下具体信息源，有 URL、类型、权重、评分 | YAML + `sources` 表 |
| **Item（条目）** | 一条标准化信息 | `items` 表 |
| **Plugin（插件）** | 代码级扩展点：来源/过滤器/推送渠道 | `plugins/` 下 Python 类 |
| **Digest（日报）** | 一次模块运行选出的内容集合，用于推送 | 内存对象 + `push_records` |
| **Feedback（反馈）** | 用户对来源或条目的显式/隐式评价 | `feedback` 表 |
| **Lifetime（时效性）** | `persistent` 永久去重 / `ephemeral` TTL 去重 | `items.lifetime` |

---

## 3. 目录结构

```
DailyImprove/
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md
├── ARCHITECTURE.md
├── modules/                      # ★ 零代码扩展点：一个主题一个 YAML
│   ├── frontend-interview.yaml
│   ├── ai-blog.yaml
│   └── example-template.yaml
├── app/
│   ├── main.py                   # FastAPI 入口 + 启动调度器
│   ├── config.py                 # 环境变量、全局配置
│   ├── scheduler.py              # APScheduler 封装
│   ├── orchestrator.py           # ModuleRunner 编排器
│   ├── pipeline/
│   │   ├── normalizer.py         # 标准化
│   │   ├── dedup.py              # 去重
│   │   ├── filters.py            # 确定性过滤
│   │   ├── llm_filter.py         # LLM 单轮过滤
│   │   ├── ranker.py             # 打分排序
│   │   ├── selector.py           # TopN 与多样性
│   │   └── composer.py           # 组装 Digest
│   ├── plugins/
│   │   ├── base.py               # 插件接口定义
│   │   ├── sources/
│   │   │   ├── rss_source.py
│   │   │   ├── api_source.py
│   │   │   ├── web_source.py
│   │   │   └── search_source.py
│   │   ├── filters/
│   │   │   ├── keyword_filter.py
│   │   │   └── llm_filter.py
│   │   └── channels/
│   │       ├── wechat_channel.py
│   │       ├── feishu_channel.py
│   │       ├── file_channel.py
│   │       └── telegram_channel.py
│   ├── models/
│   │   ├── db.py                 # SQLAlchemy engine/session
│   │   └── models.py             # ORM 模型
│   ├── web/
│   │   ├── api.py                # REST API
│   │   └── ui.py                 # Jinja2 页面
│   └── utils/
│       ├── hashing.py            # URL 归一化 + 内容哈希
│       ├── llm_client.py         # OpenAI 兼容客户端（含 Ollama）
│       └── logger.py
├── data/                         # 本地数据（SQLite、日志）
├── tests/
└── scripts/
    └── init_db.py
```

---

## 4. 插件接口设计

### 4.1 SourcePlugin

```python
# app/plugins/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class RawItem:
    title: str
    url: str
    author: str | None = None
    content: str | None = None
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class SourceConfig:
    id: int
    name: str
    type: str
    url: str
    module_config: dict
    weight: float = 1.0
    rating_multiplier: float = 1.0

class SourcePlugin(ABC):
    """来源插件：只负责抓取原始条目，不做业务判断。"""
    plugin_type = "source"
    name = "base_source"

    @abstractmethod
    def fetch(self, source: SourceConfig) -> list[RawItem]:
        """抓取一个来源，返回原始条目列表。"""

    def validate(self, source: SourceConfig) -> bool:
        """校验配置是否可用。默认 True。"""
        return True
```

内置来源插件：

| 插件名 | 类型 | 说明 |
|---|---|---|
| `rss_source` | rss | 抓取 RSS/Atom（feedparser） |
| `api_source` | api | 调用 JSON API，用 jq-like 表达式提取条目 |
| `web_source` | web | 抓取网页列表，按 CSS/正则提取条目（轻量抓取） |
| `search_source` | search | 调用搜索 API（如 Tavily/Bing/本地 SearXNG） |

> 扩展方式：在 `plugins/sources/` 新增一个实现 `SourcePlugin` 的 `.py`，在模块 YAML 中写 `source.type: my_source` 即可，由注册表自动发现。

### 4.2 FilterPlugin

```python
class FilterPlugin(ABC):
    plugin_type = "filter"
    name = "base_filter"

    @abstractmethod
    def filter(self, items: list[Item], module: ModuleConfig) -> list[Item]:
        """返回过滤后的条目（或给条目打标记）。"""
```

内置过滤插件：
- `keyword_filter`：标题/正文包含/排除关键词（确定性，无成本）。
- `time_window_filter`：只保留最近 N 小时/天。
- `llm_filter`：单轮 LLM 筛选（见第 6 节）。

### 4.3 ChannelPlugin

```python
class ChannelPlugin(ABC):
    plugin_type = "channel"
    name = "base_channel"

    @abstractmethod
    def push(self, digest: Digest, channel_config: dict) -> PushResult:
        """把 Digest 推送到目标渠道，返回外部 ID。"""
```

内置渠道插件：
- `wechat`：微信公众号草稿箱/发布。
- `feishu_doc`：创建飞书文档，并可选归档到多维表格。
- `file`：输出本地 Markdown（开发调试用，也用于兼容其他平台）。
- `telegram`：Telegram 机器人（可选，便于自测）。

> 渠道插件同样通过 `plugins/channels/*.py` 自动发现，模块 YAML 中 `push.channels: [wechat, feishu_doc]` 启用。

---

## 5. 模块配置规范（零代码新增模块）

### 5.1 示例：新增“前端面经”模块

文件：`modules/frontend-interview.yaml`

```yaml
key: frontend-interview          # 唯一键
name: 前端面经
enabled: true
schedule: "0 8 * * *"            # 每天 08:00，cron 格式
timezone: Asia/Shanghai
lifetime: persistent             # 面经非时效性 → 永久去重
dedup:
  strategy: persistent
  key_fields: [url]              # 去重依据
  cross_source: title_similarity # 跨源去重：标题相似度 > 0.85 视为同一内容
max_items_per_run: 5             # 每期最多推送条数
llm:
  model: deepseek-chat           # 任意 OpenAI 兼容模型
  temperature: 0.1
  batch_size: 10
  max_tokens: 2000
  profile: |
    用户是 3-5 年经验前端工程师，正在准备大厂面试。
    关注：JS/TS 基础、React/Vue、Node.js、工程化、算法、真实面经。
    不要：培训广告、低质量搬运、与面试无关的行业新闻。
  output_schema: |
    {"relevant": bool, "score": 0-100, "summary": "<=80字", "reason": "<=30字", "tags": ["..."]}
filter:
  keywords_include: ["面经", "面试", "面试题", "前端", "React", "Vue", "TypeScript"]
  keywords_exclude: ["培训", "广告", "限时优惠"]
  min_content_length: 100
  lookback_hours: 168             # 只取最近 7 天
sources:
  - name: 前端面试题专栏
    type: rss
    url: https://example.com/rss/interview
    base_weight: 1.0
  - name: 某技术博客-前端标签
    type: api
    url: https://api.example.com/posts?tag=frontend
    base_weight: 0.9
    config:
      method: GET
      headers: {}
      items_path: "data.items"
      title_field: "title"
      url_field: "url"
      time_field: "published_at"
push:
  channels:
    - wechat
    - feishu_doc
  wechat:
    target: draft                # draft：草稿箱；publish：发布（需认证服务号）
    account: default
  feishu_doc:
    folder_token: "..."          # 飞书目录，可选
    archive_to_bitable: true
```

### 5.2 示例：新增“AI 行业快讯”模块（时效性内容）

```yaml
key: ai-news
name: AI 行业快讯
schedule: "0 9 * * *"
lifetime: ephemeral              # ★ 时效性 → TTL 去重
dedup:
  strategy: ttl
  ttl_days: 3                    # 3 天内同一 URL 不重复推，3 天后自动清理
  key_fields: [url]
max_items_per_run: 8
llm:
  model: qwen-turbo
  profile: |
    关注 AI 大模型、开源模型、AI 产品与重要论文。
    优先：模型发布、重大技术突破、融资与产品。
    不要：纯营销稿件、重复报道。
filter:
  keywords_include: ["大模型", "LLM", "GPT", "Claude", "Gemini", "开源模型"]
  lookback_hours: 48
sources:
  - name: Hacker News AI 版
    type: rss
    url: https://hnrss.org/newest?q=AI
  - name: 机器之心 RSS
    type: rss
    url: https://www.jiqizhixin.com/rss
push:
  channels: [feishu_doc]
```

> 新增模块 = 复制模板 YAML 并放到 `modules/` 目录。系统启动/热加载时扫描该目录，自动建表记录并注册调度任务。**不改任何核心代码。**

---

## 6. LLM 筛选流水线（单轮、不依赖 Agent）

### 6.1 设计约束

1. **单轮调用**：一次 LLM 调用输入一批候选条目 + 模块偏好，输出结构化 JSON 数组。
2. **不做多步决策**：LLM 不调用工具、不自主规划、不循环重试；失败即回退。
3. **可回退**：LLM 不可用时退化为“确定性关键词 + 来源权重”选材，系统照常推送。
4. **低成本**：先用确定性过滤把候选条目压到 20~50 条，再批量送 LLM。

### 6.2 调用流程

```
候选条目 (去重/确定性过滤后 20~50 条)
        │
        ▼
构造 Prompt：
  - 模块偏好 profile
  - 来源权重提示（来源 A 评分高，来源 B 评分低，但不是硬过滤）
  - 条目列表：[id, source, title, summary/description, url, published_at]
        │
        ▼
调用 OpenAI 兼容 Chat Completions，response_format=json_object
        │
        ▼
解析得到：id, relevant, score(0-100), summary, reason, tags
        │
        ▼
relevant=false 或 score<模块阈值的条目标记 filtered_out
        │
        ▼
进入 Ranker 排序
```

### 6.3 Prompt 模板要点

```text
你是信息筛选助手。用户兴趣档案：
{{ module.llm.profile }}

来源可靠度提示（仅供参考，不是硬过滤）：
{{ source_hints }}   # 例如：来源 A 用户评分 4.6/5，权重 1.2

下面有 {{ n }} 条候选信息，请逐条判断：
- relevant：是否与用户兴趣相关（bool）
- score：相关度 0-100，越相关越高
- summary：中文一句话摘要（<=80字）
- reason：筛选理由（<=30字）
- tags：2-4 个标签

只输出 JSON：
{"items": [{"id": "...", "relevant": true, "score": 75, "summary": "...", "reason": "...", "tags": ["..."]}]}
```

### 6.4 模型选择与本地化

| 场景 | 建议模型 | 说明 |
|---|---|---|
| 隐私优先/免费 | Ollama + Qwen2.5-7B / Llama3.1-8B | 本地推理，JSON 输出需约束 |
| 性价比 | DeepSeek / Moonshot / Qwen-Turbo | 中文效果好、便宜 |
| 质量优先 | GPT-4o-mini / Claude Haiku | 结构化输出稳定 |

> LLM 客户端统一用 OpenAI 兼容接口，通过环境变量 `LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL` 切换。

---

## 7. 来源评分与反馈闭环

### 7.1 反馈类型

| 反馈动作 | 类型 | 影响 |
|---|---|---|
| 来源星级 1-5 | 显式 | 更新来源评分（影响后续来源权重） |
| 条目“有用” | 显式 | 小幅提升来源评分 |
| 条目“无用/垃圾” | 显式 | 降低来源评分 |
| 收藏 | 显式强正 | 较强提升来源评分与类目偏好 |
| 忽略/不感兴趣 | 显式负 | 降低来源评分 |
| 已读/推送后点击 | 隐式 | 轻微正反馈（如做可选项） |

### 7.2 来源评分算法（参考 CondenseIt）

对每个来源维护：
- `n`：评分次数
- `rating_avg`：平均分（1~5 归一化到 0~1）
- `global_avg`：全库来源平均分

**贝叶斯平滑**（避免“1 个 5 星就永远第一”）：

```
smoothed_rating = (C * global_avg + n * rating_avg) / (C + n)
# C 建议取 10：来源至少 10 次评分后，真实评分才主导
```

**来源权重乘数**：

```
rating_multiplier = 0.3 + 1.2 * smoothed_rating   # 评分 0 → 0.3 倍，评分 1 → 1.5 倍
final_source_weight = base_weight * rating_multiplier
```

**降级策略**：
- `smoothed_rating < 0.25` 且 `n >= 5`：降低抓取频率（如每天 → 每周两次）。
- `smoothed_rating < 0.15` 且 `n >= 10`：暂停来源，控制台提示用户确认。

### 7.3 条目最终排序

```
final_score =
    0.45 * llm_relevance       # LLM score 归一化 0~1
  + 0.20 * source_weight_norm  # 来源权重归一化
  + 0.15 * freshness_score     # e^-(age_hours / half_life)，半衰期默认 48h
  + 0.10 * interest_score      # 用户兴趣标签/类目匹配（可由反馈学习）
  + 0.10 * diversity_bonus     # 与已选条目来源/标签差异越大分越高
```

### 7.4 选材规则

- 每模块每期最多 `max_items_per_run` 条。
- 同一来源每期最多 2 条（保证多样性）。
- 来源评分低的条目不是完全不推，而是排序时被压低；若 LLM 给分特别高，仍可入选。
- 跨源去重：同一内容（标题相似度 > 0.85 或内容哈希一致）只保留来源权重最高的一条。

---

## 8. 去重与分层持久化

### 8.1 两层策略

| 内容类型 | 典型场景 | 去重策略 | 持久化策略 |
|---|---|---|---|
| `persistent` | 面经、博客、教程、面试题 | **永久唯一去重**：URL 归一化后哈希，或 `来源+标题` 哈希，已推过不再推 | 长期保留 |
| `ephemeral` | 新闻、快讯、价格、热点 | **TTL 去重**：在 `ttl_days` 内同 URL 不重复推，过期自动清理 | 可删除，不占长期存储 |

### 8.2 去重键生成

```python
def normalize_url(url: str) -> str:
    # 去 utm_* 参数、去 hash、统一协议、去尾斜杠
    ...

def item_unique_key(module_key: str, url: str, title: str, lifetime: str) -> str:
    if url:
        base = f"{module_key}:{normalize_url(url)}"
    else:
        base = f"{module_key}:{title.strip().lower()}"
    return hashlib.sha1(base.encode()).hexdigest()
```

### 8.3 状态机

```
new → filtered_out          （确定性过滤或 LLM 判定不相关）
new → selected → pushed     （入选并推送成功）
new → selected → push_failed（推送失败，可重试）
pushed（persistent）→ 永久不再进入候选
pushed（ephemeral）→ ttl 过期后物理删除，不参与长期去重
```

### 8.4 数据库约束

```sql
-- 持久型：同一模块内唯一键永久唯一
CREATE UNIQUE INDEX ux_items_persistent_dedup
  ON items(module_id, unique_key) WHERE lifetime = 'persistent';

-- 时效型：唯一键 + 创建日期，保证 TTL 窗口内不重复；窗口外允许重新进入
CREATE UNIQUE INDEX ux_items_ephemeral_dedup
  ON items(module_id, unique_key, date(fetched_at))
  WHERE lifetime = 'ephemeral';
```

> SQLite 支持部分唯一索引（partial unique index），以上写法有效。PostgreSQL 写法相同。

### 8.5 清理任务

- 每日凌晨运行 `purge_ephemeral_items()`：删除 `lifetime='ephemeral'` 且 `fetched_at < now() - ttl_days` 的条目。
- 清理 `push_records` 中对应时效型记录。
- 持久型条目不清理。

---

## 9. 数据模型

### 9.1 ER 关系

```
modules 1 ──── n sources 1 ──── n items n ──── n push_records
  │                                     │
  │                                     │
  │                                     n feedback
  │
  n runs（每次模块运行的审计记录）
```

### 9.2 建表 SQL（SQLite）

```sql
CREATE TABLE modules (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  key           TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  enabled       INTEGER NOT NULL DEFAULT 1,
  schedule      TEXT NOT NULL DEFAULT '0 8 * * *',
  timezone      TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  lifetime      TEXT NOT NULL DEFAULT 'persistent',   -- persistent | ephemeral
  max_items     INTEGER NOT NULL DEFAULT 5,
  config_yaml   TEXT,                                  -- 原始 YAML 全文备份
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sources (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id     INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  type          TEXT NOT NULL,                         -- rss | api | web | search
  url           TEXT NOT NULL,
  config_json   TEXT,
  base_weight   REAL NOT NULL DEFAULT 1.0,
  rating_avg    REAL NOT NULL DEFAULT 0.5,             -- 归一化 0~1
  rating_count  INTEGER NOT NULL DEFAULT 0,
  is_paused     INTEGER NOT NULL DEFAULT 0,
  last_fetch_at TIMESTAMP,
  last_error    TEXT,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE items (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id     INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  source_id     INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  unique_key    TEXT NOT NULL,
  content_hash  TEXT,
  title         TEXT NOT NULL,
  url           TEXT,
  author        TEXT,
  summary       TEXT,
  raw_content   TEXT,
  lifetime      TEXT NOT NULL DEFAULT 'persistent',    -- persistent | ephemeral
  status        TEXT NOT NULL DEFAULT 'new',           -- new|filtered_out|selected|pushed|push_failed
  llm_score     REAL,
  final_score   REAL,
  llm_output    TEXT,                                  -- JSON 字符串
  published_at  TIMESTAMP,
  fetched_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE push_records (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id       INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  module_id     INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  channel       TEXT NOT NULL,                         -- wechat | feishu_doc | file ...
  status        TEXT NOT NULL DEFAULT 'success',       -- success | failed
  external_id   TEXT,                                  -- 微信 media_id / 飞书 doc_token
  pushed_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feedback (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id     INTEGER REFERENCES modules(id) ON DELETE CASCADE,
  source_id     INTEGER REFERENCES sources(id) ON DELETE CASCADE,
  item_id       INTEGER REFERENCES items(id) ON DELETE SET NULL,
  feedback_type TEXT NOT NULL,                         -- source_rating|item_useful|item_useless|save|ignore
  rating        INTEGER,                               -- 1~5（source_rating 时使用）
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id     INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   TIMESTAMP,
  status        TEXT NOT NULL DEFAULT 'running',       -- running|success|failed|partial
  fetched_count INTEGER DEFAULT 0,
  after_dedup_count INTEGER DEFAULT 0,
  after_filter_count INTEGER DEFAULT 0,
  selected_count INTEGER DEFAULT 0,
  pushed_count  INTEGER DEFAULT 0,
  error_msg     TEXT
);
```

---

## 10. 执行流程（一次完整运行）

```
scheduler 触发模块 module.key
        │
        ▼
ModuleRunner.run(module_key)
        │
        ├─ 1. 校验模块 enabled，记录 runs 开始
        ├─ 2. 读取 sources（跳过 is_paused，权重参与后续排序）
        ├─ 3. 对每个 source 调用 SourcePlugin.fetch(source)
        │        ├─ 成功：更新 last_fetch_at
        │        └─ 失败：失败计数 +1；连续失败 ≥3 的 source 本次跳过，下期自动重试
        ├─ 4. Normalizer：统一为 Item，打上 source_id、来源名、lifetime
        ├─ 5. Dedup：
        │        ├─ persistent：查 items 唯一键，已存在则丢弃
        │        └─ ephemeral：查 TTL 窗口内唯一键，已存在则丢弃
        ├─ 6. 确定性过滤：关键词、时间窗、长度
        ├─ 7. LLM 单轮筛选（批量），输出 relevant/score/summary/tags
        ├─ 8. Ranker 计算 final_score
        ├─ 9. TopNSelector：按最终分排序 + 多样性规则选出 N 条
        ├─ 10. Composer：生成 Digest（标题、板块、条目、来源标注）
        ├─ 11. ChannelPlugin 逐个推送：
        │        ├─ wechat → 公众号草稿/发布
        │        └─ feishu_doc → 创建飞书文档（可选归档 Bitable）
        ├─ 12. 写 items.status / push_records / runs 结束状态
        └─ 13. 发送运行摘要（可选：日志/Telegram 通知）
```

### 10.1 失败处理

- 单个来源失败不影响其他来源。
- 单个渠道失败不影响其他渠道（`push_records.status=failed` 可重试）。
- 整次运行失败：`runs.status=failed`，记录错误，下个周期正常重跑；持久型去重保证不重复推。

---

## 11. 推送层设计

### 11.1 微信公众号

| 模式 | 说明 | 适用 |
|---|---|---|
| `draft` | 调用 `draft/add` 新建草稿，人工确认后群发 | 个人订阅号、内容审核 |
| `publish` | 调用 `freepublish/submit` 直接发布 | 认证服务号 |
| 推送内容 | 多图文消息：封面图 + 标题 + 摘要 + 正文 HTML | 每期 1 条主图文 + N 条次图文 |

关键点：
- 使用微信 access_token（本地缓存，过期自动刷新）。
- 正文由 Markdown 转 HTML 后内联样式（微信兼容）。
- 每条消息显式标注来源：`来源：xxx（用户评分 4.5/5）`。
- 草稿箱模式最适合本地部署：系统只负责每天自动生成草稿，最终是否发布由人工一键确认。

### 11.2 飞书文档

两种形态：

1. **飞书云文档（docx）**：适合长文日报，使用 `docx/v1/documents` + `children` 接口分块写入标题、段落、链接、分割线。
2. **飞书消息卡片**：适合轻推送，通过自定义机器人 webhook 或 `im/v1/messages` 发送。

推荐组合：
- 每期日报创建一个飞书云文档；
- 归档一条记录到飞书多维表格（Bitable）：`标题 | 模块 | 来源 | 链接 | 评分 | 日期`；
- 通过飞书消息卡片把文档链接推给用户/群。

关键点：
- 使用 `tenant_access_token`，本地缓存，过期自动刷新。
- 文档接口需要 App 权限：`docx:document`、`bitable:app`。
- 本地部署时 App Secret 放在 `.env`。

### 11.3 开发调试渠道

- `file`：输出 Markdown 到 `data/digest/<module>-<date>.md`，方便不依赖外部平台跑通全链路。
- `telegram`：可选，便于自测推送效果。

---

## 12. 本地化部署与 Web 控制台

### 12.1 部署形态

```bash
git clone <repo>
cp .env.example .env          # 填 LLM_API_KEY / 微信 / 飞书凭据
docker compose up -d
# Web 控制台: http://127.0.0.1:8000
```

- 数据卷：`./data:/app/data`（SQLite、日志、Digest 文件）。
- 默认只监听 `127.0.0.1`，公网部署需自行加反向代理和鉴权。
- 可选 `OLLAMA_HOST` 指向本地 Ollama，完全离线运行 LLM。

### 12.2 Web 控制台页面

| 页面 | 功能 |
|---|---|
| `GET /` | 今日概览：各模块状态、推送结果 |
| `GET /modules` | 模块列表、启停、编辑 YAML、手动运行 |
| `GET /modules/new` | 上传/粘贴 YAML，热加载新模块 |
| `GET /sources` | 来源列表、评分曲线、暂停/恢复 |
| `GET /digest` | 每期 Digest 预览与历史 |
| `GET /feedback` | 待反馈条目：来源星级、有用/无用、收藏/忽略 |
| `GET /runs` | 运行日志 |

### 12.3 反馈 API

```
POST /api/feedback
{
  "source_id": 12,
  "feedback_type": "source_rating",  // source_rating | item_useful | item_useless | save | ignore
  "rating": 5,
  "item_id": null
}
```

收到反馈后：
1. 写 `feedback` 表；
2. 重算该来源 `rating_avg`、`rating_count`；
3. 更新 `sources.rating_avg`（贝叶斯平滑后的值可实时算，也可定期物化）；
4. 后续运行中 Ranker 自动使用新权重。

---

## 13. 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | 生态成熟，feedparser/httpx/SQLAlchemy 齐全 |
| Web | FastAPI + Jinja2 | 轻量，REST + 服务端渲染 |
| 调度 | APScheduler | cron 触发、暂停/恢复、时区支持 |
| 存储 | SQLite + SQLAlchemy | 起步；数据量大后可换 PostgreSQL |
| LLM | OpenAI 兼容客户端 | 支持 DeepSeek/Moonshot/Qwen/OpenAI/Ollama |
| 抓取 | feedparser、httpx、BeautifulSoup、lxml | RSS/API/Web |
| 推送 | 微信官方 API、飞书开放平台 API | 见第 11 节 |
| 部署 | Docker Compose | 本地优先，一键启动 |
| 测试 | pytest | 管道各阶段单测 + 一个模块的端到端 fixture |

---

## 14. 实施里程碑

### M1：可运行骨架（1-2 天）
- [ ] 项目初始化、目录结构、SQLite 模型
- [ ] 模块 YAML 加载与校验
- [ ] RSS SourcePlugin + 标准化 + 持久型去重 + FileChannel
- [ ] APScheduler 每日触发 + runs 记录
- 验收：配一个 RSS 模块，能每天生成 Markdown Digest，重复 URL 不重复出现。

### M2：LLM 筛选与排序（2-3 天）
- [ ] OpenAI 兼容 LLM 客户端
- [ ] 单轮 LLM 过滤 + 回退策略
- [ ] Ranker（来源权重 + LLM 分 + 新鲜度）
- [ ] 跨源标题去重
- 验收：LLM 不可用时不崩，退化为关键词选材。

### M3：反馈闭环（2 天）
- [ ] FastAPI Web 控制台 + 反馈 API
- [ ] 来源评分（贝叶斯平滑）与权重计算
- [ ] 来源评分影响排序与抓取频率
- 验收：对某来源打 1 星后，该来源条目明显减少；打 5 星后增加。

### M4：微信 + 飞书推送（2-3 天）
- [ ] 微信草稿箱 Channel
- [ ] 飞书云文档 Channel + Bitable 归档
- [ ] 推送失败重试与状态记录
- 验收：每日自动生成微信草稿 + 飞书文档，来源标注完整。

### M5：插件体系与工程化（2-3 天）
- [ ] 插件自动发现与热加载
- [ ] 模块 YAML 新增/启停/手动触发
- [ ] ephemeral TTL 去重 + 清理任务
- [ ] Docker Compose 部署 + 文档
- 验收：新增模块只需放一个 YAML 文件，不重启核心进程即可生效。

---

## 15. 与现有开源项目的借鉴关系

| 借鉴点 | 来源项目 |
|---|---|
| Source/Sink/LLM/Search 四层插件化、YAML 配方 | jaypetez/glean |
| 星级/收藏/忽略等反馈信号、来源权重学习 | wildlifechorus/condenseit |
| 三层去重（URL→标题→摘要）、微信发布 | Alionkissadeer/ai-daily-news |
| 一个主题一个 YAML、飞书文档 + Bitable 归档 | noiseorigin/daily-digest |
| 多平台热点 + AI 筛选 + 多通道推送的产品形态 | sansan0/TrendRadar |
| LLM 过滤/重写/评估的流水线 | fabriziosalmi/UglyFeed |

---

## 16. 风险与决策记录

| 风险 | 应对 |
|---|---|
| LLM 成本随模块/来源数上升 | 确定性过滤先压到 20~50 条；用便宜模型；每模块每期上限 |
| 微信公众号 API 权限限制 | 默认草稿箱模式；认证服务号才自动发布 |
| 飞书文档 API 限流 | 分块写入 + 重试退避；缓存 token |
| 来源评分小样本偏差 | 贝叶斯平滑，C=10 |
| 插件热加载不稳定 | 新增模块只热加载 YAML；新增代码插件需重启（保证稳定性） |
| 抓取来源失效 | 来源失败计数，连续失败自动降频并在控制台提示 |

---

## 17. 立即可开始的第一步

1. 创建项目骨架（目录、pyproject、SQLite 模型）。
2. 实现 `rss_source.py` + `file_channel.py` + 一个 `modules/example.yaml`。
3. 跑通“定时抓取 → 去重 → 生成 Markdown”闭环。
4. 再逐步加入 LLM 筛选、评分反馈、微信/飞书推送。

> 本方案是系统实现依据。任何模块实现前，请先回到本文件确认接口与数据模型，保持一致性。
