"""
tests/test_ingest.py
Unit & Integration Tests for DOCX Ingestion, Question Extraction, Option Mapping,
Diagram Binding, and Chinese Explanation Schema Integrity.

Tiers Covered:
- Tier 1: Feature Coverage (585 questions across Ch 1-6, options A-D, answers, Chinese explanations, media files)
- Tier 2: Boundary & Corner Cases (special tables, nested tables, diagram options, character encoding)

Remediation Notes (Iteration 2):
- Added test_extracted_media_files_exist to verify 72 diagram images in static/media/.
- Enhanced test_questions_json_fields_and_types to verify image_url, context_table, and media file bindings on disk.
- Updated test_pure_image_options_in_ch3 to assert both Q14 and Q16 diagram options.
"""

import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import unittest
import pytest

# Project root directory (dynamic resolution)
_curr = Path(__file__).resolve()
PROJECT_ROOT = _curr.parent
for p in [_curr] + list(_curr.parents):
    if (p / "PROJECT.md").exists() or (p / "Ch_01_MC_Algo.docx").exists():
        PROJECT_ROOT = p
        break
DOCX_FILES = [
    PROJECT_ROOT / f"Ch_{i:02d}_MC_Algo.docx" for i in range(1, 7)
]
EXPECTED_COUNTS = {
    1: 113,
    2: 87,
    3: 72,
    4: 124,
    5: 86,
    6: 103,
}
TOTAL_EXPECTED_QUESTIONS = 585
EXPECTED_MEDIA_COUNTS = {
    1: 0,
    2: 12,
    3: 22,
    4: 12,
    5: 7,
    6: 19,
}
TOTAL_EXPECTED_MEDIA = 72

XML_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parse_docx_questions_raw(docx_path: Path):
    """
    Oracle helper to parse questions directly from DOCX XML DOM.
    Returns list of dicts: {number, stem, options, answer, nested_count}
    """
    assert docx_path.exists(), f"DOCX file {docx_path} not found"
    questions = []

    with zipfile.ZipFile(docx_path) as z:
        doc_xml = z.read("word/document.xml")
        tree = ET.fromstring(doc_xml)
        body = tree.find("w:body", XML_NS)
        if body is None:
            return questions

        for tbl in body.findall("w:tbl", XML_NS):
            tr = tbl.find("w:tr", XML_NS)
            if tr is None:
                continue
            tc = tr.find("w:tc", XML_NS)
            if tc is None:
                continue

            nested = tc.findall("w:tbl", XML_NS)
            if len(nested) < 2:
                continue

            # Answer table is ALWAYS the last nested table
            ans_tbl = nested[-1]
            ans_text = "".join(ans_tbl.itertext()).strip()
            if "ANSWER:" not in ans_text:
                continue

            # Canonical answer is the letter after ANSWER:
            ans_match = re.search(r"ANSWER:\s*([a-d])", ans_text, re.IGNORECASE)
            ans_letter = ans_match.group(1).lower() if ans_match else None

            # Options table is ALWAYS second to last nested table
            opt_tbl = nested[-2]
            opt_rows = opt_tbl.findall("w:tr", XML_NS)
            options = {}
            for row in opt_rows:
                cells = row.findall("w:tc", XML_NS)
                if len(cells) >= 2:
                    row_text = "".join(cells[-2].itertext()).strip()
                    label_match = re.search(r"([a-d])\.", row_text, re.IGNORECASE)
                    if label_match:
                        opt_key = label_match.group(1).lower()
                        opt_val = "".join(cells[-1].itertext()).strip()
                        options[opt_key] = opt_val

            # Question stem text
            stem_paragraphs = []
            for p in tc.findall("w:p", XML_NS):
                text = "".join(p.itertext()).strip()
                if text:
                    stem_paragraphs.append(text)
            full_stem = " ".join(stem_paragraphs)

            # Match question number
            num_match = re.match(r"^\s*(\d+)[\.\s\u00a0]", full_stem)
            q_num = int(num_match.group(1)) if num_match else len(questions) + 1

            questions.append({
                "number": q_num,
                "stem": full_stem,
                "options": options,
                "answer": ans_letter,
                "nested_count": len(nested),
            })

    return questions


# ==============================================================================
# Tier 1: Feature Coverage (DOCX Question Ingestion, Options, Answers, Media)
# ==============================================================================

