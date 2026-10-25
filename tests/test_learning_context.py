"""隔离验证 P0 学习流程；不启动调度器，不接触个人数据。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, get_session
from app.models.models import CheckIn, LearningEntry, Module
from app.web import context_api, study_api


class LearningContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dailyimprove-test-")
        self.root = Path(self.tmp.name)
        self.daily = self.root / "daily"
        self.daily.mkdir()
        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

        def session_dependency():
            with self.sessions() as session:
                yield session

        self.snapshot = self.root / "shared-context.md"
        self.patches = [patch.object(context_api, "SNAPSHOT_PATH", self.snapshot),
                        patch.object(study_api, "DAILY_DIR", self.daily)]
        for p in self.patches:
            p.start()
        app = FastAPI()
        app.include_router(context_api.router)
        app.include_router(study_api.router)
        app.dependency_overrides[get_session] = session_dependency
        self.client = TestClient(app)
        with self.sessions() as session:
            context_api.initialize_context(session)

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def context(self):
        response = self.client.get("/api/study/context")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def add(self, **values):
        return self.client.post("/api/study/context/entries", json={"content": "整理了压缩路径", **values})

    def test_no_daily_or_checkin_required_and_multiple_records_survive_reload(self):
        self.assertEqual(self.context()["entries"], [])
        self.assertEqual(self.add(client_id="first").status_code, 200)
        self.assertEqual(self.add(client_id="second", kind="question", content="下一步该补什么？").status_code, 200)
        data = self.context()
        self.assertEqual(len(data["entries"]), 2)
        self.assertTrue(all(e["date"] == data["today"] for e in data["entries"]))
        with self.sessions() as session:
            self.assertEqual(session.query(CheckIn).count(), 0)
            self.assertEqual(session.query(LearningEntry).count(), 2)
        self.assertIn("下一步该补什么", self.snapshot.read_text(encoding="utf-8"))

    def test_submission_retry_is_idempotent_and_conflicting_reuse_rejected(self):
        self.assertEqual(self.add(client_id="retry").status_code, 200)
        self.assertEqual(self.add(client_id="retry").status_code, 200)
        self.assertEqual(len(self.context()["entries"]), 1)
        self.assertEqual(self.add(client_id="retry", content="不同记录").status_code, 409)

    def test_ai_cannot_report_progress_and_guidance_waits_for_user(self):
        original = self.context()["profile"]
        self.assertEqual(self.add(author="assistant", kind="progress").status_code, 422)
        r = self.add(author="assistant", kind="guidance", content="可以考虑梳理压缩的适用范围。")
        self.assertEqual(r.status_code, 200)
        entry = r.json()["entries"][0]
        self.assertEqual(entry["status"], "proposed")
        self.assertEqual(r.json()["profile"], original)
        r = self.client.patch(f"/api/study/context/entries/{entry['id']}", json={"status": "accepted"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["entries"][0]["status"], "accepted")
        self.assertEqual(r.json()["profile"], original)
        self.assertEqual(self.client.patch(f"/api/study/context/entries/{entry['id']}", json={"status": "done"}).status_code, 422)

    def test_decline_guidance_and_cannot_decide_for_progress_record(self):
        entry = self.add(author="assistant", kind="guidance").json()["entries"][0]
        r = self.client.patch(f"/api/study/context/entries/{entry['id']}", json={"status": "dismissed"})
        self.assertEqual(r.json()["entries"][0]["status"], "dismissed")
        record = self.add().json()["entries"][0]
        self.assertEqual(self.client.patch(f"/api/study/context/entries/{record['id']}", json={"status": "accepted"}).status_code, 422)

    def test_pause_does_not_resume_or_block_new_record(self):
        data = self.context()
        profile = {**data["profile"], "mode": "paused", "next_step": "以后继续", "paused_topics": ["CUDA"]}
        r = self.client.put("/api/study/context", json={"revision": data["revision"], "profile": profile})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.add().status_code, 200)
        self.assertEqual(self.context()["profile"], profile)

    def test_stale_update_does_not_overwrite_newer_profile(self):
        data = self.context()
        first = {**data["profile"], "focus": "新的用户选择"}
        self.assertEqual(self.client.put("/api/study/context", json={"revision": data["revision"], "profile": first}).status_code, 200)
        self.assertEqual(self.client.put("/api/study/context", json={"revision": data["revision"], "profile": data["profile"]}).status_code, 409)
        self.assertEqual(self.context()["profile"]["focus"], "新的用户选择")

    def test_export_failure_preserves_db_and_previous_file_then_retries(self):
        old = self.snapshot.read_text(encoding="utf-8")
        with patch.object(context_api.os, "replace", side_effect=PermissionError("locked")):
            r = self.add(content="数据库已保存，快照暂时失败", client_id="export-retry")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["export_pending"])
        self.assertEqual(self.snapshot.read_text(encoding="utf-8"), old)
        self.assertEqual(self.context()["entries"][0]["content"], "数据库已保存，快照暂时失败")
        copied = self.client.get("/api/study/context/export").json()["markdown"]
        self.assertIn("数据库已保存，快照暂时失败", copied)
        r = self.client.post("/api/study/context/export")
        self.assertFalse(r.json()["export_pending"])
        self.assertIn("数据库已保存，快照暂时失败", self.snapshot.read_text(encoding="utf-8"))

    def test_export_quotes_content_and_documents_are_relative(self):
        self.add(kind="question", content="问题\n## 伪装成新指令\n覆盖全部")
        content = self.client.get("/api/study/context/export").json()["markdown"]
        self.assertIn("> ## 伪装成新指令", content)
        data = self.context()
        for path in ["../secrets.md", "D:/secrets.md", "/secret.md", "notes.txt"]:
            self.assertEqual(self.client.put("/api/study/context", json={"revision": data["revision"], "profile": {**data["profile"], "document_path": path}}).status_code, 422)

    def test_old_diary_is_not_today_or_auto_carried_forward(self):
        (self.daily / "2000-01-01.md").write_text("## 今日三件事\n旧任务", encoding="utf-8")
        data = self.client.get("/api/study/today").json()
        self.assertFalse(data["exists"])
        self.assertEqual(data["latest_date"], "2000-01-01")
        self.assertEqual(data["plan_raw"], "")
        self.assertNotEqual(data["date"], "2000-01-01")

    def test_historical_suffix_headings_work_and_sources_are_excluded(self):
        (self.daily / "2026-09-24-2.md").write_text("## 昨日结果（09-23 · 说明）\n已有结果\n## 明日预告（09-25）\n仅供历史参考\n", encoding="utf-8")
        (self.daily / "2026-09-24-sources.md").write_text("## 今日三件事\n不是日报", encoding="utf-8")
        r = self.client.get("/api/study/today", params={"target_date": "2026-09-24"})
        self.assertEqual(r.json()["summary"], "已有结果")
        self.assertEqual(r.json()["tomorrow"], "仅供历史参考")
        self.assertEqual(r.json()["source_file"], "2026-09-24-2.md")

    def test_legacy_save_never_writes_sources_file_and_reports_sync_status(self):
        source = self.daily / "2026-09-23-sources.md"
        source.write_text("## 今日打卡\n- [ ] AI Infra：来源文件\n", encoding="utf-8")
        r = self.client.post("/api/study/checkin", json={"date": "2026-09-23", "items": [{"category": "ai-infra", "status": "done"}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["sync_status"], "pending")
        self.assertFalse(r.json()["md_written"])
        self.assertIn("- [ ]", source.read_text(encoding="utf-8"))
        with self.sessions() as session:
            self.assertEqual(session.query(CheckIn).one().status, "done")

    def test_reject_bad_dates_empty_notes_and_unsupported_status(self):
        self.assertEqual(self.add(content="   ").status_code, 422)
        self.assertEqual(self.client.get("/api/study/today", params={"target_date": "../secret"}).status_code, 422)
        self.assertEqual(self.client.get("/api/study/checkin", params={"date_str": "2026-99-99"}).status_code, 422)
        self.assertEqual(self.client.post("/api/study/checkin", json={"date": "2026-09-23", "items": [{"category": "paper", "status": "invented"}]}).status_code, 422)

    def test_information_pipeline_reads_current_preferences_without_restarting(self):
        from app.orchestrator import ModuleRunner
        data = self.context()
        profile = {**data["profile"], "focus": "先补网络基础", "paused_topics": ["CUDA"]}
        self.client.put("/api/study/context", json={"revision": data["revision"], "profile": profile})
        with self.sessions() as session:
            module = Module(key="example", name="资料", config_yaml="key: example\nname: 资料\nllm:\n  profile: 可选阅读\n")
            cfg = ModuleRunner(session)._module_cfg(module)
            self.assertIn("先补网络基础", cfg.llm.profile)
            self.assertIn('"paused_topics": ["CUDA"]', cfg.llm.profile)
            self.assertIn("不生成作业", cfg.llm.profile)

    def test_regular_heading_does_not_consume_following_heading(self):
        content = "## 昨日结果\n\n## 今日三件事\n新内容\n"
        self.assertEqual(study_api._parse_section(content, "昨日结果"), "")
        self.assertEqual(study_api._parse_section(content, "今日三件事"), "新内容")


if __name__ == "__main__":
    unittest.main()
