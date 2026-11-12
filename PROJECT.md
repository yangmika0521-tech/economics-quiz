# Project: Economics Interactive Evaluation & Quiz Practice System
# Scope: Full Project

## Architecture
- **Language & Runtime**: Python 3.12 (FastAPI + Uvicorn) + HTML5 / CSS3 / Vanilla JavaScript SPA
- **Data Flow**:
  1. Source DOCX files (`Ch_01_MC_Algo.docx` ~ `Ch_06_MC_Algo.docx`) -> Ingestion script (`app/ingest.py`) -> Question Bank JSON (`data/questions.json`) + Diagrams (`static/media/*.png`) + Chinese Explanations.
  2. Frontend SPA -> Calls `GET /api/chapters` -> Displays chapter cards and question pool counter.
  3. User selects chapters and question count -> Calls `POST /api/quiz/new` -> Backend samples requested questions randomly without duplicates.
  4. User interacts with quiz (selects options, navigates via palette) -> Submits quiz via `POST /api/quiz/submit`.
  5. Backend computes score (correct count, total, percentage) -> Identifies incorrect answers -> Returns results along with detailed Chinese explanations (考點核心, 正解詳析, 干擾項辨析) for incorrect answers.
  6. Frontend displays score summary, chapter performance breakdown, and diagnostic review cards with Chinese explanations.
- **Code Layout**:
  ```
  c:\Users\yangm\OneDrive\Desktop\AI\經濟學\
  ├── app/
  │   ├── __init__.py
  │   ├── main.py              # FastAPI application entrypoint & static routes
  │   ├── models.py            # Pydantic schemas (Chapter, Question, QuizConfig, Submission, QuizResult)
  │   ├── ingest.py            # DOCX parser, image extractor, Chinese explanation binder
  │   └── quiz_engine.py       # Deduplicated random sampler & scoring logic
  ├── data/
  │   └── questions.json       # Ingested question bank (585 questions + Chinese explanations)
  ├── static/
  │   ├── index.html           # Single-Page Application HTML
  │   ├── css/
  │   │   └── style.css        # Responsive styling, card components, palette, modals
  │   ├── js/
  │   │   └── app.js           # Client-side state machine, API client, interactive UI
  │   └── media/               # Extracted diagram images (72 PNG files)
  ├── tests/
  │   ├── test_ingest.py       # Unit tests for question bank extraction & integrity
  │   ├── test_quiz_engine.py  # Unit tests for random sampling & scoring algorithms
  │   ├── test_api.py          # Integration tests for FastAPI endpoints
  │   └── e2e_test_runner.py   # Comprehensive E2E test runner (Tiers 1-4)
  ├── PROJECT.md
  ├── TEST_INFRA.md
  └── TEST_READY.md
  ```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | DOCX Ingestion (585 Qs) | Parse 6 DOCX files, extracting all questions, options A-D, answers | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Diagram & Media Binding | Extract 72 PNG images to static/media and bind figure/table contexts | M1 | Survey Findings |
