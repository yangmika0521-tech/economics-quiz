"""DOCX Ingestion Pipeline for Economics Question Bank.

Parses all 6 chapter files (Ch_01_MC_Algo.docx ~ Ch_06_MC_Algo.docx), extracts 72 diagrams
to static/media/, dynamically parses nested question tables, binds context figures & tables,
enriches each question with comprehensive Traditional Chinese pedagogical explanations,
and outputs a validated data/questions.json adhering to Pydantic v2 schemas.
"""

import json
import os
import sys
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import docx
from PIL import Image

from app.models import Chapter, Question, QuestionBank
from app.explanation_generator import generate_explanation
STATIC_MEDIA_DIR = PROJECT_ROOT / "static" / "media"
DATA_DIR = PROJECT_ROOT / "data"
QUESTIONS_JSON_PATH = DATA_DIR / "questions.json"

CHAPTER_METADATA = [
    {
        "id": "Ch_01",
        "number": 1,
        "filename": "Ch_01_MC_Algo.docx",
        "title_en": "Ten Principles of Economics",
        "title_zh": "經濟學十大原理",
        "expected_questions": 113,
    },
    {
        "id": "Ch_02",
        "number": 2,
        "filename": "Ch_02_MC_Algo.docx",
        "title_en": "Thinking Like an Economist",
        "title_zh": "像經濟學家一樣思考",
        "expected_questions": 87,
    },
    {
        "id": "Ch_03",
        "number": 3,
        "filename": "Ch_03_MC_Algo.docx",
        "title_en": "Interdependence and the Gains from Trade",
        "title_zh": "相互依存性與貿易利得",
        "expected_questions": 72,
    },
    {
        "id": "Ch_04",
        "number": 4,
        "filename": "Ch_04_MC_Algo.docx",
        "title_en": "The Market Forces of Supply and Demand",
        "title_zh": "供給與需求的市場力量",
        "expected_questions": 124,
    },
    {
        "id": "Ch_05",
        "number": 5,
        "filename": "Ch_05_MC_Algo.docx",
        "title_en": "Elasticity and Its Application",
        "title_zh": "彈性及其應用",
        "expected_questions": 86,
    },
    {
        "id": "Ch_06",
        "number": 6,
        "filename": "Ch_06_MC_Algo.docx",
        "title_en": "Supply, Demand, and Government Policies",
        "title_zh": "供給、需求與政府政策",
        "expected_questions": 103,
    },
]

