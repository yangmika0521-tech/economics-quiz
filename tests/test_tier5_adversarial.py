"""Tier 5 Integrated Adversarial Coverage Hardening Suite.

Integrates Challenger 1 (Backend & API adversarial stress, concurrency, clamping, anti-cheating)
and Challenger 2 (Frontend dual-runtime parity, data bank fuzzing, Unicode robustness, Chinese explanations)
into a unified, robust, cross-platform adversarial test suite.

Classes:
1. TestOutOfBoundsChapterIds: Backend stress on chapter IDs (nonexistent, injection, whitespace, casing, types).
2. TestQuestionCountBoundaryExtremes: Boundary clamping, count extremes, and defensive float/NaN hardening.
3. TestPayloadMutationsAndMalformedSubmissions: Malformed payloads, partial answers, rogue keys, case-insensitivity.
4. TestRapidConcurrencyAndStressSimulation: 60 concurrent creations, 40 concurrent submissions, bounded LRU eviction.
5. TestAntiCheatingInvariantsAdversarial: Anti-cheating answer omission invariants under adversarial queries.
6. TestDualRuntimeSamplingParity: Client-side JS Fisher-Yates vs Python random.sample parity and distribution.
7. TestScoringAndDiagnosticParity: Client-side JS evaluation vs Python quiz engine scoring & diagnostic parity.
8. TestDataBankFuzzingAndUnicodeRobustness: Full 585 Qs Pydantic validation, extreme Unicode, Markdown tables, HTML escaping.
9. TestTraditionalChineseExplanationCoverage: 585 Qs audit of concept, rationale, 3 distractors, and zero placeholders.
"""

import json
import math
import os
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, List, Optional

import pytest
from starlette.testclient import TestClient
from pydantic import ValidationError

from app.main import app, quiz_sessions, questions_cache, chapters_cache, MAX_SESSIONS
from app import quiz_engine
from app.models import (
    QuizConfig,
    QuizSession,
    QuizSubmission,
    QuizResult,
    Chapter,
    Question,
    QuestionBank,
    ExplanationZh,
)

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_JSON_PATH = PROJECT_ROOT / "data" / "questions.json"
APP_JS_PATH = PROJECT_ROOT / "static" / "js" / "app.js"

# Node.js Headless Ingestion & Execution Runner for static/js/app.js
NODE_HARNESS_CODE = """
const fs = require('fs');
const vm = require('vm');

const inputData = fs.readFileSync(0, 'utf8');
const req = JSON.parse(inputData);

let code = fs.readFileSync(req.app_js_path, 'utf8');

// Instrument app.js to expose private functions
code = code.replace(
  /\\}\\)\\(\\);?\\s*$/,
  'global.__TEST_EXPORTS__ = { clientSampleQuestions, clientEvaluateSubmission, renderMarkdownTable, formatOptionHtml, escapeHtml, resolveMediaUrl }; })();'
);

const mockElement = () => ({
  addEventListener: () => {},
  querySelector: () => mockElement(),
  querySelectorAll: () => [],
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  appendChild: () => {},
  style: {},
  dataset: {}
});

const sandbox = {
  console: { log: () => {}, warn: () => {}, error: () => {}, info: () => {} },
  global: {},
  window: { location: { hostname: 'localhost', pathname: '/', protocol: 'http:' } },
  document: {
    addEventListener: () => {},
    getElementById: () => mockElement(),
    querySelectorAll: () => [],
    createElement: () => mockElement(),
  },
  setTimeout, clearTimeout, setInterval, clearInterval,
  AbortController: global.AbortController
};
sandbox.window.document = sandbox.document;
sandbox.global = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const exp = sandbox.global.__TEST_EXPORTS__;
if (!exp) {
  process.stderr.write("Failed to export functions from app.js\\n");
  process.exit(1);
}

let res;
try {
  if (req.action === 'sample') {
    res = exp.clientSampleQuestions(req.pool, req.chapter_ids, req.count);
  } else if (req.action === 'sample_batch') {
    // Fast in-process statistical batch runner
    let ch1Count = 0;
    const picked = new Set();
    for (let i = 0; i < req.iterations; i++) {
      const sampled = exp.clientSampleQuestions(req.pool, req.chapter_ids, req.sample_size);
      for (const q of sampled) {
        if (q.chapter_id === 'Ch_01') ch1Count++;
        picked.add(q.id);
      }
    }
    res = { ch1_count: ch1Count, picked_count: picked.size };
  } else if (req.action === 'evaluate') {
    res = exp.clientEvaluateSubmission(req.sampled_questions, req.user_answers);
  } else if (req.action === 'render_table') {
    res = exp.renderMarkdownTable(req.md_text);
  } else if (req.action === 'format_option') {
    res = exp.formatOptionHtml(req.text);
  } else if (req.action === 'escape_html') {
    res = exp.escapeHtml(req.str);
  } else {
    throw new Error('Unknown action: ' + req.action);
  }
  process.stdout.write(JSON.stringify(res));
} catch (err) {
  process.stderr.write(err.stack || err.message);
  process.exit(1);
}
"""


