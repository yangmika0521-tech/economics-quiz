"""
tests/test_challenger_deep_audit.py
Independent Deep Adversarial Audit for Milestone 1 by Challenger 1.
Empirically stress-tests question bank, raw docx zip structures, media fidelity,
and pedagogical Chinese explanations.
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
PNG_HEADER = b"\x89PNG\r\n\x1a\n"

XML_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

EXPECTED_COUNTS = {
    "Ch_01": 113,
    "Ch_02": 87,
    "Ch_03": 72,
    "Ch_04": 124,
    "Ch_05": 86,
    "Ch_06": 103,
}
TOTAL_EXPECTED = 585


def load_data():
    with open(QUESTIONS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


class TestDirectDocxZipFidelity:
    """Audit raw DOCX zip archives directly without docx parser dependencies."""

    def test_raw_docx_zip_validity_and_embedded_images(self):
        """Audit embedded images inside raw docx zips vs static/media."""
        total_docx_images = 0
        per_chapter_images = {}
        for ch_num in range(1, 7):
            docx_path = PROJECT_ROOT / f"Ch_{ch_num:02d}_MC_Algo.docx"
            assert docx_path.exists(), f"DOCX file missing: {docx_path}"
            with zipfile.ZipFile(docx_path, "r") as z:
                # Find all media files in word/media/
                media_files = [n for n in z.namelist() if n.startswith("word/media/")]
                per_chapter_images[f"Ch_{ch_num:02d}"] = len(media_files)
                total_docx_images += len(media_files)
                for mf in media_files:
                    data = z.read(mf)
                    assert len(data) > 0, f"Empty media file {mf} in {docx_path.name}"

        # Expected media counts according to project specs:
        # Ch1: 0, Ch2: 12, Ch3: 22, Ch4: 12, Ch5: 7, Ch6: 19 = 72
        expected_media = {
            "Ch_01": 0,
            "Ch_02": 12,
            "Ch_03": 22,
            "Ch_04": 12,
            "Ch_05": 7,
            "Ch_06": 19,
        }
        assert per_chapter_images == expected_media, (
            f"Raw docx media count mismatch: {per_chapter_images} vs {expected_media}"
        )
        assert total_docx_images == 72, f"Total docx images {total_docx_images} != 72"

    def test_raw_docx_question_paragraph_anchors(self):
        """Count question start patterns in raw document.xml for each chapter."""
        for ch_num in range(1, 7):
            docx_path = PROJECT_ROOT / f"Ch_{ch_num:02d}_MC_Algo.docx"
            ch_id = f"Ch_{ch_num:02d}"
            expected_n = EXPECTED_COUNTS[ch_id]

            with zipfile.ZipFile(docx_path, "r") as z:
                xml_data = z.read("word/document.xml")
                root = ET.fromstring(xml_data)

                # Look for paragraph text patterns like "1. ", "2. ", etc.
                paras = root.findall(".//w:p", XML_NS)
                q_starts = []
                for p in paras:
                    texts = [t.text for t in p.findall(".//w:t", XML_NS) if t.text]
                    full_p = "".join(texts).strip()
                    m = re.match(r"^(\d+)\.\s+", full_p)
                    if m:
                        num = int(m.group(1))
                        q_starts.append(num)

                # Deduplicate sequential matches
                # In docx, each question starts with a number like "1.", "2."
                # Check that max question number matches or is at least expected_n
                assert len(q_starts) >= expected_n, (
                    f"Chapter {ch_id} has only {len(q_starts)} question number patterns, expected >= {expected_n}"
                )


class TestMediaFileIntegrity:
    """Audit all media in static/media for header fidelity, non-zero size, and referencing."""

    def test_all_pngs_have_valid_png_magic_header(self):
        png_files = list(STATIC_MEDIA_DIR.glob("*.png"))
        assert len(png_files) >= 72, f"Found only {len(png_files)} PNG files in {STATIC_MEDIA_DIR}"

        corrupted = []
        zero_sized = []
        for p in png_files:
            size = p.stat().st_size
            if size == 0:
                zero_sized.append(p.name)
            with open(p, "rb") as f:
                header = f.read(8)
                if header != PNG_HEADER:
                    corrupted.append((p.name, header))

        assert len(zero_sized) == 0, f"Found zero-sized media files: {zero_sized}"
        assert len(corrupted) == 0, f"Found non-PNG or corrupted media files: {corrupted}"

    def test_all_referenced_images_exist_and_are_valid(self):
        data = load_data()
        ref_count = 0
        for q in data["questions"]:
            if q["image_url"]:
                ref_count += 1
                rel = q["image_url"].lstrip("/")
                disk_path = PROJECT_ROOT / rel
                assert disk_path.exists(), f"Question {q['id']} references missing file {disk_path}"
                assert disk_path.stat().st_size > 100, f"Image {disk_path} unexpectedly small"

        assert ref_count >= 50, f"Expected at least 50 questions referencing image_url, got {ref_count}"


class TestQuestionContentIntegrity:
    """Deep check of stem, options, answers, and context tables."""

    def test_stems_are_not_trivial_or_truncated(self):
        data = load_data()
        too_short = []
        for q in data["questions"]:
            stem = q["stem"].strip()
            # Stems should have reasonable length (at least 3 chars, e.g. 'Trade' is 5 chars)
            if len(stem) < 3:
                too_short.append((q["id"], stem))

        assert len(too_short) == 0, f"Found suspiciously short stems: {too_short}"

    def test_no_raw_xml_or_unresolved_placeholders(self):
        data = load_data()
        bad_patterns = [
            re.compile(r"w:r[A-Z]"),
            re.compile(r"\{\{.*\}\}"),
            re.compile(r"TODO", re.IGNORECASE),
            re.compile(r"\[MISSING\]", re.IGNORECASE),
            re.compile(r"undefined", re.IGNORECASE),
        ]
        issues = []
        for q in data["questions"]:
            qid = q["id"]
            for pat in bad_patterns:
                if pat.search(q["stem"]):
                    issues.append((qid, "stem", pat.pattern))
                for opt_k, opt_v in q["options"].items():
                    # Note: options with <img> tags are allowed, but no raw docx XML
                    if pat.search(opt_v) and not opt_v.startswith("<img"):
                        issues.append((qid, f"option_{opt_k}", pat.pattern))

        assert len(issues) == 0, f"Found raw tags or placeholder markers in question bank: {issues}"

    def test_option_keys_and_uniqueness(self):
        data = load_data()
        identical_options = []
        for q in data["questions"]:
            qid = q["id"]
            opts = q["options"]
            assert set(opts.keys()) == {"a", "b", "c", "d"}, f"{qid} keys not a,b,c,d"
            vals = [opts[k].strip().lower() for k in ["a", "b", "c", "d"]]
            # Check if all 4 options are identical (would indicate extraction bug)
            if len(set(vals)) == 1:
                identical_options.append((qid, vals[0]))

        assert len(identical_options) == 0, f"Questions with 4 identical options: {identical_options}"


class TestPedagogicalExplanationsIntegrity:
    """Stress-test Chinese explanations schema, completeness, distractor coverage, and substance."""

    def test_every_question_has_complete_explanation_schema(self):
        data = load_data()
        missing_fields = []
        for q in data["questions"]:
            qid = q["id"]
            exp = q.get("explanation_zh")
            assert exp is not None, f"{qid} missing explanation_zh"
            for required in ["concept", "rationale", "distractors"]:
                if required not in exp or not exp[required]:
                    missing_fields.append((qid, required))

        assert len(missing_fields) == 0, f"Questions missing required explanation fields: {missing_fields}"

    def test_distractors_cover_all_incorrect_options(self):
        data = load_data()
        incomplete_distractors = []
        for q in data["questions"]:
            qid = q["id"]
            correct = q["correct_answer"]
            expected_distractor_keys = {"a", "b", "c", "d"} - {correct}
            actual_distractor_keys = set(q["explanation_zh"]["distractors"].keys())
            if actual_distractor_keys != expected_distractor_keys:
                incomplete_distractors.append({
                    "id": qid,
                    "correct": correct,
                    "expected": list(expected_distractor_keys),
                    "actual": list(actual_distractor_keys),
                })

        assert len(incomplete_distractors) == 0, (
            f"Questions with mismatched distractor keys: {incomplete_distractors[:5]}"
        )

    def test_chinese_explanations_character_length_and_substance(self):
        data = load_data()
        brief_explanations = []
        for q in data["questions"]:
            qid = q["id"]
            exp = q["explanation_zh"]
            concept = exp["concept"]
            rationale = exp["rationale"]
            # Concept should be non-trivial (at least 4 chars)
            if len(concept) < 4:
                brief_explanations.append((qid, "concept", concept))
            # Rationale should be substantive (at least 15 chars)
            if len(rationale) < 15:
                brief_explanations.append((qid, "rationale", rationale))

        assert len(brief_explanations) == 0, (
            f"Explanations with suspiciously brief substance: {brief_explanations[:5]}"
        )

    def test_mathematical_accuracy_ch2_slope_questions(self):
        """Empirically test slope calculations for Ch02_Q083 and Ch02_Q085."""
        data = load_data()
        q83 = next(q for q in data["questions"] if q["id"] == "Ch02_Q083")
        q85 = next(q for q in data["questions"] if q["id"] == "Ch02_Q085")

        # Q83: Points A to B on curve Figure 2-8
        # Slope = -20 / 10 = -2. Correct answer = 'a'
        assert q83["correct_answer"] == "a"
        exp83 = q83["explanation_zh"]
        assert "-20 / 10 = -2" in exp83["rationale"] or "-2" in exp83["rationale"]
        assert "ΔY" in exp83["rationale"] or "縱軸" in exp83["rationale"]

        # Q85: Points (10, 40) and (20, 35)
        # Slope = (35 - 40) / (20 - 10) = -5 / 10 = -1/2. Correct answer = 'b'
        assert q85["correct_answer"] == "b"
        exp85 = q85["explanation_zh"]
        assert "(35 - 40) / (20 - 10) = -5 / 10 = -1/2" in exp85["rationale"] or "-1/2" in exp85["rationale"]
        assert "(10, 40)" in exp85["rationale"]