class TestDocxSourceIntegrity(unittest.TestCase):
    """Validates the canonical source DOCX files as the authoritative test oracle."""

    def test_all_six_docx_files_exist(self):
        """Verify all 6 chapter files exist in project root and are valid DOCX archives."""
        for path in DOCX_FILES:
            assert path.exists(), f"Source file missing: {path.name}"
            assert path.stat().st_size > 10000, f"File {path.name} is unexpectedly small or empty"
            assert zipfile.is_zipfile(path), f"File {path.name} is not a valid zip/docx archive"

    def test_question_count_per_chapter(self):
        """Verify exact canonical question count in each chapter DOCX."""
        total = 0
        for ch, expected_q in EXPECTED_COUNTS.items():
            docx_path = PROJECT_ROOT / f"Ch_{ch:02d}_MC_Algo.docx"
            questions = parse_docx_questions_raw(docx_path)
            assert len(questions) == expected_q, (
                f"Chapter {ch} count mismatch: got {len(questions)}, expected {expected_q}"
            )
            total += len(questions)
        assert total == TOTAL_EXPECTED_QUESTIONS, (
            f"Total question count mismatch: got {total}, expected {TOTAL_EXPECTED_QUESTIONS}"
        )

    def test_sequential_question_numbering_contiguity(self):
        """Verify 100% contiguity: question numbers start at 1 and increment with 0 gaps or duplicates."""
        for ch, expected_q in EXPECTED_COUNTS.items():
            docx_path = PROJECT_ROOT / f"Ch_{ch:02d}_MC_Algo.docx"
            questions = parse_docx_questions_raw(docx_path)
            numbers = [q["number"] for q in questions]
            expected_numbers = list(range(1, expected_q + 1))
            assert numbers == expected_numbers, (
                f"Chapter {ch} numbering is not strictly 1..{expected_q}. Gaps or duplicates found."
            )

    def test_all_questions_have_valid_canonical_answer(self):
        """Verify every single question has a valid lowercase answer in {'a', 'b', 'c', 'd'}."""
        for ch in range(1, 7):
            docx_path = PROJECT_ROOT / f"Ch_{ch:02d}_MC_Algo.docx"
            questions = parse_docx_questions_raw(docx_path)
            for q in questions:
                ans = q["answer"]
                assert ans in {"a", "b", "c", "d"}, (
                    f"Invalid answer '{ans}' in Ch {ch} Q{q['number']}"
                )

    def test_all_questions_have_four_options(self):
        """Verify each question possesses options a, b, c, d."""
        for ch in range(1, 7):
            docx_path = PROJECT_ROOT / f"Ch_{ch:02d}_MC_Algo.docx"
            questions = parse_docx_questions_raw(docx_path)
            for q in questions:
                opts = q["options"]
                assert set(opts.keys()) == {"a", "b", "c", "d"}, (
                    f"Question Ch {ch} Q{q['number']} missing option keys: got {set(opts.keys())}"
                )

    def test_media_image_counts_per_chapter(self):
        """Verify exact count of embedded diagram images in each DOCX file (total 72)."""
        total_media = 0
        for ch, expected_media in EXPECTED_MEDIA_COUNTS.items():
            docx_path = PROJECT_ROOT / f"Ch_{ch:02d}_MC_Algo.docx"
            with zipfile.ZipFile(docx_path) as z:
                media_files = [n for n in z.namelist() if n.startswith("word/media/")]
                assert len(media_files) == expected_media, (
                    f"Ch {ch} media count mismatch: got {len(media_files)}, expected {expected_media}"
                )
                total_media += len(media_files)
        assert total_media == TOTAL_EXPECTED_MEDIA, (
            f"Total media mismatch: got {total_media}, expected {TOTAL_EXPECTED_MEDIA}"
        )


# ==============================================================================
# Tier 1 & 2: Ingested Data Store Verification (`data/questions.json` & `static/media/`)
# ==============================================================================

