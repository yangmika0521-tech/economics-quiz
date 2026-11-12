# Test Infrastructure & Methodology: Economics Interactive Evaluation System

## 1. Overview & Testing Philosophy

This document defines the automated End-to-End (E2E) testing infrastructure for the **Economics Interactive Evaluation & Quiz Practice System**. The testing framework adheres to an opaque-box, contract-driven testing strategy designed to validate all functional, boundary, integration, and real-world workflow requirements specified in `ORIGINAL_REQUEST.md` and `PROJECT.md`.

### 1.1 Core Principles
1. **Opaque-Box Specification Verification**: Tests evaluate system behavior against requirements and interface contracts rather than internal implementation details.
2. **Oracle-Driven Validation**: The authoritative reference for data ingestion is derived directly from the canonical DOCX files (`Ch_01_MC_Algo.docx` through `Ch_06_MC_Algo.docx`).
3. **No Facade / No Mock Cheating**: All tests execute real validation logic. Hardcoded dummy results or evasive test passes are strictly prohibited and audited.
4. **Graceful Progressive Testability**: Tests support concurrent milestone development, executing available tiers immediately while providing clear skip/pending diagnostics for components currently in flight by other milestone workers.

---

## 2. Four-Tier Testing Hierarchy

The testing architecture is organized into four complementary verification tiers:

```
+--------------------------------------------------------------------------+
| Tier 4: Real-World Application Workflows                                 |
| Full Quiz Flow: Ingestion -> Session Setup -> Submission -> Diagnostics  |
+--------------------------------------------------------------------------+
| Tier 3: Cross-Feature Combinations & State Transitions                   |
| Multi-chapter sampling + Diagram binding + Practice vs Exam modes        |
+--------------------------------------------------------------------------+
| Tier 2: Boundary, Limit & Corner Cases                                  |
| Clamping (0, 1, max, negative, overflow), 0% vs 100% scores, invalid IDs |
+--------------------------------------------------------------------------+
| Tier 1: Feature Coverage & Contract Integrity                            |
| 585 DOCX Questions, 4 Options A-D, Canonical Keys, Chinese Explanations  |
+--------------------------------------------------------------------------+
```

### 2.1 Tier 1: Feature Coverage (Unit & Data Integrity)
- **DOCX Ingestion Integrity**:
  - Total question count exactly matches 585 across 6 chapters.
  - Chapter distribution: Ch 01 (113), Ch 02 (87), Ch 03 (72), Ch 04 (124), Ch 05 (86), Ch 06 (103).
  - Contiguous question numbering starting at 1 with zero gaps or duplicates.
- **Option & Answer Schema**:
  - Exactly 4 options (`a`, `b`, `c`, `d`) per question.
  - Canonical correct answer in `{'a', 'b', 'c', 'd'}`.
  - Correct answer distribution verified against DOCX ground truth.
- **Media & Context Binding**:
  - 72 embedded diagram PNG files properly extracted to `static/media/`.
  - Questions referencing `Figure X-Y`, `Table X-Y`, or `Scenario X-Y` bound to appropriate visual/tabular context.
- **Chinese Explanation Schema**:
  - Ingested question bank (`data/questions.json`) contains structured Chinese explanations (`concept`, `rationale`, `distractors`).

### 2.2 Tier 2: Boundary & Corner Cases (Robustness & Validation)
- **Question Count Clamping**:
  - Count = 0 or negative: Clamps to 1 or raises HTTP 422 / validation error.
  - Count = 1: Returns exactly 1 unique question.
  - Count > Chapter Pool Size: Clamps to maximum available questions without infinite loop or failure.
  - Count = Total Pool Size: Returns all questions in the pool shuffled without duplicates.
- **Chapter Range Boundaries**:
  - Single chapter selection (e.g., only `Ch_01`).
  - All chapters selection (`Ch_01` through `Ch_06`).
  - Disjoint multi-chapter selection (e.g., `Ch_01`, `Ch_04`).
  - Empty chapter selection or non-existent chapter ID (e.g., `Ch_99`): Handled with 400/422 validation response.
- **Scoring Extremes**:
  - 0% Score: All answers submitted incorrectly, correct count = 0, score percentage = 0.0%.
  - 100% Score: All answers submitted correctly, correct count = total, score percentage = 100.0%.
  - Partial answers / omitted answers: Handled gracefully without crash.

### 2.3 Tier 3: Cross-Feature Combinations & State Transitions
- **Multi-Chapter Sampling with Media Binding**:
  - Sampling questions across chapters that contain diagrams (Ch 2, 3, 4, 5, 6) ensures referenced diagrams (`image_url`) travel with the question payload.
