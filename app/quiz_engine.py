"""Quiz Engine for Economics Quiz Practice & Evaluation System.

Provides core business logic for:
1. Deduplicated random question sampling across single, multiple, or all chapters,
   with boundary count clamping.
2. Submission evaluation, scoring calculations, per-chapter performance breakdown,
   and diagnostic Chinese explanation payload generation.
"""

import random
from typing import List, Dict, Any, Optional


def _get_field(item: Any, key: str, default: Any = None) -> Any:
    """Safely retrieves a field from either a dict or an object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def sample_questions(pool: List[Any], chapter_ids: List[str], count: int) -> List[Any]:
    """Randomly samples questions from the pool matching the selected chapters without replacement.

    Args:
        pool: List of question dictionaries or Question objects.
        chapter_ids: List of chapter identifiers to include (e.g. ['Ch_01', 'Ch_02']).
        count: Number of questions requested by user.

    Returns:
        List of sampled questions with 0 duplicates. Clamped to [1, len(eligible_pool)].
        Returns empty list if chapter_ids is empty or no questions match.
    """
    if not chapter_ids or not pool:
        return []

    chapter_set = set(chapter_ids)
    eligible = [q for q in pool if _get_field(q, "chapter_id") in chapter_set]

    if not eligible:
        return []

    # Defensive integer conversion:
    # Safely converts float, string numbers, etc., and falls back gracefully
    try:
        count = int(count)
    except (ValueError, TypeError):
        count = 1
    except OverflowError:
        count = len(eligible) if count > 0 else 1

    # Boundary clamping:
    # 1. Non-positive or zero counts clamp to 1.
    # 2. Counts exceeding eligible pool size clamp to total available questions.
    effective_count = count
    if effective_count <= 0:
        effective_count = 1
    elif effective_count > len(eligible):
        effective_count = len(eligible)

    # random.sample guarantees selection without replacement (zero duplicates)
    return random.sample(eligible, effective_count)


def evaluate_submission(sampled_questions: List[Any], user_answers: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """Evaluates user submitted answers against sampled questions.

    Args:
        sampled_questions: List of question dictionaries or Question models for the session.
        user_answers: Mapping from question_id to selected option key ('a', 'b', 'c', 'd').

    Returns:
        Dictionary with total_questions, correct_count, score_percentage, chapter_breakdown,
        and diagnostic results list.
    """
    total_questions = len(sampled_questions)
    correct_count = 0
    chapter_breakdown: Dict[str, Dict[str, int]] = {}
    results: List[Dict[str, Any]] = []

    for q in sampled_questions:
        q_id = _get_field(q, "id")
        ch_id = _get_field(q, "chapter_id", "Unknown")
        correct_ans = _get_field(q, "correct_answer")
        user_ans = user_answers.get(q_id) if user_answers else None

        # Check correctness
        is_correct = False
        if user_ans is not None and correct_ans is not None:
            is_correct = (str(user_ans).strip().lower() == str(correct_ans).strip().lower())

        if is_correct:
            correct_count += 1

        # Track per-chapter statistics
        if ch_id not in chapter_breakdown:
            chapter_breakdown[ch_id] = {"correct": 0, "total": 0}
        chapter_breakdown[ch_id]["total"] += 1
        if is_correct:
            chapter_breakdown[ch_id]["correct"] += 1

        # Build diagnostic result item
        results.append({
            "question_id": q_id,
            "stem": _get_field(q, "stem"),
            "user_answer": user_ans,
            "correct_answer": str(correct_ans).strip().lower() if correct_ans else "",
            "is_correct": is_correct,
            "image_url": _get_field(q, "image_url"),
            "context_table": _get_field(q, "context_table"),
            "explanation_zh": _get_field(q, "explanation_zh"),
        })

    score_percentage = (correct_count / total_questions * 100.0) if total_questions > 0 else 0.0

    return {
        "total_questions": total_questions,
        "correct_count": correct_count,
        "score_percentage": round(score_percentage, 2),
        "chapter_breakdown": chapter_breakdown,
        "results": results,
    }
