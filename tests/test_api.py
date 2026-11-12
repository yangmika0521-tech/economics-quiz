"""
tests/test_api.py
Integration & Contract Tests for Economics Quiz FastAPI REST Endpoints.

Endpoints Covered:
- GET /api/chapters: Chapter metadata list, question pool statistics
- POST /api/quiz/new: Deduplicated random sampling, anti-cheating omission, session creation
- POST /api/quiz/submit: Scoring engine, chapter breakdown, diagnostic payload generation
- Static & Root: GET / serves the SPA frontend

Tiers Covered:
- Tier 2: Boundary & Corner Cases (invalid IDs, parameter validation, clamp bounds)
- Tier 3: Cross-Feature Interactions (mode switching, anti-cheating, media references)
"""

import pytest
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

# Try importing the FastAPI application
try:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    HAS_APP = True
except (ImportError, ModuleNotFoundError):
    client = None
    HAS_APP = False


# ==============================================================================
# Interface Contract Schema Models (Mirroring PROJECT.md § Interface Contracts)
# ==============================================================================

class ChapterMetadataSchema(BaseModel):
    id: str
    number: int
    title_en: str
    title_zh: str
    total_questions: int


class ChaptersResponseSchema(BaseModel):
    chapters: List[ChapterMetadataSchema]


class QuizCreateRequestSchema(BaseModel):
    chapter_ids: List[str]
    question_count: int
    mode: str = "practice"


class QuizQuestionClientSchema(BaseModel):
    id: str
    chapter_id: str
    question_number: int
    stem: str
    image_url: Optional[str] = None
    context_table: Optional[str] = None
    options: Dict[str, str]


class QuizCreateResponseSchema(BaseModel):
    session_id: str
    total_questions: int
    questions: List[QuizQuestionClientSchema]


class SubmissionRequestSchema(BaseModel):
    session_id: str
    answers: Dict[str, str]


class DiagnosticExplanationSchema(BaseModel):
    concept: str
    rationale: str
    distractors: Dict[str, str]


class QuestionResultSchema(BaseModel):
    question_id: str
    stem: str
    user_answer: Optional[str]
    correct_answer: str
    is_correct: bool
    image_url: Optional[str] = None
    explanation_zh: Optional[DiagnosticExplanationSchema] = None


class SubmissionResponseSchema(BaseModel):
    total_questions: int
    correct_count: int
    score_percentage: float
    chapter_breakdown: Dict[str, Dict[str, int]]
    results: List[QuestionResultSchema]


# ==============================================================================
# Tier 1 & 2: API Contract Schema Validation Tests
# ==============================================================================

class TestApiSchemasContract:
    """Validates the Pydantic interface contracts defined in PROJECT.md."""

    def test_chapter_metadata_schema_validates(self):
        """Verify ChapterMetadataSchema validates compliant data correctly."""
        data = {
            "id": "Ch_01",
            "number": 1,
            "title_en": "Ten Principles of Economics",
            "title_zh": "經濟學十大原理",
            "total_questions": 113,
        }
        obj = ChapterMetadataSchema(**data)
        assert obj.id == "Ch_01"
        assert obj.number == 1
        assert obj.total_questions == 113

    def test_quiz_create_response_anti_cheating_contract(self):
        """Verify QuizCreateResponseSchema omits correct_answer and explanation_zh."""
        question_data = {
            "id": "Ch01_Q001",
            "chapter_id": "Ch_01",
            "question_number": 1,
            "stem": "Resources are...",
            "image_url": None,
            "context_table": None,
            "options": {"a": "opt A", "b": "opt B", "c": "opt C", "d": "opt D"},
        }
        resp = QuizCreateResponseSchema(
            session_id="test-session-uuid",
            total_questions=1,
            questions=[QuizQuestionClientSchema(**question_data)],
        )
        payload = resp.model_dump()
        for q in payload["questions"]:
            assert "correct_answer" not in q, "Anti-cheating violation: correct_answer exposed in client payload"
            assert "explanation_zh" not in q, "Anti-cheating violation: explanation_zh exposed in client payload"

    def test_submission_response_schema_validates(self):
        """Verify SubmissionResponseSchema validates score summary and diagnostics."""
        result_data = {
            "total_questions": 1,
            "correct_count": 0,
            "score_percentage": 0.0,
            "chapter_breakdown": {"Ch_01": {"correct": 0, "total": 1}},
            "results": [
                {
                    "question_id": "Ch01_Q001",
                    "stem": "Resources are...",
                    "user_answer": "a",
                    "correct_answer": "c",
                    "is_correct": False,
                    "image_url": None,
                    "explanation_zh": {
                        "concept": "稀少性",
                        "rationale": "資源是有限的",
                        "distractors": {"a": "錯誤"},
                    },
                }
            ],
        }
        obj = SubmissionResponseSchema(**result_data)
        assert obj.score_percentage == 0.0
        assert obj.results[0].is_correct is False
        assert obj.results[0].explanation_zh.concept == "稀少性"