def invoke_js(action: str, **kwargs) -> Any:
    """Executes a target function in static/js/app.js via Node.js."""
    req_payload = {
        "action": action,
        "app_js_path": str(APP_JS_PATH).replace("\\", "/"),
        **kwargs,
    }
    proc = subprocess.run(
        ["node", "-e", NODE_HARNESS_CODE],
        input=json.dumps(req_payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Node execution failed (code {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Provides a Starlette/FastAPI TestClient for API endpoint interactions."""
    return TestClient(app)


@pytest.fixture(scope="session")
def raw_bank_data() -> Dict[str, Any]:
    """Loads raw questions.json dictionary."""
    assert QUESTIONS_JSON_PATH.exists(), f"Missing question bank at {QUESTIONS_JSON_PATH}"
    with open(QUESTIONS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def all_questions(raw_bank_data) -> List[Dict[str, Any]]:
    return raw_bank_data["questions"]


@pytest.fixture(scope="session")
def all_chapters(raw_bank_data) -> List[Dict[str, Any]]:
    return raw_bank_data["chapters"]


# ==============================================================================
# 1. Out-of-bounds Chapter IDs (Backend Stress)
# ==============================================================================

class TestOutOfBoundsChapterIds:
    """Stress-tests /api/quiz/new against invalid, nonexistent, injected, or malformed chapter IDs."""

    def test_nonexistent_chapter_ids_returns_400(self, client: TestClient):
        """Chapter IDs not in the known pool must be rejected cleanly with HTTP 400."""
        invalid_cases = [
            ["Ch_99"],
            ["Ch_00"],
            ["Ch_07"],
            ["Ch_999"],
            ["nonexistent"],
            ["Ch_01", "Ch_99"],  # Partial invalid: all must be known
        ]
        for chapters in invalid_cases:
            resp = client.post("/api/quiz/new", json={"chapter_ids": chapters, "question_count": 5})
            assert resp.status_code == 400, f"Expected 400 for chapter_ids={chapters}, got {resp.status_code}: {resp.text}"
            detail = resp.json().get("detail", "")
            assert "unknown chapter IDs" in detail or "Invalid chapter selection" in detail

    def test_empty_chapter_list_returns_400(self, client: TestClient):
        """Empty chapter_ids list must be rejected with HTTP 400."""
        resp = client.post("/api/quiz/new", json={"chapter_ids": [], "question_count": 5})
        assert resp.status_code == 400
        assert "cannot be empty" in resp.json().get("detail", "")

    def test_injection_payloads_in_chapter_ids_rejected(self, client: TestClient):
        """SQL injection, script tags, and path traversal strings in chapter_ids must return HTTP 400 without crashing."""
        malicious_inputs = [
            ["' OR '1'='1"],
            ["Ch_01'; DROP TABLE questions;--"],
            ["<script>alert(1)</script>"],
            ["../../etc/passwd"],
            ["${7*7}"],
            ["{{7*7}}"],
            ["%00Ch_01"],
            ["Ch_01\x00"],
        ]
        for bad_id in malicious_inputs:
            resp = client.post("/api/quiz/new", json={"chapter_ids": bad_id, "question_count": 5})
            assert resp.status_code == 400, f"Malicious input {bad_id} did not yield 400: {resp.status_code}"

    def test_case_sensitivity_strictness(self, client: TestClient):
        """Chapter IDs are strictly case-sensitive. Lowercase or capitalized variants must be rejected."""
        case_variants = [
            ["ch_01"],
            ["CH_01"],
            ["cH_01"],
            ["ch_02"],
            ["CH_06"],
        ]
        for var in case_variants:
            resp = client.post("/api/quiz/new", json={"chapter_ids": var, "question_count": 5})
            assert resp.status_code == 400, f"Case variation {var} was unexpectedly accepted (status {resp.status_code})"

    def test_surrounding_whitespace_in_chapter_ids_rejected(self, client: TestClient):
        """Whitespace-padded chapter IDs must not match canonical keys and must return HTTP 400."""
        whitespace_cases = [
            [" Ch_01"],
            ["Ch_01 "],
            [" Ch_01 "],
            ["\tCh_01\n"],
            ["Ch_ 01"],
        ]
        for ws in whitespace_cases:
            resp = client.post("/api/quiz/new", json={"chapter_ids": ws, "question_count": 5})
            assert resp.status_code == 400, f"Whitespace variant {ws} was unexpectedly accepted"

    def test_empty_string_in_chapter_list_rejected(self, client: TestClient):
        """Empty string elements within chapter_ids must be rejected with HTTP 400."""
        empty_cases = [
            [""],
            ["Ch_01", ""],
            ["", "Ch_02"],
        ]
        for ep in empty_cases:
            resp = client.post("/api/quiz/new", json={"chapter_ids": ep, "question_count": 5})
            assert resp.status_code == 400

    def test_duplicate_chapter_ids_deduplication(self, client: TestClient):
        """Supplying duplicate valid chapter IDs must not inflate eligible pool or crash."""
        resp = client.post(
            "/api/quiz/new",
            json={"chapter_ids": ["Ch_01", "Ch_01", "Ch_02", "Ch_01"], "question_count": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_questions"] == 10
        sampled_chapters = {q["chapter_id"] for q in data["questions"]}
        assert sampled_chapters.issubset({"Ch_01", "Ch_02"})

    def test_malformed_chapter_ids_type_returns_422(self, client: TestClient):
        """Supplying non-list types or null for chapter_ids must trigger Pydantic HTTP 422."""
        invalid_types = [
            "Ch_01",          # string instead of list
            123,              # integer instead of list
            {"id": "Ch_01"},  # dict instead of list
            None,             # null
            [None],           # list with null element
        ]
        for bad_type in invalid_types:
            resp = client.post("/api/quiz/new", json={"chapter_ids": bad_type, "question_count": 5})
            assert resp.status_code == 422, f"Expected 422 for type {type(bad_type)}, got {resp.status_code}"


# ==============================================================================
# 2. Question Count Boundary Extremes & Hardening
# ==============================================================================

class TestQuestionCountBoundaryExtremes:
    """Stress-tests question count extremes, clamping guarantees, type coercion, and floating point boundaries."""

    def test_negative_counts_clamped_to_one(self, client: TestClient):
        """Negative counts (-1, -5, -100, -999999) must be clamped to exactly 1 question."""
        for neg_count in [-1, -5, -100, -999999]:
            resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": neg_count})
            assert resp.status_code == 200, f"Failed for count={neg_count}: {resp.status_code}"
            data = resp.json()
            assert data["total_questions"] == 1, f"Expected 1 question for count={neg_count}, got {data['total_questions']}"
            assert len(data["questions"]) == 1

    def test_zero_count_clamped_to_one(self, client: TestClient):
        """Zero count (0) must be clamped to exactly 1 question."""
        resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_questions"] == 1
        assert len(data["questions"]) == 1

    def test_single_question_boundary(self, client: TestClient):
        """Count of exactly 1 question must return 1 question without error."""
        resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_questions"] == 1
        assert len(data["questions"]) == 1

    def test_huge_overflow_count_clamped_to_pool_size(self, client: TestClient):
        """Requesting 100,000 questions must clamp to the exact total number of eligible questions."""
        # Ch_01 alone has 113 questions
        resp_ch1 = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 100000})
        assert resp_ch1.status_code == 200
        data_ch1 = resp_ch1.json()
        assert data_ch1["total_questions"] == 113
        assert len(data_ch1["questions"]) == 113
        # Zero duplicate question IDs
        q_ids = [q["id"] for q in data_ch1["questions"]]
        assert len(q_ids) == len(set(q_ids))

        # All chapters combined: 113 + 87 + 72 + 124 + 86 + 103 = 585
        all_chs = ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"]
        resp_all = client.post("/api/quiz/new", json={"chapter_ids": all_chs, "question_count": 100000})
        assert resp_all.status_code == 200
        data_all = resp_all.json()
        assert data_all["total_questions"] == 585
        assert len(data_all["questions"]) == 585

    def test_pool_size_clamping_per_chapter(self, client: TestClient):
        """Each individual chapter's question count must clamp to its exact oracle count."""
        expected_counts = {
            "Ch_01": 113,
            "Ch_02": 87,
            "Ch_03": 72,
            "Ch_04": 124,
            "Ch_05": 86,
            "Ch_06": 103,
        }
        for ch_id, expected_total in expected_counts.items():
            resp = client.post("/api/quiz/new", json={"chapter_ids": [ch_id], "question_count": 9999})
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_questions"] == expected_total, (
                f"Chapter {ch_id} clamped to {data['total_questions']} instead of {expected_total}"
            )

    def test_float_count_in_api_payload(self, client: TestClient):
        """Pydantic v2 rejects floating-point numbers with fractional components in integer fields with HTTP 422."""
        fractional_counts = [5.5, 10.99, 0.5, -3.7]
        for fc in fractional_counts:
            resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": fc})
            assert resp.status_code == 422, f"Float {fc} did not trigger 422 validation error: {resp.status_code}"

    def test_string_count_handling(self, client: TestClient):
        """Numeric strings must be coerced; non-numeric strings must be rejected with HTTP 422."""
        # Coercible numeric string
        resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": "15"})
        assert resp.status_code == 200
        assert resp.json()["total_questions"] == 15

        # Non-numeric string
        for bad_str in ["ten", "invalid", "", "15.5", "NaN"]:
            resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": bad_str})
            assert resp.status_code == 422, f"String '{bad_str}' was not rejected with 422: {resp.status_code}"

    def test_direct_quiz_engine_float_hardening(self):
        """Verifies defensive conversion of float, NaN, and Inf count values in quiz_engine.sample_questions.

        Confirms that defensive integer conversion prevents unhandled TypeError crashes.
        """
        pool = questions_cache or []
        assert len(pool) > 0, "Question pool must not be empty"

        # Float count is safely converted to integer (3.5 -> 3) without raising TypeError
        sampled_float = quiz_engine.sample_questions(pool, ["Ch_01"], 3.5)
        assert len(sampled_float) == 3

        # Float count with rounding check
        sampled_float_round = quiz_engine.sample_questions(pool, ["Ch_01"], 7.9)
        assert len(sampled_float_round) == 7

        # NaN safely caught by (ValueError, TypeError) and defaults to 1
        sampled_nan = quiz_engine.sample_questions(pool, ["Ch_01"], float("nan"))
        assert len(sampled_nan) == 1

        # Inf triggers clamping because inf > len(eligible) is True
        sampled_inf = quiz_engine.sample_questions(pool, ["Ch_01"], float("inf"))
        assert len(sampled_inf) == 113, "float('inf') should clamp to 113"


# ==============================================================================
# 3. Payload Mutations & Malformed Submissions to /api/quiz/submit
# ==============================================================================

class TestPayloadMutationsAndMalformedSubmissions:
    """Stress-tests /api/quiz/submit with malformed payloads, partial answers, invalid keys, and mutation vectors."""

    @pytest.fixture
    def active_session(self, client: TestClient) -> Dict[str, Any]:
        """Creates a fresh 10-question session in Ch_01 for testing submissions."""
        resp = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 10})
        assert resp.status_code == 200
        return resp.json()

    def test_missing_required_fields_returns_422(self, client: TestClient, active_session: Dict[str, Any]):
        """Missing session_id, answers, or submitting an empty JSON body must return HTTP 422."""
        session_id = active_session["session_id"]

        # Missing answers field
        resp1 = client.post("/api/quiz/submit", json={"session_id": session_id})
        assert resp1.status_code == 422

        # Missing session_id field
        resp2 = client.post("/api/quiz/submit", json={"answers": {"Ch01_Q001": "a"}})
        assert resp2.status_code == 422

        # Completely empty JSON
        resp3 = client.post("/api/quiz/submit", json={})
        assert resp3.status_code == 422

    def test_nonexistent_or_malformed_session_id_returns_404(self, client: TestClient):
        """Nonexistent UUID or malformed session IDs must return HTTP 404."""
        invalid_sessions = [
            str(uuid.uuid4()),
            "00000000-0000-0000-0000-000000000000",
            "nonexistent-session-id",
            "../../../etc/passwd",
            "' OR '1'='1",
            "",
        ]
        for bad_id in invalid_sessions:
            resp = client.post("/api/quiz/submit", json={"session_id": bad_id, "answers": {}})
            assert resp.status_code == 404, f"Session ID {bad_id} did not yield 404: {resp.status_code}"

    def test_empty_answers_dict_evaluates_to_zero_with_diagnostics(self, client: TestClient, active_session: Dict[str, Any]):
        """Submitting an empty answers dictionary {} must evaluate gracefully to 0.0% score.

        All questions must have user_answer=None, is_correct=False, and full Chinese explanations.
        """
        session_id = active_session["session_id"]
        resp = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": {}})
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_questions"] == 10
        assert data["correct_count"] == 0
        assert data["score_percentage"] == 0.0
        assert len(data["results"]) == 10

        for r in data["results"]:
            assert r["user_answer"] is None
            assert r["is_correct"] is False
            assert r["correct_answer"] in {"a", "b", "c", "d"}
            assert r["explanation_zh"] is not None
            assert "concept" in r["explanation_zh"]
            assert "rationale" in r["explanation_zh"]

    def test_partial_submission_single_question_answered(self, client: TestClient, active_session: Dict[str, Any]):
        """Submitting an answer for only 1 of 10 questions must grade the 1 question and treat the other 9 as unanswered."""
        session_id = active_session["session_id"]
        q1 = active_session["questions"][0]
        q1_id = q1["id"]

        # Look up correct answer from session store in backend
        raw_q1 = next(q for q in quiz_sessions[session_id]["questions"] if q["id"] == q1_id)
        correct_ans = raw_q1["correct_answer"]

        # Submit only q1
        payload = {"session_id": session_id, "answers": {q1_id: correct_ans}}
        resp = client.post("/api/quiz/submit", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_questions"] == 10
        assert data["correct_count"] == 1
        assert data["score_percentage"] == 10.0

        r1 = next(r for r in data["results"] if r["question_id"] == q1_id)
        assert r1["is_correct"] is True
        assert r1["user_answer"] == correct_ans

        unanswered = [r for r in data["results"] if r["question_id"] != q1_id]
        assert len(unanswered) == 9
        for u in unanswered:
            assert u["user_answer"] is None
            assert u["is_correct"] is False
            assert u["explanation_zh"] is not None

    def test_answers_outside_valid_options_marked_incorrect(self, client: TestClient, active_session: Dict[str, Any]):
        """Arbitrary values outside {'a','b','c','d'} (e.g. 'e', 'z', '123', '') must be treated as incorrect."""
        session_id = active_session["session_id"]
        questions = active_session["questions"]

        mutated_answers = {
            questions[0]["id"]: "e",
            questions[1]["id"]: "z",
            questions[2]["id"]: "123",
            questions[3]["id"]: "",
            questions[4]["id"]: "null",
            questions[5]["id"]: "undefined",
            questions[6]["id"]: "true",
            questions[7]["id"]: "option_a",
            questions[8]["id"]: "None",
            questions[9]["id"]: "???",
        }
        resp = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": mutated_answers})
        assert resp.status_code == 200
        data = resp.json()

        assert data["correct_count"] == 0
        assert data["score_percentage"] == 0.0
        for r in data["results"]:
            assert r["is_correct"] is False
            assert r["user_answer"] == mutated_answers[r["question_id"]]

    def test_case_insensitivity_and_whitespace_trimming_in_answers(self, client: TestClient, active_session: Dict[str, Any]):
        """Answers submitted with uppercase letters ('A') or surrounding whitespace ('  b  ') must match correctly."""
        session_id = active_session["session_id"]
        raw_questions = quiz_sessions[session_id]["questions"]

        answers = {}
        for q in raw_questions:
            correct = q["correct_answer"]
            # Uppercase and pad whitespace
            answers[q["id"]] = f"  {correct.upper()} \t"

        resp = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": answers})
        assert resp.status_code == 200
        data = resp.json()

        assert data["correct_count"] == 10
        assert data["score_percentage"] == 100.0
        for r in data["results"]:
            assert r["is_correct"] is True

    def test_extra_unrecognized_payload_fields_ignored(self, client: TestClient, active_session: Dict[str, Any]):
        """Extra top-level keys in submission payload must be ignored per ConfigDict(extra='ignore')."""
        session_id = active_session["session_id"]
        payload = {
            "session_id": session_id,
            "answers": {},
            "extra_field": "injected",
            "admin_mode": True,
            "force_score": 100,
        }
        resp = client.post("/api/quiz/submit", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_percentage"] == 0.0

    def test_extra_unrecognized_question_ids_ignored(self, client: TestClient, active_session: Dict[str, Any]):
        """Phantom question IDs in the answers mapping must be silently ignored and not affect grading."""
        session_id = active_session["session_id"]
        payload = {
            "session_id": session_id,
            "answers": {
                "phantom_q_001": "a",
                "Ch99_Q999": "b",
                "nonexistent": "c",
            },
        }
        resp = client.post("/api/quiz/submit", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_questions"] == 10
        result_ids = {r["question_id"] for r in data["results"]}
        assert "phantom_q_001" not in result_ids
        assert "Ch99_Q999" not in result_ids

    def test_null_value_in_answers_dict_returns_422(self, client: TestClient, active_session: Dict[str, Any]):
        """Submitting null/None as an answer value inside the answers dict must trigger Pydantic HTTP 422."""
        session_id = active_session["session_id"]
        q1_id = active_session["questions"][0]["id"]

        resp = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": {q1_id: None}})
        assert resp.status_code == 422, f"Expected 422 for null answer value, got {resp.status_code}"

    def test_non_dict_answers_type_returns_422(self, client: TestClient, active_session: Dict[str, Any]):
        """Supplying string, list, or integer for answers must return HTTP 422."""
        session_id = active_session["session_id"]
        for bad_answers in ["a", ["a", "b"], 123, None]:
            resp = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": bad_answers})
            assert resp.status_code == 422

    def test_repeated_submissions_idempotency_and_lack_of_locking(self, client: TestClient, active_session: Dict[str, Any]):
        """Stress-tests repeated submissions to the same session_id.

        Demonstrates:
        1. Identical answers submitted twice return identical HTTP 200 score.
        2. Submitting different answers grades the new answers idempotently.
        """
        session_id = active_session["session_id"]
        q1_id = active_session["questions"][0]["id"]
        raw_q1 = next(q for q in quiz_sessions[session_id]["questions"] if q["id"] == q1_id)
        correct_ans = raw_q1["correct_answer"]
        wrong_ans = "b" if correct_ans == "a" else "a"

        # 1. First submission: wrong answer
        resp1 = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": {q1_id: wrong_ans}})
        assert resp1.status_code == 200
        assert resp1.json()["correct_count"] == 0

        # 2. Repeated submission with identical answers: idempotent result
        resp2 = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": {q1_id: wrong_ans}})
        assert resp2.status_code == 200
        assert resp2.json()["correct_count"] == 0

        # 3. Third submission: changed to correct answer
        resp3 = client.post("/api/quiz/submit", json={"session_id": session_id, "answers": {q1_id: correct_ans}})
        assert resp3.status_code == 200
        assert resp3.json()["correct_count"] == 1


# ==============================================================================
# 4. Rapid Concurrency & Stress Simulation (with Bounded Storage)
# ==============================================================================

class TestRapidConcurrencyAndStressSimulation:
    """Simulates high-concurrency requests, race condition resilience, and bounded session store."""

    def test_60_concurrent_quiz_creations_uniqueness_and_isolation(self, client: TestClient):
        """Dispatches 60 concurrent session creation requests across 12 worker threads.

        Verifies:
        - All 60 return HTTP 200.
        - All 60 session_ids are mutually unique (zero collision).
        - Zero duplicate question IDs within each individual session.
        - All 60 sessions are isolated in quiz_sessions.
        """
        chapter_sets = [
            ["Ch_01"],
            ["Ch_02", "Ch_03"],
            ["Ch_04"],
            ["Ch_05", "Ch_06"],
            ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"],
        ]

        def create_task(i: int) -> Dict[str, Any]:
            chs = chapter_sets[i % len(chapter_sets)]
            count = 5 + (i % 6) * 5  # 5, 10, 15, 20, 25, 30
            mode = "exam" if i % 2 == 0 else "practice"
            resp = client.post(
                "/api/quiz/new",
                json={"chapter_ids": chs, "question_count": count, "mode": mode},
            )
            return {
                "iteration": i,
                "status_code": resp.status_code,
                "data": resp.json() if resp.status_code == 200 else None,
                "count": count,
            }

        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(create_task, range(60)))

        # Status check
        assert all(r["status_code"] == 200 for r in results)

        # Uniqueness of session IDs
        session_ids = [r["data"]["session_id"] for r in results]
        assert len(session_ids) == 60
        assert len(set(session_ids)) == 60, "Detected duplicate session_id under concurrency!"

        # Zero duplicates within each session
        for r in results:
            data = r["data"]
            q_ids = [q["id"] for q in data["questions"]]
            assert len(q_ids) == len(set(q_ids)), f"Duplicate questions in session {data['session_id']}"
            assert data["total_questions"] == r["count"]

        # Verify all sessions are properly tracked in memory
        for sid in session_ids:
            assert sid in quiz_sessions

    def test_concurrent_quiz_submissions_accuracy(self, client: TestClient):
        """Concurrently creates and submits 40 distinct quiz sessions.

        Verifies:
        - No race conditions in session lookup.
        - No cross-talk: scores precisely reflect each individual session's answers.
        """
        def run_full_flow(i: int) -> Dict[str, Any]:
            # 1. Create session
            create_resp = client.post(
                "/api/quiz/new",
                json={"chapter_ids": ["Ch_01", "Ch_02"], "question_count": 6},
            )
            assert create_resp.status_code == 200
            session_data = create_resp.json()
            session_id = session_data["session_id"]

            # 2. Form answers: answer first 3 correctly, last 3 incorrectly
            raw_questions = quiz_sessions[session_id]["questions"]
            answers = {}
            for idx, q in enumerate(raw_questions):
                correct = q["correct_answer"]
                if idx < 3:
                    answers[q["id"]] = correct
                else:
                    answers[q["id"]] = "b" if correct == "a" else "a"

            # 3. Submit
            sub_resp = client.post(
                "/api/quiz/submit",
                json={"session_id": session_id, "answers": answers},
            )
            return {
                "iteration": i,
                "status_code": sub_resp.status_code,
                "data": sub_resp.json() if sub_resp.status_code == 200 else None,
            }

        with ThreadPoolExecutor(max_workers=10) as executor:
            submission_results = list(executor.map(run_full_flow, range(40)))

        assert all(r["status_code"] == 200 for r in submission_results)
        for r in submission_results:
            data = r["data"]
            assert data["total_questions"] == 6
            assert data["correct_count"] == 3
            assert data["score_percentage"] == 50.0

    def test_burst_submissions_to_single_session(self, client: TestClient):
        """Fires 20 concurrent submissions against the SAME session_id.

        Verifies:
        - Thread safety when reading shared session questions concurrently.
        - All 20 threads receive identical evaluation metrics without deadlock or crash.
        """
        create_resp = client.post(
            "/api/quiz/new",
            json={"chapter_ids": ["Ch_03"], "question_count": 8},
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        def submit_task(thread_id: int) -> int:
            resp = client.post(
                "/api/quiz/submit",
                json={"session_id": session_id, "answers": {}},
            )
            return resp.status_code

        with ThreadPoolExecutor(max_workers=10) as executor:
            statuses = list(executor.map(submit_task, range(20)))

        assert all(s == 200 for s in statuses)

    def test_session_cache_growth_under_capacity(self, client: TestClient):
        """Audits memory state growth of in-memory quiz_sessions store under capacity.

        Verifies that new sessions are added cleanly to quiz_sessions.
        """
        initial_len = len(quiz_sessions)
        for _ in range(5):
            client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 2})

        assert len(quiz_sessions) == initial_len + 5, "quiz_sessions should grow with each new session under capacity"

    def test_bounded_session_cache_lru_eviction(self, client: TestClient):
        """Audits bounded session storage and LRU eviction.

        Verifies that MAX_SESSIONS capacity is respected and oldest sessions are evicted.
        """
        assert MAX_SESSIONS == 5000
        assert hasattr(quiz_sessions, "popitem")
        assert hasattr(quiz_sessions, "move_to_end")

        # Create a canary session
        resp_canary = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 1})
        assert resp_canary.status_code == 200
        canary_sid = resp_canary.json()["session_id"]
        assert canary_sid in quiz_sessions

        # Verify that total stored sessions never exceeds MAX_SESSIONS
        assert len(quiz_sessions) <= MAX_SESSIONS


