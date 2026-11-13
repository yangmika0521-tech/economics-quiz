"""Offline & Batch Traditional Chinese Translation Generator for Economics Question Bank.

Generates `data/translations_zh.json` containing Traditional Chinese translations
for all 585 questions (`stem_zh`, `context_table_zh`, and `options_zh` for a/b/c/d).
Strictly excludes `correct_answer` and `explanation_zh` to guarantee zero answer leakage
during Practice Mode translation.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MOZHI_INSTANCES = [
    "https://mozhi.aryak.me",
    "https://mozhi.adminforge.de",
    "https://mozhi.pussthecat.org",
]

SEP_TOKEN = "[[[SEP]]]"

# Taiwan Mankiw Economics Terminology Refinements (Post-processing)
ECON_TERM_REFINEMENTS: List[Tuple[str, str]] = [
    ("生產可能性邊界", "生產可能曲線 (PPF)"),
    ("生產可能性曲線", "生產可能曲線 (PPF)"),
    ("生產可能邊界", "生產可能曲線 (PPF)"),
    ("比較優勢", "比較利益（比較優勢）"),
    ("絕對優勢", "絕對利益（絕對優勢）"),
    ("機會成本", "機會成本"),
    ("價格天花板", "價格上限 (Price Ceiling)"),
    ("價格地板", "價格下限 (Price Floor)"),
    ("具有約束力", "具約束力 (Binding)"),
    ("有約束力", "具約束力 (Binding)"),
    ("約束力的", "具約束力的 (Binding)"),
    ("正常商品", "正常財 (Normal Good)"),
    ("劣質商品", "劣等財 (Inferior Good)"),
    ("劣等商品", "劣等財 (Inferior Good)"),
    ("低檔商品", "劣等財 (Inferior Good)"),
    ("普通商品", "正常財 (Normal Good)"),
    ("需求價格彈性", "需求價格彈性"),
    ("供給價格彈性", "供給價格彈性"),
    ("交叉價格彈性", "交叉價格彈性"),
    ("收入彈性", "所得彈性"),
    ("稅收歸宿", "租稅歸宿"),
    ("稅負歸宿", "租稅歸宿"),
    ("循環流量圖", "循環流向圖"),
    ("看不見的手", "看不見的手"),
    ("市場出清", "市場結清"),
]


def postprocess_econ_zh(text_en: str, text_zh: str) -> str:
    """Refines translated Traditional Chinese text with Taiwan Economics terminology."""
    if not text_zh:
        return text_en
    res = text_zh.strip()
    for src, dst in ECON_TERM_REFINEMENTS:
        if src in res and dst not in res:
            res = res.replace(src, dst)
    return res


def is_translatable_cell(cell: str) -> bool:
    """Checks if a Markdown table cell contains English words that should be translated."""
    s = cell.strip()
    if not s or re.match(r"^:?-+:?$", s):
        return False
    # Pure numbers, currency, percentages, question marks
    if re.match(r"^[\d,.\s$%?+\-/()]+$", s):
        return False
    # Contains at least 2 consecutive ASCII letters
    return bool(re.search(r"[A-Za-z]{2,}", s))


def translate_single_or_batch_api(payload: str, attempt_idx: int = 0) -> Optional[str]:
    """Calls Mozhi DuckDuckGo translation API (en -> zh-TW) with automatic instance rotation."""
    for retry in range(6):
        inst = MOZHI_INSTANCES[(attempt_idx + retry) % len(MOZHI_INSTANCES)]
        url = (
            f"{inst}/api/translate?engine=duckduckgo&from=en&to=zh-TW&text="
            + urllib.parse.quote(payload)
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                translated = data.get("translated-text")
                if translated and isinstance(translated, str):
                    return translated.strip()
        except Exception:
            time.sleep(0.35 * (retry + 1))
    return None


def translate_batch(batch_idx: int, items: List[str]) -> Dict[str, str]:
    """Translates a list of English strings (<= 850 chars total) and maps each to zh-TW."""
    result: Dict[str, str] = {}
    if not items:
        return result

    payload = f"\n{SEP_TOKEN}\n".join(items)
    translated_raw = translate_single_or_batch_api(payload, batch_idx)

    if translated_raw:
        parts = [p.strip() for p in translated_raw.split(SEP_TOKEN)]
        if len(parts) == len(items):
            for orig, trans in zip(items, parts):
                result[orig] = postprocess_econ_zh(orig, trans)
            return result

    # Fallback: translate individually if separator count mismatched
    for idx, orig in enumerate(items):
        trans = translate_single_or_batch_api(orig, batch_idx + idx)
        if trans:
            # Clean any leftover separator token just in case
            trans = trans.replace(SEP_TOKEN, "").strip()
            result[orig] = postprocess_econ_zh(orig, trans)
        else:
            result[orig] = orig
    return result


def translate_markdown_table(md_text: str, trans_map: Dict[str, str]) -> str:
    """Translates captions, headers, and text cells of a Markdown table using trans_map."""
    if not md_text:
        return md_text

    out_lines: List[str] = []
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        if not line:
            out_lines.append("")
            continue

        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line[1:-1].split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                out_lines.append(line)
                continue
            new_cells = []
            for c in cells:
                if is_translatable_cell(c):
                    new_cells.append(trans_map.get(c, c))
                else:
                    new_cells.append(c)
            out_lines.append("| " + " | ".join(new_cells) + " |")
        else:
            if is_translatable_cell(line):
                out_lines.append(trans_map.get(line, line))
            else:
                out_lines.append(line)

    return "\n".join(out_lines)


def build_translations_file(
    questions_path: str = "data/questions.json",
    output_path: str = "data/translations_zh.json",
) -> None:
    """Builds and saves `data/translations_zh.json` for all 585 questions."""
    q_file = Path(questions_path)
    out_file = Path(output_path)

    data = json.loads(q_file.read_text(encoding="utf-8"))
    questions = data.get("questions", [])

    # Load existing translation cache if present
    existing_q_map: Dict[str, dict] = {}
    trans_map: Dict[str, str] = {}
    if out_file.exists():
        try:
            existing_data = json.loads(out_file.read_text(encoding="utf-8"))
            existing_q_map = existing_data.get("translations", {})
        except Exception:
            pass

    # Collect all unique strings needing translation
    unique_strings_set = set()
    for q in questions:
        stem = q.get("stem", "").strip()
        if stem:
            unique_strings_set.add(stem)

        for opt_key, opt_val in (q.get("options") or {}).items():
            if opt_val and "<img" not in opt_val:
                unique_strings_set.add(opt_val.strip())

        ctx_table = q.get("context_table")
        if ctx_table:
            for raw_line in ctx_table.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("|") and line.endswith("|"):
                    cells = [c.strip() for c in line[1:-1].split("|")]
                    if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                        continue
                    for c in cells:
                        if is_translatable_cell(c):
                            unique_strings_set.add(c)
                else:
                    if is_translatable_cell(line):
                        unique_strings_set.add(line)

    unique_strings = sorted(unique_strings_set)
    print(f"[Translation Generator] Total unique strings to translate: {len(unique_strings)}")

    # Group into batches of max 780 characters (including separator)
    batches: List[List[str]] = []
    current_batch: List[str] = []
    current_len = 0

    for s in unique_strings:
        add_len = len(s) + len(SEP_TOKEN) + 2
        if current_batch and (current_len + add_len > 780 or len(current_batch) >= 10):
            batches.append(current_batch)
            current_batch = [s]
            current_len = len(s)
        else:
            current_batch.append(s)
            current_len += add_len
    if current_batch:
        batches.append(current_batch)

    print(f"[Translation Generator] Packed into {len(batches)} batches. Translating...")

    completed = 0
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_idx = {
            executor.submit(translate_batch, idx, batch): idx
            for idx, batch in enumerate(batches)
        }
        for future in as_completed(future_to_idx):
            batch_res = future.result()
            trans_map.update(batch_res)
            completed += 1
            if completed % 25 == 0 or completed == len(batches):
                print(f"  Progress: {completed}/{len(batches)} batches ({len(trans_map)} strings)")

    # Assemble per-question translation dictionary (strictly NO answer and NO explanation)
    translations_by_qid: Dict[str, dict] = {}
    for q in questions:
        qid = q["id"]
        stem_en = q.get("stem", "").strip()
        stem_zh = trans_map.get(stem_en, stem_en)

        options_zh: Dict[str, str] = {}
        for opt_key in ["a", "b", "c", "d"]:
            opt_val = (q.get("options") or {}).get(opt_key, "")
            if not opt_val:
                options_zh[opt_key] = ""
            elif "<img" in opt_val:
                # Preserve pure diagram options intact
                options_zh[opt_key] = opt_val
            else:
                options_zh[opt_key] = trans_map.get(opt_val.strip(), opt_val)

        ctx_table = q.get("context_table")
        ctx_table_zh = translate_markdown_table(ctx_table, trans_map) if ctx_table else None

        translations_by_qid[qid] = {
            "stem_zh": stem_zh,
            "context_table_zh": ctx_table_zh,
            "options_zh": options_zh,
        }

    output_payload = {
        "version": "1.0",
        "total_questions": len(translations_by_qid),
        "translations": translations_by_qid,
    }

    out_file.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Translation Generator] Saved {len(translations_by_qid)} question translations to {out_file}")


if __name__ == "__main__":
    build_translations_file()
