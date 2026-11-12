"""
tests/test_quiz_engine_adversarial.py
Adversarial Stress Test Suite for app/quiz_engine.py.

Designed by Challenger 1 (Milestone 2) to empirically verify:
1. High-iteration sampling deduplication stress test (>=200 iterations with 0 duplicates).
2. Count clamping edge cases (count = 0, count = -100, count = 1, count = exact pool size, count = 10,000 overflow).
3. Chapter filtering combinations (single chapter, pairs, all 6 chapters, empty list, unknown chapter IDs, duplicates).
4. Sampling integrity & Data Preservation (diagram image_url preservation, immutability, field integrity).
5. Scoring engine robustness & adversarial submission payloads (case/whitespace insensitivity, partial answers, schema conformance).
6. Randomness distribution sanity test.
"""

import os
import json
import random
import itertools
from typing import List, Dict, Any
import pytest

from app import quiz_engine
from app.models import Question, QuizResult, Chapter, QuestionBank


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(scope="module")
def real_question_bank() -> Dict[str, Any]:
    """Loads canonical data/questions.json (585 questions)."""
    questions_path = os.path.join(os.path.dirname(__file__), "..", "data", "questions.json")
    with open(questions_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def real_questions(real_question_bank) -> List[Dict[str, Any]]:
    return real_question_bank["questions"]


@pytest.fixture(scope="module")
def real_chapters(real_question_bank) -> List[Dict[str, Any]]:
    return real_question_bank["chapters"]


@pytest.fixture(scope="module")
def pydantic_questions(real_questions) -> List[Question]:
    """Converts raw dict questions into validated Pydantic Question objects."""
    return [Question(**q) for q in real_questions]


# ==============================================================================
# 1. High-Iteration Sampling Deduplication Stress Tests
# ==============================================================================

class TestAdversarialSamplingDeduplication:
    """Stress-tests sampling deduplication under high iteration counts and random parameter sweeps."""

    def test_high_iteration_sampling_deduplication_real_pool(self, real_questions):
        """Runs 300 random iterations across arbitrary chapter subsets and counts.
        Ensures 0 duplicate question IDs ever occur in any sampled session.
        """
        all_ch_ids = [f"Ch_{i:02d}" for i in range(1, 7)]
        random.seed(42)  # Seed for reproducibility while covering 300 iterations

        for iteration in range(300):
            # Select random non-empty subset of chapters (1 to 6 chapters)
            k_chapters = random.randint(1, 6)
            selected_chapters = random.sample(all_ch_ids, k_chapters)

            # Calculate actual available questions for these chapters
            eligible_count = sum(1 for q in real_questions if q["chapter_id"] in selected_chapters)

            # Select random requested count, including boundary and extreme values
            # Ranges from -20 to 800 (overflowing the entire 585 pool)
            requested_count = random.choice([
                -100, -10, 0, 1, 2, 5, 10, 20, 50, 100,
                eligible_count // 2, eligible_count, eligible_count + 1,
                585, 1000, 10000
            ])

            sampled = quiz_engine.sample_questions(real_questions, selected_chapters, requested_count)

            # Deduplication Assertion: 0 duplicate IDs
            q_ids = [q["id"] for q in sampled]
            assert len(q_ids) == len(set(q_ids)), (
                f"Iteration {iteration}: Sampled questions contain duplicates! "
                f"Count={len(q_ids)}, Unique={len(set(q_ids))}"
            )

            # Expected length based on clamping contract:
            expected_count = min(max(requested_count, 1), eligible_count)
            assert len(sampled) == expected_count, (
                f"Iteration {iteration}: Expected clamped count {expected_count}, got {len(sampled)} "
                f"(requested: {requested_count}, eligible: {eligible_count})"
            )

            # Strict chapter association assertion
            for q in sampled:
                assert q["chapter_id"] in selected_chapters, (
                    f"Iteration {iteration}: Question {q['id']} from chapter {q['chapter_id']} "
                    f"was sampled when only {selected_chapters} were requested!"
                )

    def test_deduplication_stress_full_chapters_repeated(self, real_questions):
        """Samples full 585 questions across all 6 chapters 50 times.
        Every run must return exactly 585 unique questions without duplicates.
        """
        all_ch_ids = [f"Ch_{i:02d}" for i in range(1, 7)]

        for i in range(50):
            sampled = quiz_engine.sample_questions(real_questions, all_ch_ids, 585)
            assert len(sampled) == 585, f"Run {i}: Expected 585 questions, got {len(sampled)}"
            q_ids = [q["id"] for q in sampled]
            assert len(set(q_ids)) == 585, f"Run {i}: Deduplication failed on full pool sample!"


# ==============================================================================
# 2. Count Clamping Edge Cases
# ==============================================================================

class TestAdversarialCountClamping:
    """Stress-tests boundary clamping: count <= 0 -> 1, count > pool -> pool size."""

    @pytest.mark.parametrize("non_positive_count", [0, -1, -2, -100, -999999])
    def test_count_zero_and_negative_clamping(self, real_questions, non_positive_count):
        """Any count <= 0 must clamp to exactly 1 question."""
        sampled = quiz_engine.sample_questions(real_questions, ["Ch_01"], non_positive_count)
        assert len(sampled) == 1, (
            f"Requested count {non_positive_count} did not clamp to 1; got {len(sampled)}"
        )
        assert sampled[0]["chapter_id"] == "Ch_01"

    def test_count_exact_one(self, real_questions):
        """Requested count = 1 returns exactly 1 question."""
        sampled = quiz_engine.sample_questions(real_questions, ["Ch_02"], 1)
        assert len(sampled) == 1
        assert sampled[0]["chapter_id"] == "Ch_02"

    @pytest.mark.parametrize("chapter_id,expected_pool_size", [
        ("Ch_01", 113),
        ("Ch_02", 87),
        ("Ch_03", 72),
        ("Ch_04", 124),
        ("Ch_05", 86),
        ("Ch_06", 103),
    ])
    def test_count_exact_pool_size(self, real_questions, chapter_id, expected_pool_size):
        """Requesting exact pool size returns all questions in chapter with 0 duplicates."""
        sampled = quiz_engine.sample_questions(real_questions, [chapter_id], expected_pool_size)
        assert len(sampled) == expected_pool_size
        q_ids = [q["id"] for q in sampled]
        assert len(set(q_ids)) == expected_pool_size
        for q in sampled:
            assert q["chapter_id"] == chapter_id

    @pytest.mark.parametrize("overflow_count", [73, 100, 125, 200, 1000, 10000])
    def test_count_overflow_clamping_single_chapter(self, real_questions, overflow_count):
        """Requested count > chapter pool size clamps to exact pool size without error or duplication."""
        # Ch_03 has exactly 72 questions
        sampled_ch3 = quiz_engine.sample_questions(real_questions, ["Ch_03"], overflow_count)
        assert len(sampled_ch3) == 72, (
            f"Expected Ch_03 overflow to clamp to 72, got {len(sampled_ch3)}"
        )
        assert len(set(q["id"] for q in sampled_ch3)) == 72

    @pytest.mark.parametrize("overflow_count", [586, 600, 1000, 10000, 100000])
    def test_count_overflow_clamping_all_chapters(self, real_questions, overflow_count):
        """Requested count > 585 (all chapters) clamps to 585 without error or duplication."""
        all_chs = [f"Ch_{i:02d}" for i in range(1, 7)]
        sampled_all = quiz_engine.sample_questions(real_questions, all_chs, overflow_count)
        assert len(sampled_all) == 585, (
            f"Expected all-chapters overflow to clamp to 585, got {len(sampled_all)}"
        )
        assert len(set(q["id"] for q in sampled_all)) == 585

    def test_clamping_on_micro_pool(self):
        """Tests clamping logic on small synthetic pools (e.g. pool of size 2)."""
        micro_pool = [
            {"id": "Q1", "chapter_id": "Ch_01"},
            {"id": "Q2", "chapter_id": "Ch_01"}
        ]
        # Count <= 0 clamps to 1
        assert len(quiz_engine.sample_questions(micro_pool, ["Ch_01"], 0)) == 1
        assert len(quiz_engine.sample_questions(micro_pool, ["Ch_01"], -10)) == 1

        # Count 1 returns 1
        assert len(quiz_engine.sample_questions(micro_pool, ["Ch_01"], 1)) == 1

        # Count 2 returns 2
        assert len(quiz_engine.sample_questions(micro_pool, ["Ch_01"], 2)) == 2

        # Count >= 3 clamps to 2
        assert len(quiz_engine.sample_questions(micro_pool, ["Ch_01"], 3)) == 2
        assert len(quiz_engine.sample_questions(micro_pool, ["Ch_01"], 100)) == 2


# ==============================================================================
# 3. Chapter Filtering Combinations
# ==============================================================================

class TestAdversarialChapterFiltering:
    """Stress-tests single, pair, full, empty, duplicate, and unknown chapter inputs."""

    @pytest.mark.parametrize("chapter_id", [f"Ch_{i:02d}" for i in range(1, 7)])
    def test_each_single_chapter_isolated(self, real_questions, chapter_id):
        """Verify sampling from each individual chapter returns strictly that chapter's questions."""
        sampled = quiz_engine.sample_questions(real_questions, [chapter_id], 25)
        assert len(sampled) == 25
        for q in sampled:
            assert q["chapter_id"] == chapter_id

    def test_all_15_chapter_pairs(self, real_questions):
        """Tests all 15 pairwise chapter combinations (6 choose 2)."""
        all_chs = [f"Ch_{i:02d}" for i in range(1, 7)]
        pairs = list(itertools.combinations(all_chs, 2))
        assert len(pairs) == 15

        for ch_a, ch_b in pairs:
            selected = [ch_a, ch_b]
            sampled = quiz_engine.sample_questions(real_questions, selected, 30)
            assert len(sampled) == 30
            for q in sampled:
                assert q["chapter_id"] in selected, (
                    f"Question {q['id']} chapter {q['chapter_id']} not in {selected}"
                )

    def test_empty_chapter_list(self, real_questions):
        """Empty chapter_ids list returns empty list without crashing."""
        sampled = quiz_engine.sample_questions(real_questions, [], 10)
        assert sampled == []

    def test_none_chapter_ids(self, real_questions):
        """chapter_ids = None returns empty list without crashing."""
        sampled = quiz_engine.sample_questions(real_questions, None, 10)
        assert sampled == []

    def test_empty_or_none_pool(self):
        """Empty or None pool returns empty list without crashing."""
        assert quiz_engine.sample_questions([], ["Ch_01"], 5) == []
        assert quiz_engine.sample_questions(None, ["Ch_01"], 5) == []

    def test_unknown_chapter_ids(self, real_questions):
        """Invalid or non-existent chapter IDs return empty list without crashing."""
        invalid_ids = ["Ch_99", "INVALID", "Ch_00", "Chapter1", ""]
        sampled = quiz_engine.sample_questions(real_questions, invalid_ids, 10)
        assert sampled == []

    def test_mixed_valid_and_invalid_chapter_ids(self, real_questions):
        """Mixture of valid and invalid chapter IDs extracts questions from valid chapters only."""
        mixed_ids = ["Ch_01", "Ch_99", "INVALID_XYZ"]
        sampled = quiz_engine.sample_questions(real_questions, mixed_ids, 20)
        assert len(sampled) == 20
        for q in sampled:
            assert q["chapter_id"] == "Ch_01"

    def test_duplicate_chapter_ids_in_input(self, real_questions):
        """Duplicate chapter IDs in input (e.g. ['Ch_01', 'Ch_01']) do not cause duplicate sampling."""
        sampled = quiz_engine.sample_questions(real_questions, ["Ch_01", "Ch_01", "Ch_01"], 30)
        assert len(sampled) == 30
        q_ids = [q["id"] for q in sampled]
        assert len(set(q_ids)) == 30
        for q in sampled:
            assert q["chapter_id"] == "Ch_01"


# ==============================================================================
# 4. Sampling Integrity & Data Preservation
# ==============================================================================

class TestAdversarialSamplingIntegrity:
    """Verifies diagram image_url preservation, question fields integrity, and pool immutability."""

    def test_diagram_image_url_preservation(self, real_questions):
        """Ensures questions with diagrams preserve exact image_url without corruption or loss."""
        # Find all questions in real_questions that have an image_url
        diagram_qs_map = {q["id"]: q["image_url"] for q in real_questions if q.get("image_url")}
        assert len(diagram_qs_map) == 109, f"Expected 109 diagram questions, found {len(diagram_qs_map)}"

        # Sample across chapters known to contain diagrams (Ch_02 to Ch_06)
        chapters_with_diagrams = ["Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"]
        # Sample 100 questions from these chapters
        for _ in range(5):
            sampled = quiz_engine.sample_questions(real_questions, chapters_with_diagrams, 100)
            for q in sampled:
                if q["id"] in diagram_qs_map:
                    expected_url = diagram_qs_map[q["id"]]
                    assert q.get("image_url") == expected_url, (
                        f"Image URL corrupted for question {q['id']}! "
                        f"Expected {expected_url}, got {q.get('image_url')}"
                    )
                    assert q["image_url"].startswith("/static/media/"), (
                        f"Image URL does not point to /static/media/: {q['image_url']}"
                    )

    def test_all_question_fields_preserved_after_sampling(self, real_questions):
        """Verifies that all core fields (stem, options, correct_answer, explanation_zh) remain intact."""
        sampled = quiz_engine.sample_questions(real_questions, ["Ch_01", "Ch_04"], 50)
        for q in sampled:
            assert "id" in q and q["id"].startswith("Ch")
            assert "chapter_id" in q and q["chapter_id"] in ["Ch_01", "Ch_04"]
            assert "question_number" in q and isinstance(q["question_number"], int)
            assert "stem" in q and len(q["stem"]) > 0
            assert "options" in q and len(q["options"]) == 4
            assert set(q["options"].keys()) == {"a", "b", "c", "d"}
            assert q["correct_answer"] in {"a", "b", "c", "d"}
            assert "explanation_zh" in q and q["explanation_zh"] is not None
            assert "concept" in q["explanation_zh"]
            assert "rationale" in q["explanation_zh"]
            assert "distractors" in q["explanation_zh"]

    def test_original_pool_immutability(self, real_questions):
        """Verifies that sample_questions does not mutate or alter the original question pool list."""
        original_ids = [q["id"] for q in real_questions]
        original_len = len(real_questions)

        # Run multiple aggressive samplings
        for _ in range(20):
            quiz_engine.sample_questions(real_questions, ["Ch_01", "Ch_03"], 50)
            quiz_engine.sample_questions(real_questions, ["Ch_02", "Ch_05"], 200)

        # Assert master pool remains completely identical
        assert len(real_questions) == original_len
        current_ids = [q["id"] for q in real_questions]
        assert current_ids == original_ids, "Original question pool order or contents were mutated!"

    def test_pydantic_question_model_objects_support(self, pydantic_questions):
        """Verifies that sample_questions and evaluate_submission work seamlessly with Pydantic model objects."""
        sampled = quiz_engine.sample_questions(pydantic_questions, ["Ch_01", "Ch_02"], 15)
        assert len(sampled) == 15
        for q in sampled:
            assert isinstance(q, Question)
            assert q.chapter_id in ["Ch_01", "Ch_02"]

        # Test evaluation with Pydantic objects
        answers = {q.id: q.correct_answer for q in sampled}
        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["total_questions"] == 15
        assert result["correct_count"] == 15
        assert result["score_percentage"] == 100.0


# ==============================================================================
# 5. Scoring Engine Adversarial & Robustness Tests
# ==============================================================================

class TestAdversarialScoringAndEvaluation:
    """Stress-tests evaluate_submission with boundary conditions and messy inputs."""

    def test_empty_submission(self):
        """Empty sampled questions list returns total=0, score=0.0 without divide-by-zero error."""
        result = quiz_engine.evaluate_submission([], {})
        assert result["total_questions"] == 0
        assert result["correct_count"] == 0
        assert result["score_percentage"] == 0.0
        assert result["chapter_breakdown"] == {}
        assert result["results"] == []

    def test_none_user_answers(self, real_questions):
        """Passing user_answers=None does not crash and marks all questions incorrect."""
        sampled = real_questions[:10]
        result = quiz_engine.evaluate_submission(sampled, None)
        assert result["total_questions"] == 10
        assert result["correct_count"] == 0
        assert result["score_percentage"] == 0.0
        for item in result["results"]:
            assert item["is_correct"] is False
            assert item["user_answer"] is None

    def test_case_and_whitespace_insensitivity(self, real_questions):
        """Answers submitted with uppercase letters or leading/trailing whitespace evaluate correctly."""
        sampled = real_questions[:4]
        # Craft answers with uppercase and whitespace: "  A  ", " B\n", "\tc ", " D "
        answers = {
            sampled[0]["id"]: f"  {sampled[0]['correct_answer'].upper()}  ",
            sampled[1]["id"]: f"{sampled[1]['correct_answer'].upper()}\n",
            sampled[2]["id"]: f"\t{sampled[2]['correct_answer']} ",
            sampled[3]["id"]: sampled[3]["correct_answer"].upper(),
        }
        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["total_questions"] == 4
        assert result["correct_count"] == 4
        assert result["score_percentage"] == 100.0

    def test_bogus_and_unorthodox_answers(self, real_questions):
        """Non-standard inputs ('z', 123, True, '', 'xyz') evaluate as incorrect without crashing."""
        sampled = real_questions[:5]
        answers = {
            sampled[0]["id"]: "z",
            sampled[1]["id"]: "",
            sampled[2]["id"]: "True",
            sampled[3]["id"]: 123,
            sampled[4]["id"]: None,
        }
        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["total_questions"] == 5
        assert result["correct_count"] == 0
        assert result["score_percentage"] == 0.0

    def test_partial_answers_with_sparse_keys(self, real_questions):
        """Out of 20 questions, answer only 5 correctly, 5 incorrectly, leave 10 unanswered."""
        sampled = real_questions[:20]
        answers = {}
        # First 5 correct
        for q in sampled[:5]:
            answers[q["id"]] = q["correct_answer"]
        # Next 5 wrong
        for q in sampled[5:10]:
            answers[q["id"]] = "a" if q["correct_answer"] != "a" else "b"
        # Remaining 10 unanswered (not present in answers dict)

        result = quiz_engine.evaluate_submission(sampled, answers)
        assert result["total_questions"] == 20
        assert result["correct_count"] == 5
        assert result["score_percentage"] == 25.0

        # Verify unanswered diagnostic entries
        for idx in range(10, 20):
            item = result["results"][idx]
            assert item["user_answer"] is None
            assert item["is_correct"] is False

    def test_chapter_breakdown_arithmetic_consistency(self, real_questions):
        """Verifies chapter_breakdown totals and correct counts sum exactly to grand totals."""
        all_chs = [f"Ch_{i:02d}" for i in range(1, 7)]
        sampled = quiz_engine.sample_questions(real_questions, all_chs, 60)

        # Randomize answers: 50% chance of correct answer
        random.seed(123)
        answers = {}
        for q in sampled:
            if random.random() < 0.6:
                answers[q["id"]] = q["correct_answer"]
            else:
                answers[q["id"]] = "a" if q["correct_answer"] != "a" else "b"

        result = quiz_engine.evaluate_submission(sampled, answers)

        # Check breakdown consistency
        breakdown = result["chapter_breakdown"]
        sum_total = sum(ch["total"] for ch in breakdown.values())
        sum_correct = sum(ch["correct"] for ch in breakdown.values())

        assert sum_total == result["total_questions"] == 60
        assert sum_correct == result["correct_count"]

    def test_quiz_result_pydantic_schema_conformance(self, real_questions):
        """Validates that evaluate_submission result matches Pydantic QuizResult model exactly."""
        sampled = real_questions[:10]
        answers = {q["id"]: q["correct_answer"] for q in sampled[:7]}
        result_dict = quiz_engine.evaluate_submission(sampled, answers)

        # Must parse and validate through Pydantic QuizResult without ValidationError
        validated = QuizResult(**result_dict)
        assert validated.total_questions == 10
        assert validated.correct_count == 7
        assert validated.score_percentage == 70.0
        assert len(validated.results) == 10

    def test_diagnostic_chinese_explanation_intact_for_wrong_answers(self, real_questions):
        """Verifies diagnostic payload retains complete structured Chinese explanations for mistakes."""
        sampled = real_questions[:15]
        answers = {q["id"]: "x" for q in sampled}  # all wrong
        result = quiz_engine.evaluate_submission(sampled, answers)

        for item in result["results"]:
            assert item["is_correct"] is False
            exp = item["explanation_zh"]
            assert exp is not None
            assert isinstance(exp["concept"], str) and len(exp["concept"]) > 0
            assert isinstance(exp["rationale"], str) and len(exp["rationale"]) > 0
            assert isinstance(exp["distractors"], dict)


# ==============================================================================
# 6. Randomness & Uniformity Sanity Test
# ==============================================================================

class TestSamplingRandomnessSanity:
    """Verifies that sample_questions exhibits random distribution and is not statically biased."""

    def test_uniform_distribution_across_questions(self):
        """Draw 1 question from a 5-question pool 1,000 times.
        Verify each question is drawn with frequency roughly 200 (within binomial 3-sigma [140, 260]).
        """
        pool = [{"id": f"Q_{i}", "chapter_id": "Ch_01"} for i in range(5)]
        counts = {f"Q_{i}": 0 for i in range(5)}

        trials = 1000
        for _ in range(trials):
            sampled = quiz_engine.sample_questions(pool, ["Ch_01"], 1)
            assert len(sampled) == 1
            counts[sampled[0]["id"]] += 1

        # Expected value = 200, std dev = sqrt(1000 * 0.2 * 0.8) = sqrt(160) ≈ 12.65
        # 4-sigma range: 200 +/- 55 -> [145, 255]
        for q_id, count in counts.items():
            assert 140 <= count <= 260, (
                f"Question {q_id} sampled {count} times (expected ~200, acceptable [140, 260]). "
                f"Sampling appears biased!"
            )