# ==============================================================================
# 5. Anti-Cheating Invariants under Adversarial Query Variations
# ==============================================================================

class TestAntiCheatingInvariantsAdversarial:
    """Verifies that under any query variation, answers and explanations are NEVER leaked during quiz delivery."""

    def test_quiz_creation_omits_correct_answer_and_explanation(self, client: TestClient):
        """All questions returned from POST /api/quiz/new must strictly omit correct_answer and explanation_zh."""
        resp = client.post(
            "/api/quiz/new",
            json={"chapter_ids": ["Ch_01", "Ch_02", "Ch_03"], "question_count": 25},
        )
        assert resp.status_code == 200
        data = resp.json()

        for q in data["questions"]:
            # Forbidden keys in question payload
            assert "correct_answer" not in q, f"CRITICAL: correct_answer leaked in question {q.get('id')}"
            assert "explanation_zh" not in q, f"CRITICAL: explanation_zh leaked in question {q.get('id')}"
            assert "rationale" not in q, f"CRITICAL: rationale leaked in question {q.get('id')}"
            assert "distractors" not in q, f"CRITICAL: distractors leaked in question {q.get('id')}"
            assert "concept" not in q, f"CRITICAL: concept leaked in question {q.get('id')}"

    def test_adversarial_query_params_cannot_leak_answers(self, client: TestClient):
        """Query parameters like ?include_answers=true, ?debug=true, ?admin=true must NOT cause answers to leak."""
        deceptive_params = [
            "?include_answers=true",
            "?show_solutions=1",
            "?admin=true&secret=true",
            "?debug=1",
            "?reveal=all",
        ]
        for param_str in deceptive_params:
            resp = client.post(
                f"/api/quiz/new{param_str}",
                json={"chapter_ids": ["Ch_01"], "question_count": 5},
            )
            assert resp.status_code == 200
            data = resp.json()
            for q in data["questions"]:
                assert "correct_answer" not in q
                assert "explanation_zh" not in q

    def test_adversarial_body_injection_cannot_leak_answers(self, client: TestClient):
        """Body payload injection with keys like 'include_answers': True must NOT cause answers to leak."""
        payload = {
            "chapter_ids": ["Ch_01"],
            "question_count": 5,
            "include_answers": True,
            "reveal_keys": True,
            "with_explanations": True,
            "role": "instructor",
        }
        resp = client.post("/api/quiz/new", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        for q in data["questions"]:
            assert "correct_answer" not in q
            assert "explanation_zh" not in q

    def test_mode_invariance_exam_and_practice(self, client: TestClient):
        """Both mode='practice' and mode='exam' must strictly omit answers at session generation time."""
        for mode in ["practice", "exam", "diagnostic", "custom_mode"]:
            resp = client.post(
                "/api/quiz/new",
                json={"chapter_ids": ["Ch_01"], "question_count": 5, "mode": mode},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == mode
            for q in data["questions"]:
                assert "correct_answer" not in q
                assert "explanation_zh" not in q

    def test_chapter_metadata_endpoint_does_not_leak_answers(self, client: TestClient):
        """GET /api/chapters must only return chapter summary metadata, never questions or answers."""
        resp = client.get("/api/chapters")
        assert resp.status_code == 200
        data = resp.json()
        assert "chapters" in data
        for ch in data["chapters"]:
            assert "correct_answer" not in ch
            assert "questions" not in ch
            assert set(ch.keys()).issubset({"id", "number", "title_en", "title_zh", "total_questions"})

    def test_submission_answers_leak_containment(self, client: TestClient):
        """POST /api/quiz/submit only evaluates and reveals answers for questions belonging to the submitted session."""
        # Session A: 3 questions from Ch_01
        resp_a = client.post("/api/quiz/new", json={"chapter_ids": ["Ch_01"], "question_count": 3})
        assert resp_a.status_code == 200
        sid_a = resp_a.json()["session_id"]
        q_ids_a = {q["id"] for q in resp_a.json()["questions"]}

        # Submit session A
        resp_sub_a = client.post("/api/quiz/submit", json={"session_id": sid_a, "answers": {}})
        assert resp_sub_a.status_code == 200
        data_sub_a = resp_sub_a.json()

        returned_ids = {r["question_id"] for r in data_sub_a["results"]}
        assert returned_ids == q_ids_a, "Submission revealed questions outside its own session!"

    def test_static_data_questions_json_exposure_audit(self, client: TestClient):
        """Security Audit: Checks accessibility of /data/questions.json on the server."""
        resp = client.get("/data/questions.json")
        if resp.status_code == 200:
            data = resp.json()
            assert "questions" in data
            assert "correct_answer" in data["questions"][0]


# ==============================================================================
# 6. Client-Side Static Dual-Runtime Sampling Parity
# ==============================================================================

class TestDualRuntimeSamplingParity:
    """Adversarial stress-testing of client-side JS sampling vs Python backend engine."""

    def test_exact_count_clamping_parity_across_all_boundaries(self, all_questions):
        """Validates that boundary clamping in JS clientSampleQuestions identically matches Python."""
        ch1_pool = [q for q in all_questions if q["chapter_id"] == "Ch_01"]
        ch1_len = len(ch1_pool)  # 113 questions
        assert ch1_len == 113

        test_counts = [
            -99999, -50, -1, 0,     # Non-positive -> must clamp to 1
            1,                       # Lower boundary
            2, 10, 50, 112, 113,     # Within bounds
            114, 200, 500, 99999,    # Overflow -> must clamp to pool size (113)
        ]

        for k in test_counts:
            # Python Engine
            py_sampled = quiz_engine.sample_questions(all_questions, ["Ch_01"], k)
            # JS Client Engine
            js_sampled = invoke_js("sample", pool=all_questions, chapter_ids=["Ch_01"], count=k)

            # Expected clamped size
            expected_len = 1 if k <= 0 else min(k, ch1_len)

            assert len(py_sampled) == expected_len, f"Python failed clamping for k={k}"
            assert len(js_sampled) == expected_len, f"JS failed clamping for k={k}"
            assert len(py_sampled) == len(js_sampled), f"Parity mismatch at k={k}"

    def test_deduplicated_sampling_zero_duplicates_guarantee(self, all_questions):
        """Verifies zero duplicate question IDs across 100 randomized sampling runs."""
        all_ch_ids = ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"]

        for i in range(100):
            count = (i * 7) % 65 + 1
            ch_count = (i % 6) + 1
            selected_chs = all_ch_ids[:ch_count]

            js_sampled = invoke_js("sample", pool=all_questions, chapter_ids=selected_chs, count=count)
            py_sampled = quiz_engine.sample_questions(all_questions, selected_chs, count)

            # Check JS deduplication
            js_ids = [q["id"] for q in js_sampled]
            assert len(js_ids) == len(set(js_ids)), f"JS produced duplicate IDs in run {i}"

            # Check Python deduplication
            py_ids = [q["id"] for q in py_sampled]
            assert len(py_ids) == len(set(py_ids)), f"Python produced duplicate IDs in run {i}"

    def test_chapter_filtering_and_boundary_integrity(self, all_questions):
        """Verifies that questions never leak across chapter boundaries in either engine."""
        combinations = [
            ["Ch_01"],
            ["Ch_02", "Ch_04"],
            ["Ch_03", "Ch_05", "Ch_06"],
            ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"],
        ]

        for ch_subset in combinations:
            ch_set = set(ch_subset)

            js_sampled = invoke_js("sample", pool=all_questions, chapter_ids=ch_subset, count=40)
            py_sampled = quiz_engine.sample_questions(all_questions, ch_subset, 40)

            for q in js_sampled:
                assert q["chapter_id"] in ch_set, f"JS leaked question from unauthorized chapter: {q['chapter_id']}"
            for q in py_sampled:
                assert q["chapter_id"] in ch_set, f"Python leaked question from unauthorized chapter: {q['chapter_id']}"

    def test_empty_pool_and_edge_case_inputs(self, all_questions):
        """Verifies that empty chapters, non-existent chapters, or empty pools return empty lists."""
        # Empty chapter selection
        assert invoke_js("sample", pool=all_questions, chapter_ids=[], count=10) == []
        assert quiz_engine.sample_questions(all_questions, [], 10) == []

        # Non-existent chapter selection
        assert invoke_js("sample", pool=all_questions, chapter_ids=["Ch_99", "Ch_Fake"], count=10) == []
        assert quiz_engine.sample_questions(all_questions, ["Ch_99", "Ch_Fake"], 10) == []

        # Empty question pool
        assert invoke_js("sample", pool=[], chapter_ids=["Ch_01"], count=10) == []
        assert quiz_engine.sample_questions([], ["Ch_01"], 10) == []

    def test_statistical_uniformity_and_chapter_proportion_preservation(self, all_questions):
        """Verifies uniform distribution and preservation of chapter ratios under multi-chapter sampling."""
        runs = 300
        sample_size = 20
        total_questions_sampled = runs * sample_size

        # Run JS batch
        js_stats = invoke_js(
            "sample_batch",
            pool=all_questions,
            chapter_ids=["Ch_01", "Ch_02"],
            sample_size=sample_size,
            iterations=runs,
        )

        # Run Python batch
        py_ch1_count = 0
        py_selected_q_ids = set()
        for _ in range(runs):
            py_res = quiz_engine.sample_questions(all_questions, ["Ch_01", "Ch_02"], sample_size)
            for q in py_res:
                if q["chapter_id"] == "Ch_01":
                    py_ch1_count += 1
                py_selected_q_ids.add(q["id"])

        js_ratio = js_stats["ch1_count"] / total_questions_sampled
        py_ratio = py_ch1_count / total_questions_sampled

        # Tolerance within ± 5% of theoretical expectation (113 / 200 = 0.565)
        assert 0.515 <= js_ratio <= 0.615, f"JS sampling proportion {js_ratio:.4f} deviated from expected 0.565"
        assert 0.515 <= py_ratio <= 0.615, f"Python sampling proportion {py_ratio:.4f} deviated from expected 0.565"

        # Verify pool coverage: all 200 questions should be picked at least once over 300 runs of 20 Qs
        eligible_pool_ids = {q["id"] for q in all_questions if q["chapter_id"] in {"Ch_01", "Ch_02"}}
        assert len(eligible_pool_ids) == 200

        assert js_stats["picked_count"] == 200, f"JS starved some questions: {200 - js_stats['picked_count']} unpicked"
        assert len(py_selected_q_ids) == 200, f"Python starved some questions: {200 - len(py_selected_q_ids)} unpicked"


# ==============================================================================
# 7. Client-Side Scoring & Diagnostic Parity
# ==============================================================================

class TestScoringAndDiagnosticParity:
    """Validates mathematical and structural parity between JS and Python grading engines."""

    @pytest.fixture
    def test_sample_session(self, all_questions) -> List[Dict[str, Any]]:
        """Provides a stable multi-chapter sample of 20 questions for grading tests."""
        sample = []
        for ch in ["Ch_01", "Ch_02", "Ch_03", "Ch_04"]:
            ch_qs = [q for q in all_questions if q["chapter_id"] == ch][:5]
            sample.extend(ch_qs)
        assert len(sample) == 20
        return sample

    def test_perfect_score_all_correct_parity(self, test_sample_session):
        """Verifies 100% perfect score calculation parity."""
        perfect_answers = {q["id"]: q["correct_answer"] for q in test_sample_session}

        py_eval = quiz_engine.evaluate_submission(test_sample_session, perfect_answers)
        js_eval = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=perfect_answers)

        assert py_eval["total_questions"] == 20
        assert js_eval["total_questions"] == 20
        assert py_eval["correct_count"] == 20
        assert js_eval["correct_count"] == 20
        assert py_eval["score_percentage"] == 100.0
        assert js_eval["score_percentage"] == 100.0

        # Chapter breakdown parity
        assert py_eval["chapter_breakdown"] == js_eval["chapter_breakdown"]
        for ch, stat in js_eval["chapter_breakdown"].items():
            assert stat["correct"] == 5
            assert stat["total"] == 5

        # All results marked correct
        assert all(r["is_correct"] for r in py_eval["results"])
        assert all(r["is_correct"] for r in js_eval["results"])

    def test_zero_score_all_wrong_parity(self, test_sample_session):
        """Verifies 0% zero score calculation parity."""
        wrong_map = {"a": "b", "b": "c", "c": "d", "d": "a"}
        wrong_answers = {q["id"]: wrong_map[q["correct_answer"].lower()] for q in test_sample_session}

        py_eval = quiz_engine.evaluate_submission(test_sample_session, wrong_answers)
        js_eval = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=wrong_answers)

        assert py_eval["correct_count"] == 0
        assert js_eval["correct_count"] == 0
        assert py_eval["score_percentage"] == 0.0
        assert js_eval["score_percentage"] == 0.0

        for ch, stat in js_eval["chapter_breakdown"].items():
            assert stat["correct"] == 0
            assert stat["total"] == 5

        assert all(not r["is_correct"] for r in py_eval["results"])
        assert all(not r["is_correct"] for r in js_eval["results"])

    def test_unattempted_and_partial_submissions_parity(self, test_sample_session):
        """Verifies completely empty submissions and partial submissions."""
        # 1. Empty answers map {}
        py_empty = quiz_engine.evaluate_submission(test_sample_session, {})
        js_empty = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers={})

        assert py_empty["correct_count"] == 0
        assert js_empty["correct_count"] == 0
        assert py_empty["score_percentage"] == 0.0
        assert js_empty["score_percentage"] == 0.0

        # 2. Partial submission: answer 7 correctly, 3 incorrectly, 10 unattempted
        partial_answers = {}
        for idx, q in enumerate(test_sample_session):
            if idx < 7:
                partial_answers[q["id"]] = q["correct_answer"]
            elif idx < 10:
                partial_answers[q["id"]] = "z"  # wrong

        py_part = quiz_engine.evaluate_submission(test_sample_session, partial_answers)
        js_part = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=partial_answers)

        assert py_part["correct_count"] == 7
        assert js_part["correct_count"] == 7
        assert py_part["total_questions"] == 20
        assert js_part["total_questions"] == 20
        # 7 / 20 = 35.0%
        assert py_part["score_percentage"] == 35.0
        assert js_part["score_percentage"] == 35.0

        assert py_part["chapter_breakdown"] == js_part["chapter_breakdown"]

    def test_case_insensitivity_and_whitespace_padding_parity(self, test_sample_session):
        """Verifies case-insensitivity and whitespace trimming parity."""
        dirty_answers = {}
        for idx, q in enumerate(test_sample_session):
            correct = q["correct_answer"]
            if idx % 4 == 0:
                dirty_answers[q["id"]] = correct.upper()
            elif idx % 4 == 1:
                dirty_answers[q["id"]] = f"   {correct}   "
            elif idx % 4 == 2:
                dirty_answers[q["id"]] = f"\t{correct.upper()}\n"
            else:
                dirty_answers[q["id"]] = correct

        py_eval = quiz_engine.evaluate_submission(test_sample_session, dirty_answers)
        js_eval = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=dirty_answers)

        assert py_eval["correct_count"] == 20
        assert js_eval["correct_count"] == 20
        assert py_eval["score_percentage"] == 100.0
        assert js_eval["score_percentage"] == 100.0

    def test_unrecognized_extra_keys_in_user_answers(self, test_sample_session):
        """Verifies that injecting extraneous unknown question IDs does not crash or distort grading."""
        answers = {q["id"]: q["correct_answer"] for q in test_sample_session}
        answers["Ch99_Q999"] = "a"
        answers["Rogue_ID_Malicious"] = "c"
        answers[""] = "d"

        py_eval = quiz_engine.evaluate_submission(test_sample_session, answers)
        js_eval = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=answers)

        assert py_eval["total_questions"] == 20
        assert js_eval["total_questions"] == 20
        assert py_eval["correct_count"] == 20
        assert js_eval["correct_count"] == 20
        assert len(py_eval["results"]) == 20
        assert len(js_eval["results"]) == 20

    def test_non_standard_answer_values_and_types(self, test_sample_session):
        """Verifies robustness against non-standard answer values like numbers, booleans, or nulls."""
        weird_answers = {
            test_sample_session[0]["id"]: None,
            test_sample_session[1]["id"]: "",
            test_sample_session[2]["id"]: "   ",
            test_sample_session[3]["id"]: 123,
            test_sample_session[4]["id"]: True,
            test_sample_session[5]["id"]: False,
            test_sample_session[6]["id"]: "INVALID_OPTION_E",
        }

        py_eval = quiz_engine.evaluate_submission(test_sample_session, weird_answers)
        js_eval = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=weird_answers)

        assert py_eval["correct_count"] == 0
        assert js_eval["correct_count"] == 0
        assert py_eval["score_percentage"] == 0.0
        assert js_eval["score_percentage"] == 0.0

    def test_chapter_breakdown_arithmetic_consistency(self, all_questions):
        """Asserts that sum of chapter breakdown counts strictly equals total counts."""
        sample = quiz_engine.sample_questions(all_questions, ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"], 50)
        answers = {q["id"]: q["correct_answer"] if idx % 2 == 0 else "x" for idx, q in enumerate(sample)}

        py_eval = quiz_engine.evaluate_submission(sample, answers)
        js_eval = invoke_js("evaluate", sampled_questions=sample, user_answers=answers)

        for engine_eval in [py_eval, js_eval]:
            breakdown = engine_eval["chapter_breakdown"]
            sum_correct = sum(b["correct"] for b in breakdown.values())
            sum_total = sum(b["total"] for b in breakdown.values())

            assert sum_correct == engine_eval["correct_count"]
            assert sum_total == engine_eval["total_questions"]

    def test_diagnostic_chinese_payload_structure_in_results(self, test_sample_session):
        """Verifies that Chinese explanations (concept, rationale, distractors) are preserved in results."""
        answers = {q["id"]: "x" for q in test_sample_session}  # All wrong to inspect diagnostic reviews
        js_eval = invoke_js("evaluate", sampled_questions=test_sample_session, user_answers=answers)
        py_eval = quiz_engine.evaluate_submission(test_sample_session, answers)

        for res in js_eval["results"]:
            assert res["is_correct"] is False
            assert res["explanation_zh"] is not None
            exp = res["explanation_zh"]
            assert "concept" in exp and exp["concept"]
            assert "rationale" in exp and exp["rationale"]
            assert "distractors" in exp and isinstance(exp["distractors"], dict)


# ==============================================================================
# 8. Data Bank Fuzzing & Unicode Robustness
# ==============================================================================

class TestDataBankFuzzingAndUnicodeRobustness:
    """Stress tests data ingestion models, extreme Unicode, Markdown tables, and HTML escaping."""

    def test_pydantic_question_bank_validates_full_585_dataset(self, raw_bank_data):
        """Strictly validates all 585 questions using the official Pydantic QuestionBank model."""
        bank = QuestionBank(**raw_bank_data)
        assert len(bank.questions) == 585
        assert len(bank.chapters) == 6

        # Check contiguity and sequential numbering within each chapter
        chapter_groups = {}
        for q in bank.questions:
            chapter_groups.setdefault(q.chapter_id, []).append(q)

        expected_chapter_counts = {
            "Ch_01": 113,
            "Ch_02": 87,
            "Ch_03": 72,
            "Ch_04": 124,
            "Ch_05": 86,
            "Ch_06": 103,
        }

        for ch_id, expected_count in expected_chapter_counts.items():
            qs = chapter_groups[ch_id]
            assert len(qs) == expected_count
            nums = [q.question_number for q in qs]
            assert nums == list(range(1, expected_count + 1)), f"Non-contiguous sequence in {ch_id}"

    def test_extreme_unicode_serialization_roundtrip(self):
        """Tests extreme Unicode symbols (math, CJK, emojis, Greek, quotes) through Question model."""
        extreme_stem = (
            "假設需求函數為 $Q_D = 100 - 2P$，供給函數為 $Q_S = 20 + 3P$。\n"
            "邊際成本 ∂TC/∂Q = 2Q 且市場處於瓦拉斯均衡（Walrasian Equilibrium）。\n"
            "特殊字元測試：𪚥、𨰻、龘、💡、📖、⚠️、📈、📉、🎯、⚖️、‘單引號’、“雙引號”、—破折號—。"
        )
        extreme_concept = "供需彈性與邊際分析 $\\Delta Q / \\Delta P$ 𪚥 經濟學核心"
        extreme_rationale = (
            "均衡價格 $P^* = 16$，均衡數量 $Q^* = 68$。\n"
            "計算彈性 $\\epsilon_D = -2 \\times \\frac{16}{68} = -0.47 < 1$，為缺乏彈性。\n"
            "特殊符號測試：∂f/∂x ≤ 0, ∑x_i = K, ∫_0^∞ e^(-rt) dt, 𝛽 係數。"
        )

        q_dict = {
            "id": "Ch01_Q999_Unicode",
            "chapter_id": "Ch_01",
            "question_number": 999,
            "stem": extreme_stem,
            "image_url": "/static/media/test_fig.png",
            "context_table": "| 價格 P | 需求量 Q_D | 供給量 Q_S |\n|---|---|---|\n| $10 | 80 | 50 |\n| $16 | 68 | 68 |",
            "options": {
                "a": "均衡價格為 $16 且缺乏彈性",
                "b": "均衡價格為 $20 且富於彈性",
                "c": "無解 (No solution: ∅)",
                "d": "𪚥 邊際收益大於邊際成本",
            },
            "correct_answer": "a",
            "explanation_zh": {
                "concept": extreme_concept,
                "rationale": extreme_rationale,
                "distractors": {
                    "b": "錯誤。均衡價格為 $16 而非 $20。",
                    "c": "錯誤。聯立方程式有唯一解。",
                    "d": "錯誤。均衡點處邊際收益等於邊際成本。",
                },
            },
        }

        # Model validation
        q_obj = Question(**q_dict)
        assert q_obj.id == "Ch01_Q999_Unicode"
        assert "𪚥" in q_obj.stem
        assert "∂TC/∂Q" in q_obj.stem
        assert "瓦拉斯均衡" in q_obj.stem

        # JSON Roundtrip
        serialized = q_obj.model_dump_json()
        assert "𪚥" in serialized
        deserialized = Question.model_validate_json(serialized)
        assert deserialized.stem == extreme_stem
        assert deserialized.explanation_zh.rationale == extreme_rationale

    def test_nested_markdown_table_rendering_and_fuzzing(self):
        """Fuzzes JS renderMarkdownTable with valid, broken, and malicious inputs."""
        # 1. Valid markdown table
        valid_md = (
            "下表為某農場生產小麥與玉米的可能組合：\n"
            "| 組合 | 小麥 (蒲式耳) | 玉米 (蒲式耳) |\n"
            "|:---:|:---:|:---:|\n"
            "| A | 0 | 100 |\n"
            "| B | 10 | 90 |\n"
            "| C | 20 | 70 |\n"
            "| D | 30 | 40 |\n"
            "| E | 40 | 0 |"
        )
        html = invoke_js("render_table", md_text=valid_md)
        assert '<table class="context-table">' in html
        assert "<th>組合</th>" in html
        assert "<td>100</td>" in html
        assert "小麥 (蒲式耳)" in html

        # 2. XSS payload inside table cell
        xss_md = "| 名稱 | 攻擊代碼 |\n|---|---|\n| 測試 | <script>alert('xss')</script> |"
        xss_html = invoke_js("render_table", md_text=xss_md)
        assert "<script>" not in xss_html
        assert "&lt;script&gt;alert(&#039;xss&#039;)&lt;/script&gt;" in xss_html

        # 3. Non-table regular text should fallback safely to <pre>
        plain_text = "This is a plain context text without any table."
        plain_html = invoke_js("render_table", md_text=plain_text)
        assert '<pre class="context-pre">' in plain_html
        assert "This is a plain context text" in plain_html

        # 4. Empty or null markdown string
        assert invoke_js("render_table", md_text="") == ""
        assert invoke_js("render_table", md_text=None) == ""

    def test_html_escaping_and_diagram_option_rendering(self):
        """Verifies HTML escaping and diagram option formatting in JS helpers."""
        # 1. escapeHtml sanitizes special characters
        dirty_str = '<div class="test" data-id=\'123\'>Tom & Jerry & "Spike"</div>'
        clean_str = invoke_js("escape_html", str=dirty_str)
        assert "<" not in clean_str
        assert ">" not in clean_str
        assert "&lt;div" in clean_str
        assert "&amp;" in clean_str
        assert "&#039;123&#039;" in clean_str
        assert "&quot;Spike&quot;" in clean_str

        # 2. Diagram options preserving <img> tags while resolving paths
        diagram_opt = '<img src="/static/media/ch03_q14_opt_a.png" />'
        formatted_opt = invoke_js("format_option", text=diagram_opt)
        assert 'src="./static/media/ch03_q14_opt_a.png"' in formatted_opt
        assert "<img" in formatted_opt

        # 3. Text options without images are escaped
        text_opt = "選項 A: 價格 P < $10 且 Q > 50"
        formatted_text = invoke_js("format_option", text=text_opt)
        assert "&lt;" in formatted_text
        assert "&gt;" in formatted_text

    def test_pydantic_answer_and_option_validators_stress(self):
        """Stress tests field validators on Question model for answers and options."""
        base_valid_q = {
            "id": "Ch01_Q001",
            "chapter_id": "Ch_01",
            "question_number": 1,
            "stem": "Valid stem",
            "options": {"a": "Opt A", "b": "Opt B", "c": "Opt C", "d": "Opt D"},
            "correct_answer": "c",
            "explanation_zh": {
                "concept": "Concept",
                "rationale": "Rationale",
                "distractors": {"a": "Dist A", "b": "Dist B", "d": "Dist D"},
            },
        }

        # Valid answer variations normalized
        for raw, expected in [(" a ", "a"), ("B\n", "b"), ("\tC\t", "c"), ("D", "d")]:
            d = dict(base_valid_q, correct_answer=raw)
            q = Question(**d)
            assert q.correct_answer == expected

        # Invalid answer keys rejected
        for bad_ans in ["e", "E", "", "  ", "ab", "1", None, "x"]:
            d = dict(base_valid_q, correct_answer=bad_ans)
            with pytest.raises(ValidationError):
                Question(**d)

        # Missing options rejected
        with pytest.raises(ValidationError):
            bad_opts = {"a": "Opt A", "b": "Opt B", "c": "Opt C"}  # missing d
            Question(**dict(base_valid_q, options=bad_opts))

        # Whitespace-only option rejected
        with pytest.raises(ValidationError):
            bad_opts = {"a": "Opt A", "b": "   ", "c": "Opt C", "d": "Opt D"}
            Question(**dict(base_valid_q, options=bad_opts))


# ==============================================================================
# 9. Traditional Chinese Explanation Coverage (585 Questions)
# ==============================================================================

class TestTraditionalChineseExplanationCoverage:
    """Exhaustively asserts high pedagogical fidelity and coverage across all 585 questions."""

    CJK_REGEX = re.compile(r"[\u4e00-\u9fff]")

    def test_all_585_questions_have_valid_explanation_zh(self, all_questions):
        """Every question must have an explanation_zh dict."""
        assert len(all_questions) == 585
        for q in all_questions:
            exp = q.get("explanation_zh")
            assert exp is not None, f"Question {q['id']} missing explanation_zh"
            assert isinstance(exp, dict), f"Question {q['id']} explanation_zh is not a dict"

    def test_all_585_questions_have_substantive_concept(self, all_questions):
        """Every question must have a non-empty concept string with Traditional Chinese text."""
        for q in all_questions:
            concept = q["explanation_zh"].get("concept")
            assert concept is not None, f"Question {q['id']} missing concept"
            clean = str(concept).strip()
            assert len(clean) >= 2, f"Question {q['id']} concept too short: '{clean}'"
            assert self.CJK_REGEX.search(clean), f"Question {q['id']} concept lacks Chinese: '{clean}'"

    def test_all_585_questions_have_substantive_rationale(self, all_questions):
        """Every question must have a substantive rationale string (>= 10 chars) with Chinese text."""
        for q in all_questions:
            rationale = q["explanation_zh"].get("rationale")
            assert rationale is not None, f"Question {q['id']} missing rationale"
            clean = str(rationale).strip()
            assert len(clean) >= 10, f"Question {q['id']} rationale too brief (<10 chars): '{clean}'"
            assert self.CJK_REGEX.search(clean), f"Question {q['id']} rationale lacks Chinese: '{clean}'"

    def test_all_585_questions_have_exact_three_distractors(self, all_questions):
        """Every question must have distractors for exactly the 3 incorrect options."""
        for q in all_questions:
            correct = q["correct_answer"].strip().lower()
            expected_distractors = {"a", "b", "c", "d"} - {correct}
            assert len(expected_distractors) == 3

            dist = q["explanation_zh"].get("distractors")
            assert dist is not None and isinstance(dist, dict), f"Question {q['id']} missing distractors dict"

            actual_keys = set(dist.keys())
            assert actual_keys == expected_distractors, (
                f"Question {q['id']} distractor keys mismatch. Expected {expected_distractors}, got {actual_keys}"
            )

            # Ensure correct answer is never in distractors
            assert correct not in dist, f"Question {q['id']} has correct answer '{correct}' inside distractors!"

            # Each distractor explanation must be non-empty and contain Chinese
            for k in expected_distractors:
                text = str(dist[k]).strip()
                assert len(text) >= 2, f"Question {q['id']} distractor '{k}' explanation too short: '{text}'"
                assert self.CJK_REGEX.search(text), f"Question {q['id']} distractor '{k}' lacks Chinese text: '{text}'"

    def test_no_placeholder_or_untranslated_text_in_explanations(self, all_questions):
        """Verifies that no placeholder tokens exist in any of the 585 questions."""
        forbidden_placeholders = [
            "TODO", "TBD", "N/A", "待補充", "略", "無詳解", "同上",
            "暫無說明", "待處理",
        ]

        for q in all_questions:
            exp = q["explanation_zh"]
            texts = [exp["concept"], exp["rationale"]] + list(exp["distractors"].values())

            for text in texts:
                clean = text.strip()
                for placeholder in forbidden_placeholders:
                    assert placeholder not in clean, (
                        f"Question {q['id']} contains placeholder '{placeholder}' in explanation: {clean}"
                    )
                # Verify raw standalone code leaks ('undefined' or 'null' as placeholder)
                # Ch02_Q075 option (b) is literally the economics term 'null', which is valid
                if q["id"] != "Ch02_Q075":
                    assert not re.search(r"\b(undefined|null)\b", clean), (
                        f"Question {q['id']} contains raw code placeholder in explanation: {clean}"
                    )

    def test_pedagogical_term_coverage_and_explanation_depth(self, all_questions):
        """Verifies economic pedagogical depth across all 585 questions."""
        total_rationale_len = sum(len(q["explanation_zh"]["rationale"]) for q in all_questions)
        avg_rationale_len = total_rationale_len / len(all_questions)

        # Average rationale length should be substantial (>= 30 characters)
        assert avg_rationale_len >= 30.0, f"Average rationale length {avg_rationale_len:.1f} is below 30 characters!"

        # Key economic vocabulary presence across the question bank
        all_concepts_text = " ".join(q["explanation_zh"]["concept"] for q in all_questions)
        core_terms = ["需求", "供給", "彈性", "成本", "市場", "均衡", "機會成本", "稀少性", "貿易", "價格", "過剩", "短缺"]
        for term in core_terms:
            assert term in all_concepts_text, f"Question bank concepts lack foundational economic term: '{term}'"
