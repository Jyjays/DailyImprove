"""SQLAlchemy ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index,
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
    历史接口尝试回写 plan/daily/YYYY-MM-DD.md；数据库为状态来源。
    新首页使用 LearningContext / LearningEntry，不再要求每日打卡。
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


class LearningContext(Base):
    """当前共享上下文。Markdown 是可重建快照，数据库是状态来源。"""

    __tablename__ = "learning_context"

    id = Column(Integer, primary_key=True)
    profile_json = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    export_pending = Column(Integer, nullable=False, default=1)
    export_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, nullable=False)


class LearningEntry(Base):
    """自愿记录的进展、问题和待采纳建议；一天可有多条。"""

    __tablename__ = "learning_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(64), nullable=False, unique=True)
    date = Column(String(10), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    author = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="recorded")
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class PracticeTopic(Base):
    __tablename__ = "practice_topics"
    key = Column(String(64), primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    material_title = Column(String(250), nullable=False)
    material_url = Column(Text, nullable=False)
    example = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="candidate")
    note = Column(Text, nullable=False, default="")


class PracticeQuestion(Base):
    __tablename__ = "practice_questions"
    id = Column(String(64), primary_key=True)
    canonical_key = Column(String(128), nullable=False, unique=True)
    title = Column(String(300), nullable=False)
    kind = Column(String(16), nullable=False)
    origin = Column(String(16), nullable=False)
    prompt = Column(Text, nullable=False)
    reference_notes = Column(Text, nullable=False, default="")
    followups_json = Column(Text, nullable=False, default="[]")
    topics_json = Column(Text, nullable=False, default="[]")
    roles_json = Column(Text, nullable=False, default="[]")
    document_path = Column(String(500), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class PracticeSource(Base):
    __tablename__ = "practice_sources"
    __table_args__ = (UniqueConstraint("question_id", "normalized_url", "source_type", name="uq_practice_source"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(String(64), ForeignKey("practice_questions.id"), nullable=False, index=True)
    source_type = Column(String(24), nullable=False)
    title = Column(String(300), nullable=False)
    url = Column(Text, nullable=False, default="")
    normalized_url = Column(Text, nullable=False, default="")
    published_on = Column(Date, nullable=True)
    captured_at = Column(DateTime, default=datetime.now, nullable=False)
    verification = Column(String(24), nullable=False, default="unverified")
    company = Column(String(120), nullable=False, default="")
    position = Column(String(250), nullable=False, default="")
    hiring_type = Column(String(32), nullable=False, default="")
    excerpt = Column(String(400), nullable=False, default="")
    note = Column(Text, nullable=False, default="")


class PracticeAttempt(Base):
    __tablename__ = "practice_attempts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(64), nullable=False, unique=True)
    question_id = Column(String(64), ForeignKey("practice_questions.id"), nullable=False, index=True)
    mode = Column(String(16), nullable=False)
    result = Column(String(16), nullable=False)
    answer = Column(Text, nullable=False, default="")
    note = Column(Text, nullable=False, default="")
    submission_url = Column(Text, nullable=False, default="")
    feedback_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class PracticeReview(Base):
    __tablename__ = "practice_reviews"
    question_id = Column(String(64), ForeignKey("practice_questions.id"), primary_key=True)
    due_on = Column(Date, nullable=False, index=True)
    step = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="scheduled")


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
