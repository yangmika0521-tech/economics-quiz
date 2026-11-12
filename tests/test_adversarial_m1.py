"""
tests/test_adversarial_m1.py
Adversarial Stress Test Suite for Milestone 1 Ingestion and Explanations.
Executed by Challenger 1.
"""

import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_JSON = PROJECT_ROOT / "data" / "questions.json"
STATIC_MEDIA_DIR = PROJECT_ROOT / "static" / "media"

EXPECTED_COUNTS = {
    "Ch_01": 113,
    "Ch_02": 87,
    "Ch_03": 72,
    "Ch_04": 124,
    "Ch_05": 86,
    "Ch_06": 103,
}
TOTAL_EXPECTED = 585
XML_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def load_question_bank():
    assert QUESTIONS_JSON.exists(), f"{QUESTIONS_JSON} does not exist"
    with open(QUESTIONS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_zero_duplicate_ids():
    data = load_question_bank()
    ids = [q["id"] for q in data["questions"]]
    id_counts = Counter(ids)
    duplicates = [qid for qid, count in id_counts.items() if count > 1]
    assert len(duplicates) == 0, f"Found duplicate question IDs: {duplicates}"
    assert len(ids) == TOTAL_EXPECTED, f"Expected {TOTAL_EXPECTED} IDs, got {len(ids)}"


def test_exact_question_count_per_chapter():
    data = load_question_bank()
    # Check chapters array
    assert len(data["chapters"]) == 6, f"Expected 6 chapters, got {len(data['chapters'])}"
    for ch in data["chapters"]:
        expected = EXPECTED_COUNTS[ch["id"]]
        assert ch["total_questions"] == expected, (
            f"Chapter {ch['id']} metadata total_questions={ch['total_questions']}, expected {expected}"
        )

    # Check questions array counts
    ch_q_counts = Counter(q["chapter_id"] for q in data["questions"])
    assert ch_q_counts == EXPECTED_COUNTS, (
        f"Actual chapter counts {dict(ch_q_counts)} != expected {EXPECTED_COUNTS}"
    )


def test_strict_sequential_numbering():
    data = load_question_bank()
    by_chapter = {}
    for q in data["questions"]:
        by_chapter.setdefault(q["chapter_id"], []).append(q)

    for ch_id, expected_total in EXPECTED_COUNTS.items():
        q_list = by_chapter[ch_id]
        nums = [q["question_number"] for q in q_list]
        expected_nums = list(range(1, expected_total + 1))
        assert nums == expected_nums, f"Chapter {ch_id} numbering is not strictly 1..{expected_total}"

        # Also check ID formatting: ChXX_QYYY
        ch_num = int(ch_id.split("_")[1])
        expected_ids = [f"Ch{ch_num:02d}_Q{n:03d}" for n in expected_nums]
        actual_ids = [q["id"] for q in q_list]
        assert actual_ids == expected_ids, f"Chapter {ch_id} question IDs don't match standard naming"


def test_all_options_and_answers_valid():
    data = load_question_bank()
    for q in data["questions"]:
        qid = q["id"]
        assert "options" in q, f"{qid} missing options"
        assert set(q["options"].keys()) == {"a", "b", "c", "d"}, f"{qid} options keys != a,b,c,d"
        for opt_k in ["a", "b", "c", "d"]:
            val = q["options"][opt_k]
            assert isinstance(val, str), f"{qid} option {opt_k} is not a string"
            assert len(val.strip()) > 0, f"{qid} option {opt_k} is empty"

        assert q["correct_answer"] in {"a", "b", "c", "d"}, (
            f"{qid} invalid correct_answer: {q['correct_answer']}"
        )


def test_answer_distribution_statistical_sanity():
    data = load_question_bank()
    overall_answers = Counter(q["correct_answer"] for q in data["questions"])
    print("\nOverall Answer Distribution:")
    for ans in ["a", "b", "c", "d"]:
        cnt = overall_answers[ans]
        pct = (cnt / TOTAL_EXPECTED) * 100
        print(f"  {ans}: {cnt} ({pct:.2f}%)")
        # Adversarial sanity check: each letter should have at least 15% and at most 35%
        assert 0.15 <= (cnt / TOTAL_EXPECTED) <= 0.35, (
            f"Answer '{ans}' frequency {pct:.2f}% is outside statistical sanity range [15%, 35%]"
        )

    # By-chapter distribution
    by_chapter = {}
    for q in data["questions"]:
        by_chapter.setdefault(q["chapter_id"], []).append(q["correct_answer"])

    for ch_id, ans_list in by_chapter.items():
        ch_counts = Counter(ans_list)
        total_ch = len(ans_list)
        for ans in ["a", "b", "c", "d"]:
            cnt = ch_counts[ans]
            pct = cnt / total_ch
            # No letter should be 0 or dominate > 50% in any chapter
            assert cnt > 0, f"Chapter {ch_id} has 0 questions with answer '{ans}'"
            assert pct < 0.50, f"Chapter {ch_id} has answer '{ans}' with {pct*100:.1f}% (>50%)"


def test_image_urls_exist_on_disk():
    data = load_question_bank()
    media_questions = [q for q in data["questions"] if q["image_url"] is not None]
    assert len(media_questions) > 0, "No questions have image_url populated"

    checked_urls = set()
    for q in media_questions:
        url = q["image_url"]
        assert url.startswith("/static/media/"), f"Question {q['id']} invalid image_url prefix: {url}"
        rel_path = url.lstrip("/")
        disk_path = PROJECT_ROOT / rel_path
        assert disk_path.exists(), f"Question {q['id']} image not found: {disk_path}"
        assert disk_path.stat().st_size > 0, f"Question {q['id']} image is 0 bytes: {disk_path}"
        checked_urls.add(disk_path)

    print(f"\nVerified {len(media_questions)} questions pointing to {len(checked_urls)} distinct image files")


def test_html_option_images_exist_on_disk():
    data = load_question_bank()
    img_tag_pattern = re.compile(r'<img\s+[^>]*src="([^"]+)"')
    found_option_imgs = 0

    for q in data["questions"]:
        for opt_k, opt_text in q["options"].items():
            for match in img_tag_pattern.finditer(opt_text):
                src = match.group(1)
                assert src.startswith("/static/media/"), f"{q['id']} option {opt_k} image invalid src: {src}"
                rel_path = src.lstrip("/")
                disk_path = PROJECT_ROOT / rel_path
                assert disk_path.exists(), f"{q['id']} option {opt_k} image not found: {disk_path}"
                assert disk_path.stat().st_size > 0, f"{q['id']} option {opt_k} image 0 bytes: {disk_path}"
                found_option_imgs += 1

    print(f"Verified {found_option_imgs} HTML option images in question bank")
    assert found_option_imgs >= 8, f"Expected at least 8 option images (Ch 3 Q14, Q16), got {found_option_imgs}"


def test_refer_to_figure_and_table_bindings():
    """
    Check every question that contains 'Refer to Figure' or 'Refer to Table'
    to see if image_url or context_table / in-stem table is populated.
    """
    data = load_question_bank()
    fig_pattern = re.compile(r"\bRefer\s+to\s+Figure\b", re.IGNORECASE)
    tbl_pattern = re.compile(r"\bRefer\s+to\s+Table\b", re.IGNORECASE)
    scen_pattern = re.compile(r"\bRefer\s+to\s+Scenario\b", re.IGNORECASE)

    missing_fig = []
    missing_tbl = []

    for q in data["questions"]:
        stem = q["stem"]
        qid = q["id"]

        if fig_pattern.search(stem):
            if not q["image_url"]:
                missing_fig.append((qid, stem[:60]))

        if tbl_pattern.search(stem) or scen_pattern.search(stem):
            has_context = bool(q["context_table"])
            has_instem_table = "|" in stem and "---" in stem
            if not has_context and not has_instem_table:
                missing_tbl.append((qid, stem[:60]))

    if missing_fig:
        print(f"\nWARNING: Questions with 'Refer to Figure' missing image_url ({len(missing_fig)}):")
        for qid, s in missing_fig:
            print(f"  {qid}: {s}")

    if missing_tbl:
        print(f"\nWARNING: Questions with 'Refer to Table/Scenario' missing context_table ({len(missing_tbl)}):")
        for qid, s in missing_tbl:
            print(f"  {qid}: {s}")

    assert len(missing_fig) == 0, f"{len(missing_fig)} questions refer to Figure but lack image_url: {missing_fig}"
    assert len(missing_tbl) == 0, f"{len(missing_tbl)} questions refer to Table/Scenario but lack table data: {missing_tbl}"


def test_edge_case_ch4_q90():
    data = load_question_bank()
    q90 = next(q for q in data["questions"] if q["id"] == "Ch04_Q090")
    assert q90["correct_answer"] == "c"
    # Stem must contain the in-stem demand schedule table markdown
    assert "|" in q90["stem"] and "---" in q90["stem"], "Ch 4 Q90 stem does not contain markdown table"
    # context_table should contain Table 4-5
    assert q90["context_table"] is not None, "Ch 4 Q90 context_table is None"
    assert "Table 4-5" in q90["context_table"], "Ch 4 Q90 context_table missing Table 4-5"
    assert "Aqueduct" in q90["context_table"], "Ch 4 Q90 context_table missing supplier data"
    # Check explanation
    exp = q90["explanation_zh"]
    assert exp["concept"] is not None
    assert "300" in exp["rationale"]


def test_edge_case_ch3_q14_and_q16():
    data = load_question_bank()
    q14 = next(q for q in data["questions"] if q["id"] == "Ch03_Q014")
    q16 = next(q for q in data["questions"] if q["id"] == "Ch03_Q016")

    for q in (q14, q16):
        for opt_k in ["a", "b", "c", "d"]:
            val = q["options"][opt_k]
            assert "<img" in val, f"{q['id']} option {opt_k} does not contain <img tag: {val}"
            assert 'class="option-img"' in val


def test_edge_case_ch3_q12_errata():
    data = load_question_bank()
    q12 = next(q for q in data["questions"] if q["id"] == "Ch03_Q012")
    assert q12["correct_answer"] == "b", f"Ch03_Q012 expected canonical answer 'b', got {q12['correct_answer']}"
    exp = q12["explanation_zh"]
    assert exp["note"] is not None, "Ch03_Q012 explanation_zh.note is None"
    assert "36" in exp["note"] and "7.5" in exp["note"], (
        f"Ch03_Q012 note missing 36 pastrami / 7.5 milk calculation: {exp['note']}"
    )


def test_inline_formula_questions():
    data = load_question_bank()
    # Ch 2 Q52
    q52 = next(q for q in data["questions"] if q["id"] == "Ch02_Q052")
    assert "1/2" in q52["options"]["a"]
    assert "2 sofas" in q52["options"]["b"]

    # Ch 2 Q83
    q83 = next(q for q in data["questions"] if q["id"] == "Ch02_Q083")
    assert "-1/2" in q83["options"]["c"]
    assert q83["options"]["d"] == "1/2."

    # Ch 2 Q85
    q85 = next(q for q in data["questions"] if q["id"] == "Ch02_Q085")
    assert q85["options"]["a"] == "1/2."
    assert q85["options"]["b"] == "-1/2."

    # Ch 3 Q30
    q30 = next(q for q in data["questions"] if q["id"] == "Ch03_Q030")
    assert q30["options"]["a"] == "1/3 hour"
    assert q30["options"]["b"] == "1/5 hour"


def test_curated_explanations_matching_fidelity():
    """
    Adversarial Challenge: Verify that all curated explanations defined
    in CURATED_EXPLANATIONS actually matched questions in questions.json.
    """
    from app.explanation_generator import CURATED_EXPLANATIONS
    data = load_question_bank()
    q_map = {q["id"]: q for q in data["questions"]}

    unmatched_keys = []
    generic_fallbacks = []

    for curated_key, curated_content in CURATED_EXPLANATIONS.items():
        if curated_key not in q_map:
            unmatched_keys.append(curated_key)
        else:
            actual_q = q_map[curated_key]
            actual_rationale = actual_q["explanation_zh"]["rationale"]
            expected_rationale = curated_content["rationale"]
            if actual_rationale != expected_rationale:
                generic_fallbacks.append((curated_key, actual_rationale[:60]))

    print(f"\nCurated Explanations Audit:")
    print(f"  Unmatched keys in questions.json: {unmatched_keys}")
    print(f"  Curated keys that fell back to generic rationale: {generic_fallbacks}")

    # This is an adversarial assertion:
    assert len(unmatched_keys) == 0, (
        f"CURATED_EXPLANATIONS contains keys that do not match questions.json IDs: {unmatched_keys}. "
        f"Expected IDs to be zero-padded like Ch02_Q083 instead of Ch02_Q83!"
    )
    assert len(generic_fallbacks) == 0, (
        f"Questions that should have received curated explanations got generic ones: {generic_fallbacks}"
    )


def test_docx_oracle_cross_verification():
    """
    Oracle Cross-Verification:
    Compare every single question's answer in data/questions.json against
    direct raw parsing from the DOCX file.
    Must achieve 100% agreement on all 585 canonical answers.
    """
    from tests.test_ingest import parse_docx_questions_raw
    data = load_question_bank()
    q_map = {q["id"]: q for q in data["questions"]}

    mismatches = []
    total_checked = 0

    for ch_num in range(1, 7):
        docx_path = PROJECT_ROOT / f"Ch_{ch_num:02d}_MC_Algo.docx"
        raw_qs = parse_docx_questions_raw(docx_path)
        for rq in raw_qs:
            total_checked += 1
            qid = f"Ch{ch_num:02d}_Q{rq['number']:03d}"
            assert qid in q_map, f"Question {qid} missing from questions.json"
            ingested_q = q_map[qid]
            expected_ans = rq["answer"]
            actual_ans = ingested_q["correct_answer"]
            if actual_ans != expected_ans:
                mismatches.append({
                    "id": qid,
                    "docx_answer": expected_ans,
                    "ingested_answer": actual_ans,
                })

    print(f"\nOracle Cross-Verification: {total_checked}/585 questions checked against raw DOCX")
    assert len(mismatches) == 0, f"Found {len(mismatches)} answer mismatches against DOCX: {mismatches}"