MEDIA_MANIFEST = [
    # CH 2 (12 items)
    ('Ch_02_MC_Algo.docx', 'image1.png', 'ch02_fig01.png'),
    ('Ch_02_MC_Algo.docx', 'image2.png', 'ch02_fig02.png'),
    ('Ch_02_MC_Algo.docx', 'image3.png', 'ch02_fig03.png'),
    ('Ch_02_MC_Algo.docx', 'image4.png', 'ch02_fig04_a.png'),
    ('Ch_02_MC_Algo.docx', 'image5.png', 'ch02_fig04_b.png'),
    ('Ch_02_MC_Algo.docx', 'image6.png', 'ch02_fig05.png'),
    ('Ch_02_MC_Algo.docx', 'image7.png', 'ch02_fig06.png'),
    ('Ch_02_MC_Algo.docx', 'image8.png', 'ch02_inline_half.png'),
    ('Ch_02_MC_Algo.docx', 'image9.png', 'ch02_fig07.png'),
    ('Ch_02_MC_Algo.docx', 'image10.png', 'ch02_fig08.png'),
    ('Ch_02_MC_Algo.docx', 'image11.png', 'ch02_inline_neg_half.png'),
    ('Ch_02_MC_Algo.docx', 'image12.png', 'ch02_fig09.png'),
    # CH 3 (22 items)
    ('Ch_03_MC_Algo.docx', 'image1.png', 'ch03_q014_opt_a.png'),
    ('Ch_03_MC_Algo.docx', 'image2.png', 'ch03_q014_opt_b.png'),
    ('Ch_03_MC_Algo.docx', 'image3.png', 'ch03_q014_opt_c.png'),
    ('Ch_03_MC_Algo.docx', 'image4.png', 'ch03_q014_opt_d.png'),
    ('Ch_03_MC_Algo.docx', 'image5.png', 'ch03_q016_opt_a1.png'),
    ('Ch_03_MC_Algo.docx', 'image6.png', 'ch03_q016_opt_a2.png'),
    ('Ch_03_MC_Algo.docx', 'image7.png', 'ch03_q016_opt_b1.png'),
    ('Ch_03_MC_Algo.docx', 'image8.png', 'ch03_q016_opt_b2.png'),
    ('Ch_03_MC_Algo.docx', 'image9.png', 'ch03_q016_opt_c1.png'),
    ('Ch_03_MC_Algo.docx', 'image10.png', 'ch03_q016_opt_c2.png'),
    ('Ch_03_MC_Algo.docx', 'image11.png', 'ch03_q016_opt_d1.png'),
    ('Ch_03_MC_Algo.docx', 'image12.png', 'ch03_q016_opt_d2.png'),
    ('Ch_03_MC_Algo.docx', 'image13.png', 'ch03_fig01_a.png'),
    ('Ch_03_MC_Algo.docx', 'image14.png', 'ch03_fig01_b.png'),
    ('Ch_03_MC_Algo.docx', 'image15.png', 'ch03_fig02.png'),
    ('Ch_03_MC_Algo.docx', 'image16.png', 'ch03_inline_frac_a.png'),
    ('Ch_03_MC_Algo.docx', 'image17.png', 'ch03_inline_frac_b.png'),
    ('Ch_03_MC_Algo.docx', 'image18.png', 'ch03_fig03_a.png'),
    ('Ch_03_MC_Algo.docx', 'image19.png', 'ch03_fig03_b.png'),
    ('Ch_03_MC_Algo.docx', 'image20.png', 'ch03_fig04_a.png'),
    ('Ch_03_MC_Algo.docx', 'image21.png', 'ch03_fig04_b.png'),
    ('Ch_03_MC_Algo.docx', 'image22.png', 'ch03_fig05.png'),
    # CH 4 (12 items)
    ('Ch_04_MC_Algo.docx', 'image1.png', 'ch04_fig01.png'),
    ('Ch_04_MC_Algo.docx', 'image2.png', 'ch04_fig02_c1.png'),
    ('Ch_04_MC_Algo.docx', 'image3.png', 'ch04_fig02_c2.png'),
    ('Ch_04_MC_Algo.docx', 'image4.png', 'ch04_fig03.png'),
    ('Ch_04_MC_Algo.docx', 'image5.png', 'ch04_fig04.png'),
    ('Ch_04_MC_Algo.docx', 'image6.png', 'ch04_fig05_fa.png'),
    ('Ch_04_MC_Algo.docx', 'image7.png', 'ch04_fig05_fb.png'),
    ('Ch_04_MC_Algo.docx', 'image8.png', 'ch04_fig06.png'),
    ('Ch_04_MC_Algo.docx', 'image9.png', 'ch04_fig07.png'),
    ('Ch_04_MC_Algo.docx', 'image10.png', 'ch04_fig08.png'),
    ('Ch_04_MC_Algo.docx', 'image11.png', 'ch04_fig09.png'),
    ('Ch_04_MC_Algo.docx', 'image12.png', 'ch04_fig10.png'),
    # CH 5 (7 items)
    ('Ch_05_MC_Algo.docx', 'image1.png', 'ch05_fig01.png'),
    ('Ch_05_MC_Algo.docx', 'image2.png', 'ch05_fig02.png'),
    ('Ch_05_MC_Algo.docx', 'image3.png', 'ch05_fig03.png'),
    ('Ch_05_MC_Algo.docx', 'image4.png', 'ch05_fig04.png'),
    ('Ch_05_MC_Algo.docx', 'image5.png', 'ch05_fig05.png'),
    ('Ch_05_MC_Algo.docx', 'image6.png', 'ch05_fig06.png'),
    ('Ch_05_MC_Algo.docx', 'image7.png', 'ch05_fig07.png'),
    # CH 6 (19 items)
    ('Ch_06_MC_Algo.docx', 'image1.png', 'ch06_fig01_a.png'),
    ('Ch_06_MC_Algo.docx', 'image2.png', 'ch06_fig01_b.png'),
    ('Ch_06_MC_Algo.docx', 'image3.png', 'ch06_fig02.png'),
    ('Ch_06_MC_Algo.docx', 'image4.png', 'ch06_fig03.png'),
    ('Ch_06_MC_Algo.docx', 'image5.png', 'ch06_fig04_a.png'),
    ('Ch_06_MC_Algo.docx', 'image6.png', 'ch06_fig04_b.png'),
    ('Ch_06_MC_Algo.docx', 'image7.png', 'ch06_fig05.png'),
    ('Ch_06_MC_Algo.docx', 'image8.png', 'ch06_fig06.png'),
    ('Ch_06_MC_Algo.docx', 'image9.png', 'ch06_fig07.png'),
    ('Ch_06_MC_Algo.docx', 'image10.png', 'ch06_fig08.png'),
    ('Ch_06_MC_Algo.docx', 'image11.png', 'ch06_fig09.png'),
    ('Ch_06_MC_Algo.docx', 'image12.png', 'ch06_fig10.png'),
    ('Ch_06_MC_Algo.docx', 'image13.png', 'ch06_fig11.png'),
    ('Ch_06_MC_Algo.docx', 'image14.png', 'ch06_fig12.png'),
    ('Ch_06_MC_Algo.docx', 'image15.png', 'ch06_fig13.png'),
    ('Ch_06_MC_Algo.docx', 'image16.png', 'ch06_fig14.png'),
    ('Ch_06_MC_Algo.docx', 'image17.png', 'ch06_fig15_a.png'),
    ('Ch_06_MC_Algo.docx', 'image18.png', 'ch06_fig15_b.png'),
    ('Ch_06_MC_Algo.docx', 'image19.png', 'ch06_fig15_c.png'),
]

