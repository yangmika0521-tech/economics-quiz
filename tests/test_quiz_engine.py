"""
tests/test_quiz_engine.py
Unit & Functional Tests for Deduplicated Random Sampling, Boundary Count Clamping,
Scoring Accuracy, and Diagnostic Result Generation.

Tiers Covered:
- Tier 1: Feature Coverage (Sampling without duplicates, Scoring percentages, Diagnostic payloads)
- Tier 2: Boundary & Corner Cases (Clamping 0/1/max/overflow, 0% vs 100% scores, invalid inputs)

Remediation Notes (Iteration 2):
- Removed all in-test oracle fallback defaults from getattr.
- Directly invokes app.quiz_engine functions when available.
- Decorated with @pytest.mark.skipif(not HAS_QUIZ_ENGINE, ...) to cleanly skip until M2 is implemented.
- Clamping assertions tightened to exact equality (len == 1).
"""

import math
import pytest

# Check whether app.quiz_engine is available
try:
    from app import quiz_engine
    HAS_QUIZ_ENGINE = hasattr(quiz_engine, "sample_questions") and hasattr(quiz_engine, "evaluate_submission")
except (ImportError, ModuleNotFoundError):
    quiz_engine = None
    HAS_QUIZ_ENGINE = False


# ==============================================================================
# Synthetic Question Pool Fixture for Pure Engine Contract Testing
# ==============================================================================

@pytest.fixture
def sample_question_pool():
    """Generates a controlled pool of 30 questions across 3 chapters for deterministic testing."""
    pool = []
    for ch_idx in range(1, 4):
        ch_id = f"Ch_{ch_idx:02d}"
        for q_idx in range(1, 11):
            q_id = f"Ch{ch_idx:02d}_Q{q_idx:03d}"
            correct_ans = ["a", "b", "c", "d"][(q_idx - 1) % 4]
            pool.append({
                "id": q_id,
                "chapter_id": ch_id,
                "question_number": q_idx,
                "stem": f"Economics question {q_idx} for Chapter {ch_idx}",
                "image_url": None,
                "context_table": None,
                "options": {
                    "a": f"Option A for Q{q_idx}",
                    "b": f"Option B for Q{q_idx}",
                    "c": f"Option C for Q{q_idx}",
                    "d": f"Option D for Q{q_idx}",
                },
                "correct_answer": correct_ans,
                "explanation_zh": {
                    "concept": f"核心概念 Ch{ch_idx}",
                    "rationale": f"正確解析：根據經濟學原理，選項 {correct_ans} 為正解。",
                    "distractors": {
                        opt: f"選項 {opt} 不正確。" for opt in ["a", "b", "c", "d"] if opt != correct_ans
                    }
                }
            })
    return pool


# ==============================================================================
# Tier 1: Feature Coverage (Sampling & Scoring Logic)
# ==============================================================================

@pytest.mark.skipif(not HAS_QUIZ_ENGINE, reason="app.quiz_engine not yet available (M2 in progress)")
class TestSamplingFeatureCoverage:
    """Tests deduplicated random sampling behavior across single, multiple, and all chapters."""

    def test_sampling_deduplication_guarantee(self, sample_question_pool):
        """Verify sampled questions contain zero duplicate question IDs."""
        for _ in range(10):
            sampled = quiz_engine.sample_questions(sample_question_pool, ["Ch_01", "Ch_02"], 15)
            q_ids = [q["id"] for q in sampled]
            assert len(q_ids) == len(set(q_ids)), "Sampled questions contain duplicates!"
            assert len(sampled) == 15

    def test_sampling_from_single_chapter(self, sample_question_pool):
        """Verify all sampled questions belong strictly to the selected single chapter."""
        sampled = quiz_engine.sample_questions(sample_question_pool, ["Ch_01"], 8)
        assert len(sampled) == 8
        for q in sampled:
            assert q["chapter_id"] == "Ch_01"

    def test_sampling_from_multiple_chapters(self, sample_question_pool):
        """Verify sampled questions are drawn only from the specified subset of chapters."""
        selected_chs = ["Ch_01", "Ch_03"]
        sampled = quiz_engine.sample_questions(sample_question_pool, selected_chs, 12)
        assert len(sampled) == 12
        for q in sampled:
            assert q["chapter_id"] in selected_chs
            assert q["chapter_id"] != "Ch_02"

    def test_scoring_accuracy_partial_score(self, sample_question_pool):
        """Verify scoring logic calculates correct count and percentage accurately."""
        sampled = sample_question_pool[:10]  # 10 questions
        answers = {}
        for idx, q in enumerate(sampled):
            if idx < 7:
                answers[q["id"]] = q["correct_answer"]
            else:
                wrong_opt = "a" if q["correct_answer"] != "a" else "b"
                answers[q["id"]] = wrong_opt

        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["total_questions"] == 10
        assert result["correct_count"] == 7
        assert math.isclose(result["score_percentage"], 70.0, abs_tol=0.1)

    def test_diagnostic_payload_for_incorrect_answers(self, sample_question_pool):
        """Verify incorrect answers provide user's choice, correct answer, and detailed Chinese explanation."""
        q = sample_question_pool[0]
        wrong_choice = "a" if q["correct_answer"] != "a" else "b"
        answers = {q["id"]: wrong_choice}

        result = quiz_engine.evaluate_submission([q], answers)
        item = result["results"][0]
        assert item["is_correct"] is False
        assert item["user_answer"] == wrong_choice
        assert item["correct_answer"] == q["correct_answer"]
        assert "explanation_zh" in item and item["explanation_zh"] is not None
        assert "concept" in item["explanation_zh"]
        assert "rationale" in item["explanation_zh"]
        assert "distractors" in item["explanation_zh"]


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Clamping, Limits, Extremes)
# ==============================================================================