| 3 | Chinese Explanations Store | High-quality structured Chinese explanations (concept, rationale, distractors) | M1 | ORIGINAL_REQUEST §R4 |
| 4 | Chapter Metadata API | Endpoint `GET /api/chapters` returning chapter stats and titles | M2 | ORIGINAL_REQUEST §R2 |
| 5 | Deduplicated Random Sampling | Endpoint `POST /api/quiz/new` sampling without duplicates across single/multiple/all chapters | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Scoring Engine | Endpoint `POST /api/quiz/submit` computing correct count, total, percentage | M2 | ORIGINAL_REQUEST §R4 |
| 7 | Diagnostic Result Payload | Return user answers, correct answers, and Chinese explanations for mistakes | M2 | ORIGINAL_REQUEST §R4 |
| 8 | Web Configuration UI | Chapter multi-select, quick buttons (all, Ch 1-3, etc.), count input with clamp | M3 | ORIGINAL_REQUEST §R2 |
| 9 | Interactive Quiz UI | Question stem, zoomable diagram view, option radio/buttons, next/prev | M3 | ORIGINAL_REQUEST §R3 |
| 10 | Question Palette Drawer | Floating/collapsible question map with answered, unanswered, flagged statuses | M3 | ORIGINAL_REQUEST §R3 |
| 11 | Submission Guardrail Modal | Warns on unattempted questions with option to return or confirm submit | M3 | ORIGINAL_REQUEST §R3 |
| 12 | Score & Review UI | Summary card (score, percentage, count), diagnostic cards with Chinese explanations | M3 | ORIGINAL_REQUEST §R4 |
| 13 | Dual Mode Support | Practice Mode (immediate feedback) vs Formal Evaluation Mode (timed, submit to grade) | M3 | Survey Findings |
| 14 | E2E Test Suite (Tiers 1-4) | Automated test suite verifying ingestion, sampling, scoring, and UI flows | E2E Track | ORIGINAL_REQUEST §Acceptance |
| 15 | Final Verification & Hardening | 100% E2E test pass + Tier 5 adversarial hardening | M_FINAL | Project Pattern |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Ingestion & Explanations | DOCX parsing, media extraction, Chinese explanation generation (`app/ingest.py`, `data/questions.json`, `static/media/`) | none | PLANNED |
| M2 | Backend API & Sampling | FastAPI endpoints, models, deduplicated sampling, scoring engine (`app/main.py`, `app/models.py`, `app/quiz_engine.py`) | M1 | PLANNED |
| M3 | Interactive Web UI | Responsive SPA (`static/index.html`, `static/css/style.css`, `static/js/app.js`) with config, quiz, palette, scoring & Chinese explanations review | M2 | PLANNED |
| E2E | E2E Testing Suite | Opaque-box test harness & test cases Tiers 1-4 (`tests/test_*.py`, `tests/e2e_test_runner.py`, `TEST_READY.md`) | none | IN_PROGRESS |
| M_FINAL | E2E Test Pass & Hardening | Pass 100% of E2E test suite + Phase 2 adversarial coverage hardening | M3, E2E | PLANNED |

## Interface Contracts
### Ingestion Output ↔ Backend Models (`data/questions.json`)
```json
{
  "chapters": [
    {
      "id": "Ch_01",
      "number": 1,
      "title_en": "Ten Principles of Economics",
      "title_zh": "經濟學十大原理",
      "total_questions": 113
    }
  ],
  "questions": [
    {
      "id": "Ch01_Q001",
      "chapter_id": "Ch_01",
      "question_number": 1,
      "stem": "Resources are...",
      "image_url": "/static/media/ch02_fig1.png",
      "context_table": null,
      "options": {
        "a": "scarce for households but not for economies.",
        "b": "scarce for economies but not for households.",
        "c": "scarce for both households and economies.",
        "d": "abundant for both households and economies."
      },
      "correct_answer": "c",
      "explanation_zh": {
        "concept": "稀少性與資源配置 (Scarcity)",
        "rationale": "經濟學的核心在於社會資源的稀少性。無論對家庭或整個經濟體而言，資源都是有限的...",
        "distractors": {
          "a": "錯誤。對經濟體而言資源亦具有稀少性。",
          "b": "錯誤。對家計單位而言資源亦有限。",
          "d": "錯誤。資源並非豐富無缺。"
        }
      }
    }
  ]
}
```

### Backend API ↔ Frontend Client
1. `GET /api/chapters`:
   - Response: `{"chapters": [ChapterMetadata, ...]}`
2. `POST /api/quiz/new`:
   - Request: `{"chapter_ids": ["Ch_01", "Ch_02"], "question_count": 10, "mode": "practice" | "exam"}`
   - Response: `{"session_id": "uuid", "total_questions": 10, "questions": [{"id", "chapter_id", "question_number", "stem", "image_url", "context_table", "options": {"a", "b", "c", "d"}}]}` (answers and explanations omitted during quiz!)
3. `POST /api/quiz/submit`:
   - Request: `{"session_id": "uuid", "answers": {"Ch01_Q001": "c", "Ch01_Q002": "a"}}`
   - Response:
     ```json
     {
       "total_questions": 10,
       "correct_count": 8,
       "score_percentage": 80.0,
       "chapter_breakdown": {"Ch_01": {"correct": 4, "total": 5}},
       "results": [
         {
           "question_id": "Ch01_Q001",
           "stem": "Resources are...",
           "user_answer": "a",
           "correct_answer": "c",
           "is_correct": false,
           "image_url": null,
           "explanation_zh": {
             "concept": "稀少性與資源配置",
             "rationale": "經濟學的核心在於社會資源的稀少性...",
             "distractors": {"a": "錯誤。對經濟體而言資源亦具有稀少性。"}
           }
         }
       ]
     }
     ```