MULTI_PANEL_COMPOSITES = [
    ('ch02_fig04.png', ['ch02_fig04_a.png', 'ch02_fig04_b.png']),
    ('ch03_fig01.png', ['ch03_fig01_a.png', 'ch03_fig01_b.png']),
    ('ch03_fig03.png', ['ch03_fig03_a.png', 'ch03_fig03_b.png']),
    ('ch03_fig04.png', ['ch03_fig04_a.png', 'ch03_fig04_b.png']),
    ('ch04_fig02.png', ['ch04_fig02_c1.png', 'ch04_fig02_c2.png']),
    ('ch04_fig05.png', ['ch04_fig05_fa.png', 'ch04_fig05_fb.png']),
    ('ch06_fig01.png', ['ch06_fig01_a.png', 'ch06_fig01_b.png']),
    ('ch06_fig04.png', ['ch06_fig04_a.png', 'ch06_fig04_b.png']),
    ('ch06_fig15.png', ['ch06_fig15_a.png', 'ch06_fig15_b.png', 'ch06_fig15_c.png']),
]

FIGURE_MAP: Dict[str, Dict[str, str]] = {
    "Ch_02": {
        "figure 2-1": "/static/media/ch02_fig01.png",
        "figure 2-2": "/static/media/ch02_fig02.png",
        "figure 2-3": "/static/media/ch02_fig03.png",
        "figure 2-4": "/static/media/ch02_fig04.png",
        "figure 2-4, graph (a)": "/static/media/ch02_fig04_a.png",
        "figure 2-4, graph (b)": "/static/media/ch02_fig04_b.png",
        "figure 2-5": "/static/media/ch02_fig05.png",
        "figure 2-6": "/static/media/ch02_fig06.png",
        "figure 2-7": "/static/media/ch02_fig07.png",
        "figure 2-8": "/static/media/ch02_fig08.png",
        "figure 2-9": "/static/media/ch02_fig09.png",
    },
    "Ch_03": {
        "figure 3-1": "/static/media/ch03_fig01.png",
        "figure 3-1, graph (a)": "/static/media/ch03_fig01_a.png",
        "figure 3-1, graph (b)": "/static/media/ch03_fig01_b.png",
        "figure 3-2": "/static/media/ch03_fig02.png",
        "figure 3-3": "/static/media/ch03_fig03.png",
        "figure 3-3, graph (a)": "/static/media/ch03_fig03_a.png",
        "figure 3-3, graph (b)": "/static/media/ch03_fig03_b.png",
        "figure 3-4": "/static/media/ch03_fig04.png",
        "figure 3-4, graph (a)": "/static/media/ch03_fig04_a.png",
        "figure 3-4, graph (b)": "/static/media/ch03_fig04_b.png",
        "figure 3-5": "/static/media/ch03_fig05.png",
    },
    "Ch_04": {
        "figure 4-1": "/static/media/ch04_fig01.png",
        "figure 4-2": "/static/media/ch04_fig02.png",
        "figure 4-3": "/static/media/ch04_fig03.png",
        "figure 4-4": "/static/media/ch04_fig04.png",
        "figure 4-5": "/static/media/ch04_fig05.png",
        "figure 4-6": "/static/media/ch04_fig06.png",
        "figure 4-7": "/static/media/ch04_fig07.png",
        "figure 4-8": "/static/media/ch04_fig08.png",
        "figure 4-9": "/static/media/ch04_fig09.png",
        "figure 4-10": "/static/media/ch04_fig10.png",
    },
    "Ch_05": {
        "figure 5-1": "/static/media/ch05_fig01.png",
        "figure 5-2": "/static/media/ch05_fig02.png",
        "figure 5-3": "/static/media/ch05_fig03.png",
        "figure 5-4": "/static/media/ch05_fig04.png",
        "figure 5-5": "/static/media/ch05_fig05.png",
        "figure 5-6": "/static/media/ch05_fig06.png",
        "figure 5-7": "/static/media/ch05_fig07.png",
    },
    "Ch_06": {
        "figure 6-1": "/static/media/ch06_fig01.png",
        "figure 6-1, graph (a)": "/static/media/ch06_fig01_a.png",
        "figure 6-1, graph (b)": "/static/media/ch06_fig01_b.png",
        "figure 6-2": "/static/media/ch06_fig02.png",
        "figure 6-3": "/static/media/ch06_fig03.png",
        "figure 6-4": "/static/media/ch06_fig04.png",
        "figure 6-4, graph (a)": "/static/media/ch06_fig04_a.png",
        "figure 6-4, graph (b)": "/static/media/ch06_fig04_b.png",
        "figure 6-5": "/static/media/ch06_fig05.png",
        "figure 6-6": "/static/media/ch06_fig06.png",
        "figure 6-7": "/static/media/ch06_fig07.png",
        "figure 6-8": "/static/media/ch06_fig08.png",
        "figure 6-9": "/static/media/ch06_fig09.png",
        "figure 6-10": "/static/media/ch06_fig10.png",
        "figure 6-11": "/static/media/ch06_fig11.png",
        "figure 6-12": "/static/media/ch06_fig12.png",
        "figure 6-13": "/static/media/ch06_fig13.png",
        "figure 6-14": "/static/media/ch06_fig14.png",
        "figure 6-15": "/static/media/ch06_fig15.png",
        "figure 6-15, graph (a)": "/static/media/ch06_fig15_a.png",
        "figure 6-15, graph (b)": "/static/media/ch06_fig15_b.png",
        "figure 6-15, graph (c)": "/static/media/ch06_fig15_c.png",
    }
}


