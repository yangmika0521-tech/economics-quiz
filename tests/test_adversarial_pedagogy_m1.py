"""
tests/test_adversarial_pedagogy_m1.py
Adversarial Stress Test Suite for Pedagogical Quality and Chinese Explanations.
Executed by Challenger 2 (Explanation & Pedagogical Quality Adversarial Challenger).
"""

import json
import re
from pathlib import Path
from collections import Counter
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_JSON = PROJECT_ROOT / "data" / "questions.json"


@pytest.fixture(scope="module")
def question_bank():
    assert QUESTIONS_JSON.exists(), f"Missing {QUESTIONS_JSON}"
    with open(QUESTIONS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "questions" in data, "questions.json missing top-level 'questions' key"
    assert len(data["questions"]) == 585, f"Expected 585 questions, got {len(data['questions'])}"
    return data["questions"]


def test_ch02_q083_and_q085_mathematical_accuracy(question_bank):
    """
    Stress-test Ch02_Q083 and Ch02_Q085:
    - Mathematical slope calculations must be explicitly present in rationale.
    - Mathematical slope formulas must be accurate (Rise/Run = ΔY/ΔX).
    - Distractor explanations must properly map to the specific incorrect options.
    """
    q_map = {q["id"]: q for q in question_bank}
    assert "Ch02_Q083" in q_map, "Ch02_Q083 not found in questions.json"
    assert "Ch02_Q085" in q_map, "Ch02_Q085 not found in questions.json"

    # 1. Ch02_Q083
    q83 = q_map["Ch02_Q083"]
    assert q83["correct_answer"] == "a"
    exp83 = q83["explanation_zh"]
    assert exp83["concept"] is not None and "斜率" in exp83["concept"]
    # Check rationale formula: -20 / 10 = -2
    rat83 = exp83["rationale"]
    assert "-20" in rat83 and "10" in rat83 and "-2" in rat83
    assert "ΔY" in rat83 or "縱軸" in rat83
    assert "ΔX" in rat83 or "橫軸" in rat83
    # Check distractors mapping
    d83 = exp83["distractors"]
    assert set(d83.keys()) == {"b", "c", "d"}
    assert "負號" in d83["b"] or "正斜率" in d83["b"]  # option b is 2. (lost negative sign)
    assert "-1/2" in d83["c"] or "倒置" in d83["c"]    # option c is -1/2. (inverted ΔX/ΔY)
    assert "1/2" in d83["d"] or "雙重錯誤" in d83["d"]  # option d is 1/2. (inverted and lost negative)

    # 2. Ch02_Q085
    q85 = q_map["Ch02_Q085"]
    assert q85["correct_answer"] == "b"
    exp85 = q85["explanation_zh"]
    assert exp85["concept"] is not None and "斜率" in exp85["concept"]
    # Check rationale formula: (35 - 40) / (20 - 10) = -5 / 10 = -1/2
    rat85 = exp85["rationale"]
    assert "(10, 40)" in rat85 or "10" in rat85
    assert "(20, 35)" in rat85 or "35" in rat85
    assert "-5" in rat85 or "-1/2" in rat85
    # Check distractors mapping
    d85 = exp85["distractors"]
    assert set(d85.keys()) == {"a", "c", "d"}
    assert "負號" in d85["a"] or "1/2" in d85["a"]   # option a is 1/2. (lost negative sign)
    assert "-2" in d85["c"] or "倒置" in d85["c"]    # option c is –2. (inverted)
    assert "2" in d85["d"] or "相反" in d85["d"]     # option d is 2. (inverted and positive)


def test_midpoint_formula_isolation_to_chapter_5(question_bank):
    """
    Stress-test that '中點公式' / '未採用中點公式' / midpoint elasticity formulas
    are strictly isolated to Chapter 5 (Elasticity) and NEVER cited in
    Chapters 1, 2, 3, 4, or 6.
    """
    forbidden_terms = ["未採用中點公式", "中點公式", "中點法", "midpoint"]
    illegal_occurrences = []

    for q in question_bank:
        ch = q["chapter_id"]
        qid = q["id"]
        exp = q["explanation_zh"]
        text_to_search = (
            (exp.get("concept") or "") + " " +
            (exp.get("rationale") or "") + " " +
            (exp.get("note") or "") + " " +
            " ".join(exp.get("distractors", {}).values())
        ).lower()

        for term in forbidden_terms:
            if term.lower() in text_to_search:
                if ch != "Ch_05":
                    illegal_occurrences.append({
                        "id": qid,
                        "chapter": ch,
                        "term": term,
                        "distractor_hits": [
                            k for k, v in exp.get("distractors", {}).items()
                            if term.lower() in v.lower()
                        ]
                    })

    assert len(illegal_occurrences) == 0, (
        f"Found {len(illegal_occurrences)} illegal citations of midpoint formula outside Chapter 5: "
        f"{illegal_occurrences}"
    )


def test_all_585_questions_explanation_completeness(question_bank):
    """
    Verify all 585 questions have fully populated, structured Chinese explanations:
    - concept: string, len >= 5
    - rationale: string, len >= 25
    - distractors: dict with exactly 3 keys matching {'a', 'b', 'c', 'd'} - {correct_answer}
    - each distractor text: string, len >= 10
    """
    assert len(question_bank) == 585
    defects = []

    for q in question_bank:
        qid = q["id"]
        corr = q["correct_answer"]
        exp = q.get("explanation_zh")

        if not isinstance(exp, dict):
            defects.append(f"{qid}: explanation_zh is not a dict")
            continue

        concept = exp.get("concept")
        if not concept or not isinstance(concept, str) or len(concept.strip()) < 5:
            defects.append(f"{qid}: invalid or too short concept: {concept!r}")

        rationale = exp.get("rationale")
        if not rationale or not isinstance(rationale, str) or len(rationale.strip()) < 25:
            defects.append(f"{qid}: invalid or too short rationale: {rationale!r}")

        distractors = exp.get("distractors")
        if not isinstance(distractors, dict):
            defects.append(f"{qid}: distractors is not a dict")
            continue

        expected_keys = {"a", "b", "c", "d"} - {corr}
        if set(distractors.keys()) != expected_keys:
            defects.append(f"{qid}: distractors keys {set(distractors.keys())} != {expected_keys}")

        for opt_k, dist_text in distractors.items():
            if not isinstance(dist_text, str) or len(dist_text.strip()) < 10:
                defects.append(f"{qid}: distractor '{opt_k}' too short: {dist_text!r}")

    assert len(defects) == 0, f"Found {len(defects)} explanation completeness defects:\n" + "\n".join(defects[:10])


def test_distractor_non_tautology_and_no_placeholders(question_bank):
    """
    Stress-test distractors against tautological patterns and placeholder junk:
    - No 'TODO', 'TBD', 'placeholder', 'undefined', 'null', 'NaN', 'xxx'
    - No empty circular tautologies like '選項 a 錯誤因為它是錯的' or '不是正確選項'
    - Must refer to substantive economic concepts or calculations
    """
    forbidden_tokens = ["todo", "tbd", "placeholder", "undefined", "lorem", "xxx", "asdf"]
    tautological_patterns = [
        re.compile(r"因為它是錯的"),
        re.compile(r"因為不是正確答案"),
        re.compile(r"不是正確選項$"),
        re.compile(r"該選項是錯的$"),
        re.compile(r"這不是正確答案"),
    ]

    violations = []
    for q in question_bank:
        qid = q["id"]
        exp = q["explanation_zh"]
        for opt_k, dist_text in exp.get("distractors", {}).items():
            lower_text = dist_text.lower()
            for token in forbidden_tokens:
                if token in lower_text:
                    violations.append(f"{qid} distractor ({opt_k}) contains forbidden token '{token}'")

            for pat in tautological_patterns:
                if pat.search(dist_text):
                    violations.append(f"{qid} distractor ({opt_k}) contains tautology '{pat.pattern}'")

    assert len(violations) == 0, f"Found {len(violations)} distractor quality violations:\n" + "\n".join(violations[:10])


def test_flagship_curated_pedagogy_verification(question_bank):
    """
    Verify high-complexity flagship pedagogical questions:
    - Ch03_Q012: Teacher errata note with 36 pastrami / 7.5 milk theoretical derivation
    - Ch04_Q090: Nested Table 4-5 market equilibrium calculation (sum = 300 at P=$2.00)
    - Ch02_Q052: PPF slope opportunity cost (2 sofas vs 1/2)
    - Ch03_Q014 & Ch03_Q016: Diagrammatic option analysis
    - Ch03_Q030: Inline fraction unit labor calculation (1/3 hour)
    """
    q_map = {q["id"]: q for q in question_bank}

    # Ch03_Q012
    q12 = q_map["Ch03_Q012"]
    exp12 = q12["explanation_zh"]
    assert exp12["note"] is not None
    assert "36" in exp12["note"] and "7.5" in exp12["note"]
    assert "40 小時" in exp12["note"]

    # Ch04_Q090
    q90 = q_map["Ch04_Q090"]
    exp90 = q90["explanation_zh"]
    assert "300" in exp90["rationale"]
    assert "2.00" in exp90["rationale"]
    assert exp90["distractors"]["a"] is not None and "350" in exp90["distractors"]["a"]

    # Ch02_Q052
    q52 = q_map["Ch02_Q052"]
    exp52 = q52["explanation_zh"]
    assert "斜率" in exp52["concept"] or "PPF" in exp52["concept"]
    assert "2" in exp52["rationale"]

    # Ch03_Q014
    q14 = q_map["Ch03_Q014"]
    exp14 = q14["explanation_zh"]
    assert "Aruba" in exp14["rationale"]
    assert "截距" in exp14["rationale"]

    # Ch03_Q016
    q16 = q_map["Ch03_Q016"]
    exp16 = q16["explanation_zh"]
    assert "Kenya" in exp16["rationale"] and "Peru" in exp16["rationale"]

    # Ch03_Q030
    q30 = q_map["Ch03_Q030"]
    exp30 = q30["explanation_zh"]
    assert "1/3" in exp30["rationale"]


def test_chapter5_elasticity_pedagogical_depth(question_bank):
    """
    Verify Chapter 5 elasticity questions:
    - Questions classified as midpoint elasticity mention 中點公式 in rationale or distractors
    - Total revenue tests mention P×Q and price elasticity
    - Distractors for numerical elasticity questions handle percentage calculation or inverted ratio
    """
    ch5_qs = [q for q in question_bank if q["chapter_id"] == "Ch_05"]
    assert len(ch5_qs) == 86

    midpoint_qs = [
        q for q in ch5_qs
        if "中點" in q["explanation_zh"]["concept"] or "midpoint" in q["stem"].lower()
    ]
    assert len(midpoint_qs) == 19, f"Expected exactly 19 midpoint elasticity questions in Ch 5, got {len(midpoint_qs)}"

    for q in midpoint_qs:
        exp = q["explanation_zh"]
        all_exp_text = exp["rationale"] + " " + " ".join(exp["distractors"].values())
        assert "中點" in all_exp_text or "彈性" in all_exp_text, (
            f"{q['id']} midpoint question lacks 中點 or 彈性 in explanation"
        )

    # In addition, total questions in Ch 5 citing midpoint across rationale or distractors is 40
    ch5_all_midpoint = [
        q for q in ch5_qs
        if "中點" in (q["explanation_zh"]["rationale"] + " " + " ".join(q["explanation_zh"]["distractors"].values()))
    ]
    assert len(ch5_all_midpoint) == 40, f"Expected 40 questions in Ch 5 referencing midpoint, got {len(ch5_all_midpoint)}"


def test_rationale_pedagogical_structure(question_bank):
    """
    Ensure every question's rationale follows high pedagogical standards:
    - Contains core concept heading or clear theoretical reasoning
    - Mentions correct answer option
    - Contains no dangling template tags like '{' or '}'
    """
    template_tag_re = re.compile(r"\{[a-zA-Z0-9_]+\}")
    issues = []

    for q in question_bank:
        qid = q["id"]
        corr = q["correct_answer"]
        rat = q["explanation_zh"]["rationale"]

        if template_tag_re.search(rat):
            issues.append(f"{qid}: rationale contains unexpanded template tag")

        # Must mention the correct option key
        if f"({corr})" not in rat and f"選項 {corr}" not in rat and f"選 ({corr})" not in rat:
            issues.append(f"{qid}: rationale does not reference correct option ({corr})")

    assert len(issues) == 0, f"Found {len(issues)} rationale structure issues:\n" + "\n".join(issues[:10])
