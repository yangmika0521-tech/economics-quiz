"""FastAPI Application for Economics Interactive Evaluation & Quiz Practice System.

Provides REST endpoints for:
- Querying chapter metadata and question counts (GET /api/chapters)
- Generating randomized quiz sessions with anti-cheating protections (POST /api/quiz/new)
- Evaluating quiz submissions, calculating scores, and returning rich Chinese diagnostics (POST /api/quiz/submit)
- Static file serving (/static) and SPA root delivery (GET /)
"""

import json
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from app.models import (
    Chapter,
    QuizConfig,
    QuizQuestion,
    QuizSession,
    QuizSubmission,
    QuizResult,
)
from app import quiz_engine


# ============================================================================
# Paths & Data Loading
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_JSON_PATH = PROJECT_ROOT / "data" / "questions.json"
STATIC_DIR = PROJECT_ROOT / "static"


def load_question_bank() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Loads chapter metadata and questions from data/questions.json."""
    target_path = QUESTIONS_JSON_PATH
    if not target_path.exists():
        fallback = Path.cwd() / "data" / "questions.json"
        if fallback.exists():
            target_path = fallback

    if not target_path.exists():
        return [], []

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("chapters", []), data.get("questions", [])


chapters_cache, questions_cache = load_question_bank()
known_chapter_ids = {c["id"] for c in chapters_cache}

# Bounded in-memory store for active quiz sessions (LRU capacity limit)
# session_id -> {"questions": list_of_raw_questions, "mode": mode_str}
MAX_SESSIONS = 5000
quiz_sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()


# ============================================================================
# FastAPI App Initialization
# ============================================================================

app = FastAPI(
    title="Economics Interactive Evaluation & Quiz Practice System",
    description="Interactive evaluation and practice system for Economics MC question bank.",
    version="1.0.0",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/chapters", response_model=Dict[str, List[Chapter]])
async def get_chapters():
    """Returns metadata and question counts for all available chapters."""
    global chapters_cache, questions_cache, known_chapter_ids
    if not chapters_cache:
        chapters_cache, questions_cache = load_question_bank()
        known_chapter_ids = {c["id"] for c in chapters_cache}

    return {"chapters": chapters_cache}


@app.post("/api/quiz/new", response_model=QuizSession)
async def create_quiz_session(config: QuizConfig):
    """Generates a new randomized quiz session based on user configuration.

    Strictly complies with the Anti-Cheating invariant:
    Omits `correct_answer` and `explanation_zh` from the questions sent to the client.
    """
    global chapters_cache, questions_cache, known_chapter_ids
    if not chapters_cache or not questions_cache:
        chapters_cache, questions_cache = load_question_bank()
        known_chapter_ids = {c["id"] for c in chapters_cache}

    # 1. Validation: chapter_ids cannot be empty
    if not config.chapter_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid chapter selection: chapter_ids cannot be empty.",
        )

    # 2. Validation: all chapter_ids must exist in known chapters
    invalid_ids = [ch for ch in config.chapter_ids if ch not in known_chapter_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid chapter selection: unknown chapter IDs {invalid_ids}.",
        )

    # 3. Sample questions using quiz engine
    sampled = quiz_engine.sample_questions(
        questions_cache,
        config.chapter_ids,
        config.question_count,
    )

    if not sampled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No questions available for the selected chapter criteria.",
        )

    # 4. Generate session ID and store full questions with answers in bounded session cache
    session_id = str(uuid.uuid4())
    session_mode = config.mode or "practice"
    if session_id in quiz_sessions:
        quiz_sessions.move_to_end(session_id)
    quiz_sessions[session_id] = {
        "questions": sampled,
        "mode": session_mode,
    }
    # Enforce bounded session store capacity (LRU eviction)
    while len(quiz_sessions) > MAX_SESSIONS:
        quiz_sessions.popitem(last=False)

    # 5. Build client-facing questions list, omitting correct answers & explanations
    client_questions = [
        QuizQuestion(
            id=q["id"],
            chapter_id=q["chapter_id"],
            question_number=q["question_number"],
            stem=q["stem"],
            image_url=q.get("image_url"),
            context_table=q.get("context_table"),
            options=q["options"],
        )
        for q in sampled
    ]

    return QuizSession(
        session_id=session_id,
        total_questions=len(client_questions),
        mode=session_mode,
        questions=client_questions,
    )


@app.post("/api/quiz/submit", response_model=QuizResult)
async def submit_quiz(submission: QuizSubmission):
    """Evaluates user answers, computes score, and returns detailed Chinese explanations."""
    session_id = submission.session_id
    if session_id not in quiz_sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found or expired.",
        )

    # Move active session to end for LRU recency
    quiz_sessions.move_to_end(session_id)
    session_data = quiz_sessions[session_id]
    sampled_questions = session_data["questions"]

    # Compute evaluation results
    eval_result = quiz_engine.evaluate_submission(
        sampled_questions,
        submission.answers,
    )

    return QuizResult(**eval_result)


# ============================================================================
# Static Files & SPA Root Route
# ============================================================================

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DATA_DIR = PROJECT_ROOT / "data"
if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


@app.get("/")
async def serve_root():
    """Serves the Single Page Application index.html if present, else default API landing."""
    index_html = STATIC_DIR / "index.html"
    if not index_html.exists():
        fallback_root = PROJECT_ROOT / "index.html"
        if fallback_root.exists():
            index_html = fallback_root

    if index_html.exists():
        return FileResponse(str(index_html))
    return HTMLResponse("<h1>Economics Quiz API</h1><p>API is operational.</p>")
