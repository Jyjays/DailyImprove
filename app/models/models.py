"""SQLAlchemy ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.models.db import Base


class Module(Base):
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    enabled = Column(Integer, nullable=False, default=1)
    schedule = Column(String(64), nullable=False, default="0 8 * * *")
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    lifetime = Column(String(16), nullable=False, default="persistent")
    max_items = Column(Integer, nullable=False, default=5)
    config_yaml = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    sources = relationship("Source", back_populates="module", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="module", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(String(32), nullable=False, default="rss")
    url = Column(Text, nullable=False)
    config_json = Column(Text, nullable=True)
    base_weight = Column(Float, nullable=False, default=1.0)
    rating_avg = Column(Float, nullable=False, default=0.5)
    rating_count = Column(Integer, nullable=False, default=0)
    is_paused = Column(Integer, nullable=False, default=0)
    last_fetch_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    module = relationship("Module", back_populates="sources")
    items = relationship("Item", back_populates="source")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_module_unique", "module_id", "unique_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    unique_key = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=True)
    title = Column(String(512), nullable=False)
    url = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    raw_content = Column(Text, nullable=True)
    lifetime = Column(String(16), nullable=False, default="persistent")
    status = Column(String(32), nullable=False, default="new")
    llm_score = Column(Float, nullable=True)
    final_score = Column(Float, nullable=True)
    llm_output = Column(Text, nullable=True)
    merged_sources = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.now, nullable=False)

    module = relationship("Module", back_populates="items")
    source = relationship("Source", back_populates="items")


class PushRecord(Base):
    __tablename__ = "push_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="success")
    external_id = Column(String(255), nullable=True)
    pushed_at = Column(DateTime, default=datetime.now, nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    feedback_type = Column(String(32), nullable=False)
    rating = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class RunRecord(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=datetime.now, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, default="running")
    fetched_count = Column(Integer, default=0)
    after_dedup_count = Column(Integer, default=0)
    after_filter_count = Column(Integer, default=0)
    selected_count = Column(Integer, default=0)
    pushed_count = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)


class CheckIn(Base):
    """每日打卡记录。

    状态四档（与 AGENTS.md 7.3 节一致）：
      done    [x] 已完成
      todo    [ ] 未做
      partial [!] 部分完成且跨天延续
      blocked [?] 卡住，需写清卡点
    打卡会同时回写 plan/daily/YYYY-MM-DD.md，保证 md 仍是单一事实来源。
    """
    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("date", "category", name="uq_checkin_date_category"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)          # YYYY-MM-DD
    category = Column(String(32), nullable=False)                   # ai-infra/paper/interview/drone/blocker
    title = Column(String(255), nullable=False)                     # 打卡项标题
    status = Column(String(16), nullable=False, default="todo")
    note = Column(Text, nullable=True)                              # 特殊说明 / 卡点
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class Favorite(Base):
    """知识条目收藏。

    单独建表而不是在 items 上打标记，原因：
      - 收藏不受"近 N 天"时间窗影响，需要能独立查
      - 抓取产物被 reset_items.py 清空时，收藏随之级联删除，不留悬空记录
    """
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("item_id", name="uq_favorite_item"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class Course(Base):
    """课程与学习资料。track 对应三条主线，phase 对应 roadmap 阶段。"""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    provider = Column(String(128), nullable=True)                   # CMU / UIUC / NVIDIA ...
    url = Column(String(1024), nullable=True)                       # 课程主页
    description = Column(Text, nullable=True)                       # 课程介绍
    track = Column(String(32), nullable=False, default="ai-infra")  # ai-infra/paper/drone
    phase = Column(String(16), nullable=True)                       # P0~P4
    resources = Column(Text, nullable=True)                         # JSON: [{name,url,type}]
    status = Column(String(16), nullable=False, default="未开始")     # 未开始/进行中/已完成
    progress = Column(Integer, nullable=False, default=0)           # 0-100
    created_at = Column(DateTime, default=datetime.now, nullable=False)