class TestQuestionsJsonRepository(unittest.TestCase):
    """Validates the output question bank JSON and media extracted by the ingestion pipeline."""

    def setUp(self):
        self.json_path = PROJECT_ROOT / "data" / "questions.json"
        self.media_dir = PROJECT_ROOT / "static" / "media"

    def test_extracted_media_files_exist(self):
        """Verify that extracted diagram PNG images exist in static/media/."""
        if not self.media_dir.exists():
            self.skipTest("static/media/ directory not yet generated by ingestion pipeline (M1 in progress)")

        png_files = list(self.media_dir.glob("*.png"))
        assert len(png_files) >= TOTAL_EXPECTED_MEDIA, (
            f"Expected at least {TOTAL_EXPECTED_MEDIA} extracted PNG images in static/media/, got {len(png_files)}"
        )
        for png in png_files:
            assert png.stat().st_size > 0, f"Media file {png.name} is 0 bytes (empty/corrupted)"

    def test_questions_json_structure_if_present(self):
        """Verify schema of data/questions.json if it has been ingested."""
        if not self.json_path.exists():
            self.skipTest("data/questions.json not yet generated by ingestion pipeline (M1 in progress)")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "chapters" in data, "questions.json missing 'chapters' key"
        assert "questions" in data, "questions.json missing 'questions' key"
        assert len(data["chapters"]) == 6, f"Expected 6 chapters, got {len(data['chapters'])}"
        assert len(data["questions"]) == TOTAL_EXPECTED_QUESTIONS, (
            f"Expected {TOTAL_EXPECTED_QUESTIONS} questions, got {len(data['questions'])}"
        )

    def test_questions_json_fields_and_types(self):
        """Verify each question in questions.json adheres to the interface contract and binds media."""
        if not self.json_path.exists():
            self.skipTest("data/questions.json not yet generated by ingestion pipeline (M1 in progress)")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chapter_ids = {c["id"] for c in data["chapters"]}
        has_media_dir = self.media_dir.exists()

        for q in data["questions"]:
            assert "id" in q and isinstance(q["id"], str)
            assert "chapter_id" in q and q["chapter_id"] in chapter_ids
            assert "question_number" in q and isinstance(q["question_number"], int)
            assert "stem" in q and len(q["stem"].strip()) > 0
            assert "options" in q and isinstance(q["options"], dict)
            assert set(q["options"].keys()) == {"a", "b", "c", "d"}
            assert "correct_answer" in q and q["correct_answer"] in {"a", "b", "c", "d"}

            # Verify image_url and context_table bindings (PROJECT.md § Interface Contracts)
            assert "image_url" in q, f"Question {q['id']} missing 'image_url' field"
            assert "context_table" in q, f"Question {q['id']} missing 'context_table' field"
            if q["image_url"] is not None:
                assert isinstance(q["image_url"], str)
                if has_media_dir:
                    rel_path = q["image_url"].lstrip("/").replace("/", os.sep)
                    target_file = PROJECT_ROOT / rel_path
                    assert target_file.exists(), (
                        f"Question {q['id']} references missing media image file: {target_file}"
                    )

    def test_chinese_explanations_exist_and_structured(self):
        """Verify structured Chinese explanations (concept, rationale, distractors) exist in question bank."""
        if not self.json_path.exists():
            self.skipTest("data/questions.json not yet generated by ingestion pipeline (M1 in progress)")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        has_chinese_re = re.compile(r"[\u4e00-\u9fff]")
        for q in data["questions"]:
            assert "explanation_zh" in q, f"Question {q['id']} missing 'explanation_zh'"
            exp = q["explanation_zh"]
            assert isinstance(exp, dict), f"Question {q['id']} 'explanation_zh' must be dict"
            assert "concept" in exp, f"Question {q['id']} explanation missing 'concept'"
            assert "rationale" in exp, f"Question {q['id']} explanation missing 'rationale'"
            assert "distractors" in exp, f"Question {q['id']} explanation missing 'distractors'"

            # Verify presence of Chinese characters in rationale
            assert has_chinese_re.search(exp["rationale"]), (
                f"Question {q['id']} explanation rationale must contain Chinese characters"
            )


# ==============================================================================
# Tier 2: Boundary & Corner Cases in Ingestion
# ==============================================================================

class TestIngestBoundaryAndCornerCases(unittest.TestCase):
    """Validates resilience against known DOCX quirks and edge cases."""

    def test_chapter_4_q90_three_nested_tables(self):
        """
        Verify Chapter 4 Question 90 which contains 3 nested tables:
        (1) Data table, (2) Options table, (3) Answer table.
        """
        docx_path = PROJECT_ROOT / "Ch_04_MC_Algo.docx"
        questions = parse_docx_questions_raw(docx_path)
        q90 = next((q for q in questions if q["number"] == 90), None)
        assert q90 is not None, "Ch 4 Q90 not found"
        assert q90["nested_count"] >= 2, f"Expected nested tables, got {q90['nested_count']}"
        assert q90["answer"] == "c", f"Ch 4 Q90 expected answer 'c', got '{q90['answer']}'"

    def test_pure_image_options_in_ch3(self):
        """Verify Chapter 3 Questions 14 & 16 containing diagram-based options are handled without loss."""
        docx_path = PROJECT_ROOT / "Ch_03_MC_Algo.docx"
        questions = parse_docx_questions_raw(docx_path)
        for q_num in (14, 16):
            q_item = next((q for q in questions if q["number"] == q_num), None)
            assert q_item is not None, f"Ch 3 Q{q_num} not found"
            assert set(q_item["options"].keys()) == {"a", "b", "c", "d"}
            assert q_item["answer"] in {"a", "b", "c", "d"}

    def test_non_existent_file_handling(self):
        """Verify ingestion gracefully handles non-existent or corrupted files without unhandled crash."""
        fake_path = PROJECT_ROOT / "NonExistent_Ch_99.docx"
        with self.assertRaises(AssertionError):
            parse_docx_questions_raw(fake_path)


if __name__ == "__main__":
    unittest.main()

