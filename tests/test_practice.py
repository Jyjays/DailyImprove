"""P1 练习流程的隔离集成测试，所有写入仅在临时目录。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import practice
from app.models.db import Base, get_session
from app.models.models import PracticeAttempt, PracticeQuestion, PracticeReview, PracticeSource, PracticeTopic
from app.practice import initialize_practice
from app.web import blog_api, context_api, practice_api


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dailyimprove-p1-")
        self.root = Path(self.tmp.name)
        self.blog = self.root / "blog"
        self.blog.mkdir()
        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.patches = [patch.object(context_api, "SNAPSHOT_PATH", self.root / "shared.md"), patch.object(blog_api, "BLOG_ROOT", self.blog)]
        for p in self.patches:
            p.start()
        app = FastAPI()
        app.include_router(practice_api.router)
        app.include_router(context_api.router)

        def dependency():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_session] = dependency
        self.client = TestClient(app)
        with self.sessions() as session:
            initialize_practice(session)
            context_api.initialize_context(session)

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def detail(self, key="lc-146"):
        response = self.client.get(f"/api/study/practice/questions/{key}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def attempt(self, key="lc-146", **extra):
        return self.client.post(f"/api/study/practice/questions/{key}/attempts", json={"result": "independent", **extra})

    def source(self, **extra):
        return {"source_type": "interview", "title": "原作者帖子", "url": "https://www.nowcoder.com/discuss/example", **extra}

    def create(self, **extra):
        return self.client.post("/api/study/practice/questions", json={"title": "测试开放问题", "prompt": "请说明关键取舍", "topics": ["storage"], "source": self.source(), **extra})

    def test_seed_has_topics_sources_and_is_idempotent_without_overwriting(self):
        topics = self.client.get("/api/study/practice/topics").json()["items"]
        self.assertEqual(len(topics), 9)
        questions = self.client.get("/api/study/practice/questions").json()
        self.assertEqual(questions["total"], 13)
        self.assertTrue(all(q["sources"] for q in questions["items"]))
        self.client.patch("/api/study/practice/questions/lc-146", json={"reference_notes": "自己的修订"})
        with self.sessions() as session:
            initialize_practice(session)
            self.assertEqual(session.query(PracticeQuestion).count(), 13)
            self.assertEqual(session.query(PracticeSource).count(), 13)
        self.assertEqual(self.detail()["reference_notes"], "自己的修订")

    def test_history_metadata_and_generated_questions_are_distinguishable(self):
        interview = self.detail("interview-cache")
        self.assertEqual(interview["origin"], "author")
        source = interview["sources"][0]
        self.assertEqual(source["published_on"], "2023-02-11")
        self.assertEqual((source["company"], source["hiring_type"]), ("百度", "实习"))
        self.assertIn("不代表近期高频", source["note"])
        self.assertEqual(self.detail("tcp-framing")["origin"], "generated")

    def test_manual_import_keeps_unverified_source_and_dedups_question(self):
        first = self.create(reference_notes="原先的参考")
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["created"])
        question_id = first.json()["question"]["id"]
        self.attempt(question_id)
        second = self.create(reference_notes="不覆盖旧内容", source=self.source(url="https://www.nowcoder.com/discuss/another"))
        self.assertFalse(second.json()["created"])
        detail = self.detail(question_id)
        self.assertEqual(len(detail["sources"]), 2)
        self.assertEqual(len(detail["attempts"]), 1)
        self.assertEqual(detail["reference_notes"], "原先的参考")
        self.assertTrue(all(s["verification"] == "unverified" for s in detail["sources"]))

    def test_leetcode_cn_com_dedup_by_problem_slug(self):
        r = self.create(title="同一道题的中文题名", kind="algorithm", source=self.source(source_type="algorithm", url="https://leetcode.cn/problems/lru-cache/?utm_source=x"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["created"])
        self.assertEqual(r.json()["question"]["id"], "lc-146")
        self.assertEqual(len(self.detail()["sources"]), 2)

    def test_external_sources_require_url_and_verification_is_explicit(self):
        self.assertEqual(self.create(source=self.source(url="")).status_code, 422)
        self.assertEqual(self.create(source=self.source(verification="checked")).status_code, 422)
        r = self.create()
        source = r.json()["question"]["sources"][0]
        response = self.client.patch(f"/api/study/practice/sources/{source['id']}", json={"verification": "user_confirmed"})
        self.assertEqual(response.json()["verification"], "user_confirmed")

    def test_source_duplicate_does_not_add_rows(self):
        row = self.create().json()["question"]
        for _ in range(2):
            self.assertEqual(self.client.post(f"/api/study/practice/questions/{row['id']}/sources", json=self.source()).status_code, 200)
        self.assertEqual(len(self.detail(row["id"])["sources"]), 1)

    def test_personal_and_generated_questions_can_exist_without_external_url(self):
        r = self.create(source=self.source(source_type="personal", url=""))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["question"]["origin"], "personal")
        self.assertEqual(self.create(title="自拟开放问题", source=self.source(source_type="generated", url="")).json()["question"]["origin"], "generated")

    def test_attempt_retries_are_idempotent_and_multiple_attempts_survive(self):
        self.assertEqual(self.attempt(client_id="same", note="一次记录").status_code, 200)
        self.assertEqual(self.attempt(client_id="same", note="一次记录").status_code, 200)
        self.assertEqual(self.attempt(client_id="same", note="不同内容").status_code, 409)
        self.assertEqual(self.attempt(client_id="other", result="hinted").status_code, 200)
        self.assertEqual(len(self.detail()["attempts"]), 2)

    def test_reading_never_increases_review_step(self):
        self.assertEqual(self.attempt(mode="read", result="independent").status_code, 422)
        self.assertEqual(self.attempt(mode="read", result="understood").status_code, 200)
        self.assertEqual(self.detail()["review"]["step"], 0)
        self.assertEqual(self.detail()["review"]["due_on"], (practice.today() + timedelta(days=1)).isoformat())

    def test_review_intervals_and_difficulty_reset(self):
        fixed = date(2026, 10, 24)
        with patch.object(practice_api, "today", return_value=fixed):
            for days in (1, 3, 7, 14):
                response = self.attempt(mode="written")
                self.assertEqual(response.json()["question"]["review"]["due_on"], (fixed + timedelta(days=days)).isoformat())
            self.attempt(result="again")
        self.assertEqual(self.detail()["review"]["step"], 0)

    def test_pause_not_auto_resumed_by_attempt_and_does_not_block_new_question(self):
        response = self.client.patch("/api/study/practice/reviews/lc-146", json={"action": "pause"})
        self.assertEqual(response.json()["status"], "paused")
        self.assertEqual(self.attempt().status_code, 200)
        self.assertEqual(self.detail()["review"]["status"], "paused")
        self.assertEqual(self.attempt("lc-206").status_code, 200)
        self.client.patch("/api/study/practice/reviews/lc-146", json={"action": "resume"})
        self.assertEqual(self.detail()["review"]["status"], "scheduled")

    def test_review_queue_is_small_and_postponable(self):
        with self.sessions() as session:
            for q in session.query(PracticeQuestion).limit(6):
                session.add(PracticeReview(question_id=q.id, due_on=practice.today()-timedelta(days=30), step=0, status="scheduled"))
            session.commit()
        queue = self.client.get("/api/study/practice/reviews").json()["items"]
        self.assertEqual(len(queue), 3)
        key = queue[0]["id"]
        r = self.client.patch(f"/api/study/practice/reviews/{key}", json={"action": "postpone", "days": 3})
        self.assertEqual(r.json()["due_on"], (practice.today()+timedelta(days=3)).isoformat())
        self.assertEqual(self.client.get("/api/study/practice/reviews?limit=100").status_code, 422)

    def test_paused_topic_excluded_from_queue_but_learning_unlocked(self):
        self.client.patch("/api/study/practice/reviews/tcp-framing", json={"action": "resume"})
        self.client.patch("/api/study/practice/topics/network", json={"status": "paused", "note": "之后再看"})
        self.assertNotIn("tcp-framing", [r["id"] for r in self.client.get("/api/study/practice/reviews").json()["items"]])
        self.assertEqual(self.attempt("tcp-framing").status_code, 200)

    def test_practice_and_topic_choices_in_shared_context_without_false_mastery(self):
        self.client.patch("/api/study/practice/topics/storage", json={"status": "focusing", "note": "压缩更新路径"})
        self.attempt(note="尚未讲清淘汰边界", result="again")
        overview = self.client.get("/api/study/practice/summary").json()
        self.assertEqual(overview["attempts_last_7_days"], 1)
        exported = self.client.get("/api/study/context/export").json()["markdown"]
        self.assertIn("尚未讲清淘汰边界", exported)
        self.assertIn("压缩更新路径", exported)
        self.assertIn("自评 again", exported)

    def test_project_questions_use_selected_document_and_dedup(self):
        (self.blog / "项目.md").write_text("---\ntitle: 列存整理\n---\n# 压缩\n这里是尚待核验的说明", encoding="utf-8")
        payload = {"document_path": "项目.md", "topics": ["storage"]}
        for _ in range(2):
            r = self.client.post("/api/study/practice/project-questions", json=payload)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.json()["items"]), 3)
            self.assertTrue(all(q["origin"] == "generated" and q["document_path"] == "项目.md" for q in r.json()["items"]))
        with self.sessions() as session:
            self.assertEqual(session.query(PracticeQuestion).filter_by(kind="project").count(), 3)
        self.assertNotEqual(self.client.post("/api/study/practice/project-questions", json={"document_path": "../outside.md"}).status_code, 200)

    def test_feedback_unavailable_does_not_lose_attempt(self):
        attempt = self.attempt(answer="我的回答").json()["attempt"]
        with patch.object(practice_api, "LLMClient") as client:
            client.return_value.available = False
            r = self.client.post(f"/api/study/practice/attempts/{attempt['id']}/feedback")
        self.assertFalse(r.json()["available"])
        self.assertEqual(self.detail()["attempts"][0]["answer"], "我的回答")

    def test_feedback_is_qualitative_persisted_and_does_not_change_self_assessment(self):
        attempt = self.attempt(answer="我的回答", result="hinted").json()["attempt"]
        review_before = self.detail()["review"]
        with patch.object(practice_api, "LLMClient") as client:
            client.return_value.available = True
            client.return_value.chat_json.return_value = {"covered": ["有结构"], "missing": ["边界"], "followups": ["复杂度？"], "caveat": "仅作参考", "score": 100}
            r = self.client.post(f"/api/study/practice/attempts/{attempt['id']}/feedback")
        self.assertTrue(r.json()["available"])
        self.assertNotIn("score", r.json()["feedback"])
        self.assertEqual(self.detail()["review"], review_before)
        self.assertEqual(self.detail()["attempts"][0]["feedback"]["missing"], ["边界"])

    def test_preview_failure_keeps_manual_import_available_and_blocks_internal_targets(self):
        with patch.object(practice, "_fetchable", side_effect=ValueError("unsupported")):
            response = self.client.post("/api/study/practice/sources/preview", json={"url": "https://example.com/a"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["readable"])
        self.assertEqual(self.create().status_code, 200)
        for url in ["http://127.0.0.1:8000", "http://localhost/a", "file:///secret", "https://user:secret@example.com/"]:
            self.assertEqual(self.client.post("/api/study/practice/sources/preview", json={"url": url}).status_code, 422)

    def test_preview_returns_short_candidate_not_verified_question(self):
        raw = "<html><title>公开材料</title><main>" + ("用于验证的公开正文。" * 60) + "</main></html>"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.is_redirect = False
        response.headers = {"content-type": "text/html"}
        response.encoding = "utf-8"
        response.iter_bytes.return_value = [raw.encode()]
        with patch.object(practice, "_fetchable", side_effect=lambda u: u), patch.object(practice.httpx, "Client") as client, patch("trafilatura.extract", return_value="可读公开正文。" * 80):
            client.return_value.__enter__.return_value.stream.return_value = response
            result = practice.preview_source("https://man7.org/example")
        self.assertTrue(result["readable"])
        self.assertLessEqual(len(result["excerpt"]), 350)
        self.assertEqual(result["verification"], "unverified")

    def test_search_never_falls_back_to_llm_credentials(self):
        from app.config import settings
        from app.plugins.sources.search_source import SearchSourcePlugin
        source = SimpleNamespace(config={}, url="数据库面经", name="面经搜索")
        with patch.dict(os.environ, {}, clear=True), patch.object(settings, "llm_api_key", "private-test-key"), patch("app.plugins.sources.search_source.httpx.post") as post:
            with self.assertRaises(ValueError):
                SearchSourcePlugin().fetch(source)
            post.assert_not_called()

    def test_invalid_topics_missing_question_and_invalid_result(self):
        self.assertEqual(self.create(topics=["missing"]).status_code, 422)
        self.assertEqual(self.attempt(result="mastered").status_code, 422)
        self.assertEqual(self.attempt("missing").status_code, 404)
        self.assertEqual(self.client.get("/api/study/practice/questions?kind=unsupported").status_code, 422)


if __name__ == "__main__":
    unittest.main()