- **Mode Switching**:
  - **Practice Mode**: Immediate feedback support, question payload delivers stems and options.
  - **Formal Evaluation (Exam) Mode**: Timed or untimed full submission, answers hidden until submission payload evaluated.
- **Security & Anti-Cheating**:
  - Quiz delivery endpoint (`POST /api/quiz/new`) omits `correct_answer` and `explanation_zh` to prevent client-side inspection cheating.
  - Submission endpoint (`POST /api/quiz/submit`) securely evaluates submitted answers against server-side session or store.

### 2.4 Tier 4: Real-World Application Workflows (E2E End-to-End)
- **Complete Student Practice Flow**:
  1. Student requests chapter metadata (`GET /api/chapters`).
  2. Student configures a 20-question quiz across Chapters 1, 2, and 3 (`POST /api/quiz/new`).
  3. Student answers questions (some correct, some incorrect).
  4. Student submits quiz (`POST /api/quiz/submit`).
  5. Student receives score summary (e.g., 15/20, 75.0%), chapter breakdown, and rich Chinese explanations for the 5 incorrect questions.
- **Complete Formal Examination Flow**:
  1. User starts exam mode with 50 questions across all 6 chapters.
  2. Answers all questions, navigates question palette.
  3. Submits exam and verifies comprehensive diagnostic review.

---

## 3. Directory Layout & Test Suite Map

```
tests/
├── __init__.py              # Package marker
├── test_ingest.py           # Tier 1 & 2: DOCX Parsing, Question Counts, Diagram Binding, Explanations
├── test_quiz_engine.py      # Tier 1 & 2: Random Sampling, No-Duplicate Guarantees, Clamping, Scoring
├── test_api.py              # Tier 2 & 3: FastAPI Endpoints, Input Validation, Session Management, Security
└── e2e_test_runner.py       # Tier 4: Unified Standalone Runner executing Tiers 1-4 with ANSI report
```

### 3.1 Test File Breakdown

| Test File | Primary Focus | Tiers Covered | Target Acceptance Criteria |
|---|---|---|---|
| `tests/test_ingest.py` | DOCX parsing, 585 questions verification, option extraction, diagram binding, explanation storage | Tier 1, Tier 2 | ORIGINAL_REQUEST §R1, §Acceptance (Data Ingestion) |
| `tests/test_quiz_engine.py` | Sampling without replacement, boundary clamping, scoring calculations, diagnostic feedback generation | Tier 1, Tier 2 | ORIGINAL_REQUEST §R2, §R4, §Acceptance (Quiz Config & Scoring) |
| `tests/test_api.py` | Endpoints `GET /api/chapters`, `POST /api/quiz/new`, `POST /api/quiz/submit`, parameter validation, error handling | Tier 2, Tier 3 | ORIGINAL_REQUEST §R2, §R3, §R4 |
| `tests/e2e_test_runner.py` | Full end-to-end integration workflows, cross-module assertions, summary metrics | Tier 1, 2, 3, 4 | ORIGINAL_REQUEST §Acceptance (All) |

---

## 4. Test Execution Guide

### 4.1 Prerequisites
- Python 3.12+
- Dependencies: `pytest`, `httpx`, `fastapi`, `python-docx`, `pydantic`

### 4.2 Running Tests via Pytest
Run all unit and integration tests:
```powershell
python -m pytest tests/ -v
```

Run specific test modules:
```powershell
python -m pytest tests/test_ingest.py -v
python -m pytest tests/test_quiz_engine.py -v
python -m pytest tests/test_api.py -v
```

### 4.3 Running Unified Standalone E2E Runner
Run the standalone runner that executes all four tiers and generates a comprehensive terminal report:
```powershell
python tests/e2e_test_runner.py
```
Exit code will be `0` when all assertions pass.

---

## 5. Verification Checklist & Success Criteria

- [ ] All 6 DOCX files exist and match canonical question counts (113, 87, 72, 124, 86, 103).
- [ ] Total canonical question pool equals 585 questions.
- [ ] All questions have lowercase single-letter answers in `{'a', 'b', 'c', 'd'}`.
- [ ] Diagram extraction accounts for 72 PNG files across Chapters 2-6.
- [ ] Deduplicated sampling never yields duplicate question IDs in a single quiz session.
- [ ] Boundary clamping prevents negative, zero, or overflow question requests.
- [ ] Scoring logic accurately calculates correct count, total, percentage, and per-chapter breakdown.
- [ ] Diagnostic review returns Chinese explanations for incorrect questions.
- [ ] Unfinished or in-progress modules gracefully notify rather than produce unhandled crashes.