# ==============================================================================
# Tier 2 & 3: Live FastAPI Endpoints Integration Tests (Executed when app is ready)
# ==============================================================================

@pytest.mark.skipif(not HAS_APP, reason="app.main not yet available (M2 in progress)")
class TestLiveApiEndpoints:
    """Integration tests running against the live FastAPI application."""

    def test_get_chapters_endpoint(self):
        """GET /api/chapters returns 200 with all 6 chapters and question totals."""
        response = client.get("/api/chapters")
        assert response.status_code == 200
        data = response.json()
        assert "chapters" in data
        assert len(data["chapters"]) == 6
        total = sum(c["total_questions"] for c in data["chapters"])
        assert total == 585

    def test_post_quiz_new_success(self):
        """POST /api/quiz/new creates a session with sampled questions without duplicates."""
        payload = {
            "chapter_ids": ["Ch_01", "Ch_02"],
            "question_count": 10,
            "mode": "practice",
        }
        response = client.post("/api/quiz/new", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert len(data["questions"]) == 10
        q_ids = [q["id"] for q in data["questions"]]
        assert len(q_ids) == len(set(q_ids)), "Duplicate questions found in quiz session"
        # Anti-cheating verification
        for q in data["questions"]:
            assert "correct_answer" not in q
            assert "explanation_zh" not in q

    def test_post_quiz_new_invalid_chapter_error(self):
        """POST /api/quiz/new with non-existent chapter ID returns 400 or 422 error."""
        payload = {
            "chapter_ids": ["Ch_99_NonExistent"],
            "question_count": 5,
        }
        response = client.post("/api/quiz/new", json=payload)
        assert response.status_code in {400, 422}

    def test_post_quiz_new_empty_chapter_list_error(self):
        """POST /api/quiz/new with empty chapter_ids returns 400 or 422 error."""
        payload = {
            "chapter_ids": [],
            "question_count": 5,
        }
        response = client.post("/api/quiz/new", json=payload)
        assert response.status_code in {400, 422}

    def test_post_quiz_new_count_clamping(self):
        """POST /api/quiz/new requesting count larger than pool clamps to pool size."""
        payload = {
            "chapter_ids": ["Ch_03"],  # 72 questions
            "question_count": 1000,
        }
        response = client.post("/api/quiz/new", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["questions"]) == 72, f"Expected clamped count 72, got {len(data['questions'])}"

    def test_post_quiz_new_non_positive_count_clamping(self):
        """POST /api/quiz/new with count <= 0 clamps to minimum 1 question."""
        for cnt in [0, -5]:
            payload = {"chapter_ids": ["Ch_01"], "question_count": cnt}
            response = client.post("/api/quiz/new", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert len(data["questions"]) == 1, f"Count {cnt} expected clamped count 1, got {len(data['questions'])}"

    def test_post_quiz_submit_evaluation_flow(self):
        """POST /api/quiz/submit evaluates answers and returns score and Chinese explanations."""
        # Step 1: Create session
        new_res = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 3})
        assert new_res.status_code == 200
        quiz_data = new_res.json()
        session_id = quiz_data["session_id"]
        questions = quiz_data["questions"]

        # Step 2: Submit answers (deliberately all "a")
        answers = {q["id"]: "a" for q in questions}
        submit_res = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": answers})
        assert submit_res.status_code == 200
        res_data = submit_res.json()

        assert res_data["total_questions"] == 3
        assert "score_percentage" in res_data
        assert "correct_count" in res_data
        assert "results" in res_data
        assert len(res_data["results"]) == 3

        # Check diagnostics on incorrect questions
        for item in res_data["results"]:
            if not item["is_correct"]:
                assert "explanation_zh" in item
                assert item["explanation_zh"] is not None
                assert "rationale" in item["explanation_zh"]

    def test_post_quiz_submit_invalid_session_error(self):
        """POST /api/quiz/submit with unknown session_id returns 404 or 400 error."""
        response = client.post("/api/quiz/submit", json={
            "session_id": "invalid-uuid-99999",
            "answers": {"Ch01_Q001": "a"},
        })
        assert response.status_code in {400, 404, 422}
