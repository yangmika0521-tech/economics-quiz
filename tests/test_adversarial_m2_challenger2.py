"""Adversarial stress-test suite for Milestone 2 (Challenger 2).

Empirically tests:
1. Session Lifecycle & Concurrency (50 concurrent sessions, UUID isolation, deduplication).
2. Anti-Cheating Invariant (omission of correct_answer and explanation_zh).
3. Scoring Extremes (100% perfect, 0% zero score, partial/unanswered submissions).
4. Robustness & Error Injection (unknown/malformed session IDs, empty answers, unrecognized IDs, clamping, validation).
"""

import math
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List

import pytest
from fastapi.testclient import TestClient

from app.main import app, quiz_sessions, questions_cache


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Shared TestClient instance for live API testing."""
    return TestClient(app)


# ==============================================================================
# 1. Session Lifecycle & Concurrency Stress Testing
# ==============================================================================

class TestConcurrencyAndSessionLifecycle:
    """Stress-tests concurrent session creation, UUID uniqueness, and session isolation."""

    def test_50_concurrent_quiz_sessions_isolation_and_uniqueness(self, client: TestClient):
        """Creates 50 concurrent quiz sessions across varied modes, chapter selections, and counts.

        Verifies:
        - All 50 return HTTP 200.
        - All 50 session_ids are valid UUIDs and mutually unique.
        - All sessions are isolated in the in-memory session store.
        - Each session contains zero internal question ID duplicates.
        - Random sampling produces diverse sets across sessions.
        """
        all_chapters = ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"]
        chapter_presets = [
            ["Ch_01"],
            ["Ch_01", "Ch_02"],
            ["Ch_03", "Ch_04"],
            ["Ch_05", "Ch_06"],
            ["Ch_02", "Ch_04", "Ch_06"],
            all_chapters,
        ]

        def create_session(index: int) -> Dict[str, Any]:
            mode = "exam" if index % 2 == 0 else "practice"
            selected_chapters = chapter_presets[index % len(chapter_presets)]
            count = 5 + (index % 5) * 5  # 5, 10, 15, 20, 25

            payload = {
                "chapter_ids": selected_chapters,
                "question_count": count,
                "mode": mode,
            }
            resp = client.post("/api/quiz/new", json=payload)
            return {
                "index": index,
                "status_code": resp.status_code,
                "payload": resp.json(),
                "requested_count": count,
                "requested_mode": mode,
                "requested_chapters": selected_chapters,
            }

        # Launch 50 concurrent requests with 10 worker threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(create_session, range(50)))

        # 1. Status code assertion
        assert all(r["status_code"] == 200 for r in results), (
            f"Not all concurrent sessions succeeded: {[r['status_code'] for r in results if r['status_code'] != 200]}"
        )

        # 2. Session ID uniqueness and UUID format
        session_ids = [r["payload"]["session_id"] for r in results]
        assert len(session_ids) == 50
        assert len(set(session_ids)) == 50, "Duplicate session IDs detected across concurrent creations!"

        for sid in session_ids:
            # Validates standard UUID structure
            parsed = uuid.UUID(sid)
            assert str(parsed) == sid

        # 3. Session isolation in server-side storage
        for r in results:
            sid = r["payload"]["session_id"]
            assert sid in quiz_sessions, f"Session {sid} not found in backend quiz_sessions dictionary"
            server_data = quiz_sessions[sid]
            assert server_data["mode"] == r["requested_mode"]
            assert len(server_data["questions"]) == len(r["payload"]["questions"])

        # 4. Intra-session deduplication
        for r in results:
            q_ids = [q["id"] for q in r["payload"]["questions"]]
            assert len(q_ids) == len(set(q_ids)), (
                f"Session {r['payload']['session_id']} contains duplicate questions!"
            )
            assert len(q_ids) == r["payload"]["total_questions"]

            # Verify questions belong only to requested chapters
            allowed_ch = set(r["requested_chapters"])
            for q in r["payload"]["questions"]:
                assert q["chapter_id"] in allowed_ch, (
                    f"Question {q['id']} chapter {q['chapter_id']} not in requested {allowed_ch}"
                )

        # 5. Question diversity check across identical configs
        # Filter sessions that used all_chapters and count=25
        large_sessions = [
            r for r in results
            if r["requested_chapters"] == all_chapters and r["requested_count"] == 25
        ]
        if len(large_sessions) >= 2:
            s1_ids = set(q["id"] for q in large_sessions[0]["payload"]["questions"])
            s2_ids = set(q["id"] for q in large_sessions[1]["payload"]["questions"])
            assert s1_ids != s2_ids, "Random sampling produced identical question sets for large pool!"


# ==============================================================================
# 2. Anti-Cheating Invariant
# ==============================================================================

class TestAntiCheatingInvariant:
    """Verifies that client question payloads NEVER expose answers or explanations."""

    def test_anti_cheating_omission_across_50_sessions(self, client: TestClient):
        """Audits every single question in 50 newly created sessions for answer leakage."""
        for i in range(50):
            resp = client.post("/api/quiz/new", json={
                "chapter_ids": ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"],
                "question_count": 10,
                "mode": "exam" if i % 2 == 0 else "practice",
            })
            assert resp.status_code == 200
            data = resp.json()

            for q in data["questions"]:
                # 1. Negative assertions: correct_answer and explanation_zh must NOT exist
                assert "correct_answer" not in q, f"Anti-cheating breached: 'correct_answer' found in {q['id']}"
                assert "explanation_zh" not in q, f"Anti-cheating breached: 'explanation_zh' found in {q['id']}"
                assert "answer" not in q, f"Suspicious key 'answer' found in {q['id']}"
                assert "rationale" not in q, f"Suspicious key 'rationale' found in {q['id']}"

                # 2. Positive schema verification: required client fields only
                assert "id" in q
                assert "chapter_id" in q
                assert "question_number" in q
                assert "stem" in q
                assert "options" in q
                assert isinstance(q["options"], dict)
                assert set(q["options"].keys()) == {"a", "b", "c", "d"}

            # 3. String-level sanity check on raw JSON text
            # Ensure "correct_answer" does not appear as a json key
            raw_text = resp.text
            assert '"correct_answer"' not in raw_text, "Raw response payload contains 'correct_answer' key"
            assert '"explanation_zh"' not in raw_text, "Raw response payload contains 'explanation_zh' key"


# ==============================================================================
# 3. Scoring Extremes (100%, 0%, Partial & Unanswered)
# ==============================================================================

class TestScoringExtremes:
    """Adversarially tests extreme grading conditions and unanswered question handling."""

    def test_100_percent_perfect_score_submission(self, client: TestClient):
        """Submitting all correct answers must yield 100.0% score and perfect chapter breakdowns."""
        # 1. Create a 30-question session across all 6 chapters
        resp_new = client.post("/api/quiz/new", json={
            "chapter_ids": ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"],
            "question_count": 30,
            "mode": "exam",
        })
        assert resp_new.status_code == 200
        session_id = resp_new.json()["session_id"]

        # 2. Extract ground truth correct answers from backend session cache
        raw_questions = quiz_sessions[session_id]["questions"]
        assert len(raw_questions) == 30
        correct_answers = {q["id"]: q["correct_answer"] for q in raw_questions}

        # 3. Submit perfect answers
        resp_sub = client.post("/api/quiz/submit", json={
            "session_id": session_id,
            "answers": correct_answers,
        })
        assert resp_sub.status_code == 200
        result = resp_sub.json()

        # 4. Verify 100% metrics
        assert result["total_questions"] == 30
        assert result["correct_count"] == 30
        assert math.isclose(result["score_percentage"], 100.0, abs_tol=0.001)

        # All results must be marked correct
        for item in result["results"]:
            assert item["is_correct"] is True
            assert item["user_answer"] == item["correct_answer"]

        # Chapter breakdown must be 100% for all chapters present
        for ch_id, stats in result["chapter_breakdown"].items():
            assert stats["correct"] == stats["total"], (
                f"Chapter {ch_id} breakdown imperfect: {stats['correct']}/{stats['total']}"
            )

    def test_0_percent_zero_score_submission_and_rich_diagnostics(self, client: TestClient):
        """Submitting all wrong answers must yield 0.0% score and rich Chinese explanations for all questions."""
        # 1. Create a 25-question session
        resp_new = client.post("/api/quiz/new", json={
            "chapter_ids": ["Ch_01", "Ch_02", "Ch_03"],
            "question_count": 25,
            "mode": "practice",
        })
        assert resp_new.status_code == 200
        session_id = resp_new.json()["session_id"]
        raw_questions = quiz_sessions[session_id]["questions"]

        # 2. Construct guaranteed wrong answers
        wrong_answers = {}
        for q in raw_questions:
            correct = q["correct_answer"].lower()
            # Pick a letter that differs from the correct answer
            wrong = "a" if correct != "a" else "b"
            wrong_answers[q["id"]] = wrong

        # 3. Submit wrong answers
        resp_sub = client.post("/api/quiz/submit", json={
            "session_id": session_id,
            "answers": wrong_answers,
        })
        assert resp_sub.status_code == 200
        result = resp_sub.json()

        # 4. Verify 0% metrics
        assert result["total_questions"] == 25
        assert result["correct_count"] == 0
        assert math.isclose(result["score_percentage"], 0.0, abs_tol=0.001)

        # 5. Verify every single wrong answer has detailed Chinese explanations
        for item in result["results"]:
            assert item["is_correct"] is False
            assert item["user_answer"] != item["correct_answer"]

            exp = item.get("explanation_zh")
            assert exp is not None, f"Question {item['question_id']} missing explanation_zh"
            assert isinstance(exp["concept"], str) and len(exp["concept"].strip()) > 0
            assert isinstance(exp["rationale"], str) and len(exp["rationale"].strip()) > 0
            assert isinstance(exp["distractors"], dict)
            assert len(exp["distractors"]) >= 1, (
                f"Question {item['question_id']} distractors dictionary is empty!"
            )

        # Chapter breakdown must have 0 correct
        for ch_id, stats in result["chapter_breakdown"].items():
            assert stats["correct"] == 0
            assert stats["total"] > 0

    def test_partial_and_unanswered_submission(self, client: TestClient):
        """Submitting answers for only half the questions must score unattempted questions as incorrect."""
        # 1. Create a 20-question session
        resp_new = client.post("/api/quiz/new", json={
            "chapter_ids": ["Ch_04", "Ch_05"],
            "question_count": 20,
            "mode": "practice",
        })
        assert resp_new.status_code == 200
        session_id = resp_new.json()["session_id"]
        raw_questions = quiz_sessions[session_id]["questions"]
        assert len(raw_questions) == 20

        # 2. Submit answers for first 10 questions only (6 correct, 4 wrong), leaving 10 unattempted
        partial_answers = {}
        for i, q in enumerate(raw_questions[:10]):
            if i < 6:
                partial_answers[q["id"]] = q["correct_answer"]
            else:
                partial_answers[q["id"]] = "a" if q["correct_answer"].lower() != "a" else "b"

        # 3. Submit partial answers
        resp_sub = client.post("/api/quiz/submit", json={
            "session_id": session_id,
            "answers": partial_answers,
        })
        assert resp_sub.status_code == 200
        result = resp_sub.json()

        # 4. Verify evaluation metrics
        assert result["total_questions"] == 20
        assert result["correct_count"] == 6
        expected_percentage = round(6 / 20 * 100.0, 2)  # 30.0%
        assert math.isclose(result["score_percentage"], expected_percentage, abs_tol=0.01)

        # 5. Check unanswered questions
        answered_ids = set(partial_answers.keys())
        unanswered_results = [r for r in result["results"] if r["question_id"] not in answered_ids]
        assert len(unanswered_results) == 10

        for unattempted in unanswered_results:
            assert unattempted["user_answer"] is None, "Unattempted question should have user_answer=None"
            assert unattempted["is_correct"] is False, "Unattempted question must be scored as incorrect"
            assert unattempted["explanation_zh"] is not None, "Unattempted question must still receive explanation"


# ==============================================================================
# 4. Robustness & Error Injection
# ==============================================================================

class TestRobustnessAndErrorInjection:
    """Stress-tests invalid inputs, malformed sessions, empty answers, and extra parameters."""

    def test_submit_to_unknown_uuid_returns_404(self, client: TestClient):
        """Submitting to a non-existent UUID must return HTTP 404."""
        unknown_id = str(uuid.uuid4())
        resp = client.post("/api/quiz/submit", json={
            "session_id": unknown_id,
            "answers": {"Ch01_Q001": "a"},
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_submit_to_malformed_session_ids_returns_404(self, client: TestClient):
        """Submitting to non-UUID or malicious strings must return HTTP 404 without unhandled crashes."""
        malformed_inputs = [
            "invalid_session_id_12345",
            "../../../etc/passwd",
            "<script>alert(1)</script>",
            "' OR 1=1 --",
            "",
            "   ",
        ]
        for bad_id in malformed_inputs:
            resp = client.post("/api/quiz/submit", json={
                "session_id": bad_id,
                "answers": {},
            })
            assert resp.status_code == 404, f"Expected 404 for malformed session ID '{bad_id}', got {resp.status_code}"

    def test_submit_empty_answers_dictionary_grades_validly(self, client: TestClient):
        """Submitting an empty answers dictionary {} must grade gracefully with 0% score and all questions marked incorrect."""
        resp_new = client.post("/api/quiz/new", json={
            "chapter_ids": ["Ch_01"],
            "question_count": 5,
        })
        assert resp_new.status_code == 200
        session_id = resp_new.json()["session_id"]

        resp_sub = client.post("/api/quiz/submit", json={
            "session_id": session_id,
            "answers": {},
        })
        assert resp_sub.status_code == 200
        data = resp_sub.json()
        assert data["total_questions"] == 5
        assert data["correct_count"] == 0
        assert math.isclose(data["score_percentage"], 0.0, abs_tol=0.001)
        assert all(not r["is_correct"] for r in data["results"])
        assert all(r["user_answer"] is None for r in data["results"])

    def test_submit_extra_unrecognized_question_ids_handled_gracefully(self, client: TestClient):
        """Submitting extra/unrecognized question IDs must not crash the engine and must not inject spurious results."""
        resp_new = client.post("/api/quiz/new", json={
            "chapter_ids": ["Ch_02"],
            "question_count": 5,
        })
        session_id = resp_new.json()["session_id"]
        valid_ids = [q["id"] for q in resp_new.json()["questions"]]

        # Submit answers including phantom question IDs
        polluted_answers = {
            valid_ids[0]: "a",
            "NONEXISTENT_Q999": "b",
            "HACKED_QUESTION_ID": "c",
            "Ch99_Q9999": "d",
        }
        resp_sub = client.post("/api/quiz/submit", json={
            "session_id": session_id,
            "answers": polluted_answers,
        })
        assert resp_sub.status_code == 200
        data = resp_sub.json()

        # Engine must evaluate only the 5 questions belonging to the session
        assert data["total_questions"] == 5
        result_ids = [r["question_id"] for r in data["results"]]
        assert set(result_ids) == set(valid_ids)
        assert "NONEXISTENT_Q999" not in result_ids

    def test_case_insensitivity_and_whitespace_in_answers(self, client: TestClient):
        """Submitting answers with uppercase letters or leading/trailing whitespace must be normalized."""
        resp_new = client.post("/api/quiz/new", json={
            "chapter_ids": ["Ch_01"],
            "question_count": 5,
        })
        session_id = resp_new.json()["session_id"]
        raw_questions = quiz_sessions[session_id]["questions"]

        # Provide uppercase with spaces for correct answers
        normalized_answers = {
            q["id"]: f"  {q['correct_answer'].upper()}  "
            for q in raw_questions
        }
        resp_sub = client.post("/api/quiz/submit", json={
            "session_id": session_id,
            "answers": normalized_answers,
        })
        assert resp_sub.status_code == 200
        data = resp_sub.json()
        assert data["correct_count"] == 5
        assert math.isclose(data["score_percentage"], 100.0, abs_tol=0.001)

    def test_quiz_create_clamping_and_validation(self, client: TestClient):
        """Validates count clamping and chapter selection error handling."""
        # 1. Non-positive count clamps to 1
        r_zero = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 0})
        assert r_zero.status_code == 200
        assert r_zero.json()["total_questions"] == 1

        r_neg = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": -99})
        assert r_neg.status_code == 200
        assert r_neg.json()["total_questions"] == 1

        # 2. Count exceeding pool clamps to total available
        r_huge = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_03"], "question_count": 999999})
        assert r_huge.status_code == 200
        assert r_huge.json()["total_questions"] == 72  # Ch_03 has 72 questions

        # 3. Empty chapter selection returns 400
        r_empty = client.post("/api/quiz/new", json={"chapter_ids": [], "question_count": 10})
        assert r_empty.status_code == 400

        # 4. Unknown chapter returns 400
        r_bad_ch = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_999"], "question_count": 10})
        assert r_bad_ch.status_code == 400