# ============================================================================
# Media Extraction & Composite Stitching
# ============================================================================

def extract_all_media() -> int:
    """Extracts all 72 source images to static/media/ and generates composite images."""
    STATIC_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for docx_filename, src_name, dst_name in MEDIA_MANIFEST:
        docx_path = PROJECT_ROOT / docx_filename
        assert docx_path.exists(), f"Source DOCX {docx_filename} missing"
        with zipfile.ZipFile(docx_path) as z:
            data = z.read(f"word/media/{src_name}")
            (STATIC_MEDIA_DIR / dst_name).write_bytes(data)
            count += 1

    # Generate multi-panel composites
    for comp_name, parts in MULTI_PANEL_COMPOSITES:
        part_paths = [STATIC_MEDIA_DIR / p for p in parts]
        if all(p.exists() for p in part_paths):
            imgs = [Image.open(p) for p in part_paths]
            total_w = sum(im.width for im in imgs) + 20 * (len(imgs) - 1)
            max_h = max(im.height for im in imgs)
            comp = Image.new("RGB", (total_w, max_h), (255, 255, 255))
            x_offset = 0
            for im in imgs:
                comp.paste(im, (x_offset, (max_h - im.height) // 2))
                x_offset += im.width + 20
            comp.save(STATIC_MEDIA_DIR / comp_name)

    return count


# ============================================================================
# Context Tables and Scenarios Parser
# ============================================================================

def clean_text_cell(text: str) -> str:
    """Cleans up raw cell text from Word."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("\u200b", "")).strip()


def format_nested_table_as_markdown(nested_table) -> str:
    """Converts a Word table into a GitHub-flavored Markdown table."""
    rows = []
    for r in nested_table.rows:
        row_vals = [clean_text_cell(c.text) for c in r.cells]
        # Ignore completely empty rows
        if any(row_vals):
            rows.append(row_vals)

    if not rows:
        return ""

    # Determine max cols
    max_cols = max(len(r) for r in rows)
    # Pad rows to max_cols
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    header = rows[0]
    separator = ["---"] * max_cols
    body = rows[1:]

    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(separator) + " |")
    for b in body:
        lines.append("| " + " | ".join(b) + " |")
    return "\n".join(lines)


def build_context_registry(doc: docx.Document, chapter_id: str) -> Dict[str, str]:
    """Scans all non-question tables to catalog context tables and scenarios as Markdown."""
    registry = {}
    for tbl in doc.tables:
        cell = tbl.cell(0, 0)
        p_texts = [clean_text_cell(p.text) for p in cell.paragraphs if clean_text_cell(p.text)]
        full_p = "\n\n".join(p_texts)

        # Check if question table
        if re.match(r"^\s*\d+[\.\s\xa0]", full_p):
            continue
        # Check if header table
        if "Multiple Choice" in full_p:
            continue

        # Look for Table X-Y or Scenario X-Y
        m_tbl = re.search(r"\b(Table\s+\d+[-–]\d+)\b", full_p, re.IGNORECASE)
        m_scen = re.search(r"\b(Scenario\s+\d+[-–]\d+)\b", full_p, re.IGNORECASE)

        if m_tbl or m_scen:
            key = (m_tbl.group(1) if m_tbl else m_scen.group(1)).lower().replace("–", "-")
            md_parts = [full_p]
            for nt in cell.tables:
                table_md = format_nested_table_as_markdown(nt)
                if table_md:
                    md_parts.append(table_md)
            registry[key] = "\n\n".join(md_parts)

    return registry


# ============================================================================
# Question Table Parser
# ============================================================================

def parse_question_outer_cell(
    cell,
    q_num: int,
    chapter_id: str,
    context_registry: Dict[str, str]
) -> Question:
    """Parses a single question outer cell into a complete Question domain model."""
    nested_tables = cell.tables
    assert len(nested_tables) >= 2, f"Expected at least 2 nested tables in {chapter_id} Q{q_num}"

    # 1. Dynamically locate options table, answer table, and any in-stem table
    ans_tbl = None
    opt_tbl = None
    instem_tbls = []

    for nt in nested_tables:
        t_text = " ".join(c.text for row in nt.rows for c in row.cells)
        if "ANSWER:" in t_text:
            ans_tbl = nt
        elif any(re.match(r"^[a-d]\.", c.text.strip()) for row in nt.rows for c in row.cells):
            opt_tbl = nt
        else:
            instem_tbls.append(nt)

    assert ans_tbl is not None, f"Missing answer table in {chapter_id} Q{q_num}"
    assert opt_tbl is not None, f"Missing options table in {chapter_id} Q{q_num}"

    # 2. Extract Canonical Answer
    ans_text = " ".join(clean_text_cell(c.text) for row in ans_tbl.rows for c in row.cells)
    ans_match = re.search(r"ANSWER:\s*([a-d])", ans_text, re.IGNORECASE)
    assert ans_match, f"Cannot parse answer letter from '{ans_text}' in {chapter_id} Q{q_num}"
    correct_answer = ans_match.group(1).lower()

    # 3. Extract Options
    options = {}
    for r in opt_tbl.rows:
        cells = r.cells
        opt_key = None
        opt_val = ""
        for idx, c in enumerate(cells):
            c_text = clean_text_cell(c.text)
            km = re.match(r"^([a-d])\.", c_text, re.IGNORECASE)
            if km:
                opt_key = km.group(1).lower()
                # value is in the next cell
                if idx + 1 < len(cells):
                    opt_val = clean_text_cell(cells[idx + 1].text)
                break
        if opt_key:
            options[opt_key] = opt_val

    # Handle known option special cases (diagram options, inline fractions)
    if chapter_id == "Ch_02":
        if q_num == 52:
            options["a"] = "the slope of the production possibilities frontier, or 1/2 of a sofa."
            options["b"] = "the reciprocal of the slope of the production possibilities frontier, or 2 sofas."
            options["c"] = "the reciprocal of the slope of the production possibilities frontier, or 1/2 of a sofa."
            options["d"] = "the slope of the production possibilities frontier, or 2 sofas."
        elif q_num == 83:
            options["a"] = "–2."
            options["b"] = "2."
            options["c"] = "-1/2."
            options["d"] = "1/2."
        elif q_num == 85:
            options["a"] = "1/2."
            options["b"] = "-1/2."
            options["c"] = "–2."
            options["d"] = "2."

    elif chapter_id == "Ch_03":
        if q_num == 14:
            options["a"] = '<img src="/static/media/ch03_q014_opt_a.png" alt="Option A diagram" class="option-img" />'
            options["b"] = '<img src="/static/media/ch03_q014_opt_b.png" alt="Option B diagram" class="option-img" />'
            options["c"] = '<img src="/static/media/ch03_q014_opt_c.png" alt="Option C diagram" class="option-img" />'
            options["d"] = '<img src="/static/media/ch03_q014_opt_d.png" alt="Option D diagram" class="option-img" />'
        elif q_num == 16:
            options["a"] = '<img src="/static/media/ch03_q016_opt_a1.png" alt="Kenya" class="option-img" /> <img src="/static/media/ch03_q016_opt_a2.png" alt="Peru" class="option-img" />'
            options["b"] = '<img src="/static/media/ch03_q016_opt_b1.png" alt="Kenya" class="option-img" /> <img src="/static/media/ch03_q016_opt_b2.png" alt="Peru" class="option-img" />'
            options["c"] = '<img src="/static/media/ch03_q016_opt_c1.png" alt="Kenya" class="option-img" /> <img src="/static/media/ch03_q016_opt_c2.png" alt="Peru" class="option-img" />'
            options["d"] = '<img src="/static/media/ch03_q016_opt_d1.png" alt="Kenya" class="option-img" /> <img src="/static/media/ch03_q016_opt_d2.png" alt="Peru" class="option-img" />'
        elif q_num == 30:
            options["a"] = "1/3 hour"
            options["b"] = "1/5 hour"
            options["c"] = "3 hours"
            options["d"] = "5 hours"

    # Verify all 4 options exist
    for opt in ["a", "b", "c", "d"]:
        assert opt in options and len(options[opt].strip()) > 0, (
            f"Question {chapter_id} Q{q_num} missing valid option '{opt}'"
        )

    # 4. Extract Question Stem
    p_texts = [clean_text_cell(p.text) for p in cell.paragraphs if clean_text_cell(p.text)]
    raw_stem = " ".join(p_texts)
    # Remove leading number prefix: "90. " -> ""
    clean_stem = re.sub(r"^\s*\d+[\.\s\xa0]+", "", raw_stem).strip()

    # Include in-stem table if present (e.g. Ch 4 Q90)
    if instem_tbls:
        instem_md = "\n\n" + format_nested_table_as_markdown(instem_tbls[0])
        clean_stem = clean_stem + instem_md

    # 5. Bind Figure Diagram (image_url)
    image_url = None
    fig_ref_found = None
    ch_fig_map = FIGURE_MAP.get(chapter_id, {})

    # Check for specific graph reference first, e.g. "Figure 2-4, Graph (a)"
    m_fig_spec = re.search(r"\b(Figure\s+\d+[-–]\d+)[,\s]+(Graph\s*\([a-c]\))", clean_stem, re.IGNORECASE)
    if m_fig_spec:
        spec_key = f"{m_fig_spec.group(1).lower().replace('–', '-')}, {m_fig_spec.group(2).lower()}"
        if spec_key in ch_fig_map:
            image_url = ch_fig_map[spec_key]
            fig_ref_found = m_fig_spec.group(1)

    if not image_url:
        m_fig = re.search(r"\b(Figure\s+\d+[-–]\d+)\b", clean_stem, re.IGNORECASE)
        if m_fig:
            fig_key = m_fig.group(1).lower().replace("–", "-")
            if fig_key in ch_fig_map:
                image_url = ch_fig_map[fig_key]
                fig_ref_found = m_fig.group(1)

    # 6. Bind Context Table or Scenario (context_table)
    context_table = None
    tbl_ref_found = None

    m_tbl = re.search(r"\b(Table\s+\d+[-–]\d+)\b", clean_stem, re.IGNORECASE)
    m_scen = re.search(r"\b(Scenario\s+\d+[-–]\d+)\b", clean_stem, re.IGNORECASE)

    if m_tbl:
        tbl_key = m_tbl.group(1).lower().replace("–", "-")
        if tbl_key in context_registry:
            context_table = context_registry[tbl_key]
            tbl_ref_found = m_tbl.group(1)
    elif m_scen:
        scen_key = m_scen.group(1).lower().replace("–", "-")
        if scen_key in context_registry:
            context_table = context_registry[scen_key]
            tbl_ref_found = m_scen.group(1)

    # 7. Generate Pedagogical Chinese Explanation
    q_id = f"{chapter_id.replace('_', '')}_Q{q_num:03d}"
    explanation_zh = generate_explanation(
        question_id=q_id,
        chapter_id=chapter_id,
        question_number=q_num,
        stem=clean_stem,
        options=options,
        correct_answer=correct_answer,
        fig_ref=fig_ref_found,
        tbl_ref=tbl_ref_found
    )

    return Question(
        id=q_id,
        chapter_id=chapter_id,
        question_number=q_num,
        stem=clean_stem,
        image_url=image_url,
        context_table=context_table,
        options=options,
        correct_answer=correct_answer,
        explanation_zh=explanation_zh
    )


# ============================================================================
# Main Ingestion Workflow
# ============================================================================

def ingest_all() -> QuestionBank:
    """Executes full question bank ingestion and writes data/questions.json."""
    print("=" * 70)
    print(">>> Starting Economics Question Bank Ingestion Pipeline")
    print("=" * 70)

    # 1. Media Extraction
    print("\n[Step 1/4] Extracting diagrams to static/media/...")
    media_count = extract_all_media()
    print(f" -> Successfully extracted {media_count} PNG diagrams and composite figures.")

    # 2. Ingest Chapters and Questions
    print("\n[Step 2/4] Parsing chapter DOCX files...")
    all_chapters: List[Chapter] = []
    all_questions: List[Question] = []

    for meta in CHAPTER_METADATA:
        ch_id = meta["id"]
        ch_num = meta["number"]
        filename = meta["filename"]
        docx_path = PROJECT_ROOT / filename
        assert docx_path.exists(), f"Source file {docx_path} not found"

        print(f" -> Parsing {ch_id}: {meta['title_en']} ({filename})...")
        doc = docx.Document(docx_path)

        # Pass 1: Build Context Registry for Table X-Y and Scenario X-Y
        context_reg = build_context_registry(doc, ch_id)

        # Pass 2: Extract Question Tables
        ch_questions: List[Question] = []
        for tbl in doc.tables:
            cell = tbl.cell(0, 0)
            p_texts = [clean_text_cell(p.text) for p in cell.paragraphs if clean_text_cell(p.text)]
            full_p = " ".join(p_texts)
            m = re.match(r"^\s*(\d+)[\.\s\xa0]", full_p)
            if m:
                q_num = int(m.group(1))
                q_obj = parse_question_outer_cell(
                    cell=cell,
                    q_num=q_num,
                    chapter_id=ch_id,
                    context_registry=context_reg
                )
                ch_questions.append(q_obj)

        expected = meta["expected_questions"]
        assert len(ch_questions) == expected, (
            f"{ch_id} question count mismatch: got {len(ch_questions)}, expected {expected}"
        )

        # Verify sequential numbering
        seq = [q.question_number for q in ch_questions]
        assert seq == list(range(1, expected + 1)), f"{ch_id} numbering is not strictly 1..{expected}"

        all_chapters.append(
            Chapter(
                id=ch_id,
                number=ch_num,
                title_en=meta["title_en"],
                title_zh=meta["title_zh"],
                total_questions=len(ch_questions)
            )
        )
        all_questions.extend(ch_questions)
        print(f"    Done: {len(ch_questions)} questions parsed cleanly.")

    # 3. Model Validation
    print("\n[Step 3/4] Validating full QuestionBank domain model with Pydantic v2...")
    bank = QuestionBank(chapters=all_chapters, questions=all_questions)
    # Strict validation
    validated_bank = QuestionBank.model_validate(bank.model_dump())
    assert len(validated_bank.questions) == 585, f"Expected 585 questions, got {len(validated_bank.questions)}"
    print(f" -> QuestionBank validated! Total chapters: {len(validated_bank.chapters)}, total questions: {len(validated_bank.questions)}")

    # 4. Serialize to data/questions.json
    print("\n[Step 4/4] Writing output to data/questions.json...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUESTIONS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(validated_bank.model_dump(), f, ensure_ascii=False, indent=2)

    file_size_kb = QUESTIONS_JSON_PATH.stat().st_size / 1024
    print(f" -> Ingestion complete! Saved to {QUESTIONS_JSON_PATH} ({file_size_kb:.1f} KB)")
    print("=" * 70)
    return validated_bank


if __name__ == "__main__":
    ingest_all()