@pytest.mark.skipif(not HAS_QUIZ_ENGINE, reason="app.quiz_engine not yet available (M2 in progress)")
class TestEngineBoundariesAndCornerCases:
    """Tests extreme parameters, boundary limits, and edge conditions."""

    def test_requested_count_exceeds_pool_size_clamping(self, sample_question_pool):
        """When requested question count exceeds available questions, clamp to pool size without error."""
        # Ch_01 only has 10 questions in this fixture
        sampled = quiz_engine.sample_questions(sample_question_pool, ["Ch_01"], 50)
        assert len(sampled) == 10, f"Expected clamped count 10, got {len(sampled)}"
        q_ids = [q["id"] for q in sampled]
        assert len(q_ids) == len(set(q_ids)), "Deduplication failed during clamping"

    def test_requested_count_of_one(self, sample_question_pool):
        """Boundary count = 1 returns exactly 1 question."""
        sampled = quiz_engine.sample_questions(sample_question_pool, ["Ch_01", "Ch_02"], 1)
        assert len(sampled) == 1

    def test_requested_count_zero_or_negative_clamping(self, sample_question_pool):
        """Boundary count <= 0 should clamp to minimum 1 question."""
        sampled_zero = quiz_engine.sample_questions(sample_question_pool, ["Ch_01"], 0)
        assert len(sampled_zero) == 1, f"Expected clamped count 1, got {len(sampled_zero)}"
        sampled_neg = quiz_engine.sample_questions(sample_question_pool, ["Ch_01"], -10)
        assert len(sampled_neg) == 1, f"Expected clamped count 1, got {len(sampled_neg)}"

    def test_perfect_score_boundary_100_percent(self, sample_question_pool):
        """All answers correct: correct_count == total, score_percentage == 100.0."""
        sampled = sample_question_pool[:5]
        answers = {q["id"]: q["correct_answer"] for q in sampled}
        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["correct_count"] == 5
        assert result["total_questions"] == 5
        assert math.isclose(result["score_percentage"], 100.0, abs_tol=0.01)
        for r in result["results"]:
            assert r["is_correct"] is True

    def test_zero_score_boundary_0_percent(self, sample_question_pool):
        """All answers incorrect: correct_count == 0, score_percentage == 0.0."""
        sampled = sample_question_pool[:5]
        answers = {
            q["id"]: ("a" if q["correct_answer"] != "a" else "b")
            for q in sampled
        }
        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["correct_count"] == 0
        assert result["total_questions"] == 5
        assert math.isclose(result["score_percentage"], 0.0, abs_tol=0.01)
        for r in result["results"]:
            assert r["is_correct"] is False

    def test_empty_chapter_selection_handling(self, sample_question_pool):
        """Empty chapter list returns empty list or raises ValueError without unhandled crash."""
        try:
            sampled = quiz_engine.sample_questions(sample_question_pool, [], 10)
            assert len(sampled) == 0
        except ValueError:
            pass  # Raising ValueError on empty chapter selection is also valid

    def test_unanswered_questions_in_submission(self, sample_question_pool):
        """Submitting partial answers treats unattempted questions as incorrect."""
        sampled = sample_question_pool[:4]
        # Only answer 2 out of 4 questions
        answers = {
            sampled[0]["id"]: sampled[0]["correct_answer"],
            sampled[1]["id"]: sampled[1]["correct_answer"],
        }
        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["total_questions"] == 4
        assert result["correct_count"] == 2
        assert math.isclose(result["score_percentage"], 50.0, abs_tol=0.1)
        assert result["results"][2]["user_answer"] is None
        assert result["results"][2]["is_correct"] is False
