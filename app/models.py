"""Domain models for Economics Quiz and Ingestion System.

This module provides the single source of truth for all domain entities,
question bank structures, quiz configurations, and diagnostic feedback payloads.
Built with Pydantic v2.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ============================================================================
# 1. Core Question Bank Entities (Milestone 1 Focus)
# ============================================================================

class ExplanationZh(BaseModel):
    """Detailed Chinese pedagogical explanation for a question."""
    model_config = ConfigDict(extra="ignore")

    concept: str = Field(
        ...,
        description="Core economic principle or concept (e.g., '稀少性與資源配置 (Scarcity)')"
    )
    rationale: str = Field(
        ...,
        description="Detailed step-by-step Chinese rationale explaining why the correct answer is right"
    )
    distractors: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of incorrect option keys ('a', 'b', 'c', 'd') to specific reasons why they are wrong"
    )
    note: Optional[str] = Field(
        None,
        description="Optional teacher note, errata, or examination tip"
    )


class Chapter(BaseModel):
    """Metadata for an economics chapter in the question bank."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique chapter identifier, e.g., 'Ch_01'")
    number: int = Field(..., ge=1, le=6, description="Chapter number (1 through 6)")
    title_en: str = Field(..., description="English chapter title")
    title_zh: str = Field(..., description="Traditional Chinese chapter title")
    total_questions: int = Field(..., ge=0, description="Total number of questions in chapter")


class Question(BaseModel):
    """Full question entity in the question bank."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique question ID, e.g., 'Ch01_Q001'")
    chapter_id: str = Field(..., description="Chapter identifier foreign key, e.g., 'Ch_01'")
    question_number: int = Field(..., ge=1, description="1-based question sequence number within chapter")
    stem: str = Field(..., description="Question stem / prompt text")
    image_url: Optional[str] = Field(None, description="Static URL to diagram image if referenced")
    context_table: Optional[str] = Field(None, description="Context table text or Markdown if question references a table")
    options: Dict[str, str] = Field(..., description="Mapping of option keys 'a', 'b', 'c', 'd' to text")
    correct_answer: str = Field(..., description="Canonical correct option key ('a', 'b', 'c', or 'd')")
    explanation_zh: ExplanationZh = Field(..., description="Structured Chinese explanation")

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"a", "b", "c", "d"}:
            raise ValueError(f"correct_answer must be one of 'a', 'b', 'c', 'd', got '{v}'")
        return clean

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: Dict[str, str]) -> Dict[str, str]:
        for opt in ["a", "b", "c", "d"]:
            if opt not in v or not str(v[opt]).strip():
                raise ValueError(f"Question options missing or empty for '{opt}'")
        return v


class QuestionBank(BaseModel):
    """Root container representing data/questions.json."""
    model_config = ConfigDict(extra="ignore")

    chapters: List[Chapter] = Field(default_factory=list)
    questions: List[Question] = Field(default_factory=list)


# ============================================================================
# 2. Quiz Session & API Entities (M2 & M3 Integration)
# ============================================================================

class QuizConfig(BaseModel):
    """Payload for POST /api/quiz/new."""
    model_config = ConfigDict(extra="ignore")

    chapter_ids: List[str] = Field(default_factory=list, description="List of chapter IDs to include, e.g., ['Ch_01']")
    question_count: int = Field(10, description="Number of questions requested")
    mode: Optional[str] = Field("practice", description="Mode: 'practice' (instant feedback) or 'exam' (graded at submission)")


class QuizQuestion(BaseModel):
    """Question sent to client during quiz (answers and explanations omitted)."""
    model_config = ConfigDict(extra="ignore")

    id: str
    chapter_id: str
    question_number: int
    stem: str
    image_url: Optional[str] = None
    context_table: Optional[str] = None
    options: Dict[str, str]


class QuizSession(BaseModel):
    """Response payload for POST /api/quiz/new."""
    model_config = ConfigDict(extra="ignore")

    session_id: str
    total_questions: int
    mode: str
    questions: List[QuizQuestion]


class QuizSubmission(BaseModel):
    """Payload for POST /api/quiz/submit."""
    model_config = ConfigDict(extra="ignore")

    session_id: str
    answers: Dict[str, str] = Field(
        ...,
        description="Mapping from question_id to selected option key ('a', 'b', 'c', or 'd')"
    )


class QuestionResult(BaseModel):
    """Individual question review returned after quiz submission."""
    model_config = ConfigDict(extra="ignore")

    question_id: str
    stem: str
    user_answer: Optional[str] = None
    correct_answer: str
    is_correct: bool
    image_url: Optional[str] = None
    context_table: Optional[str] = None
    explanation_zh: Optional[ExplanationZh] = None


class QuizResult(BaseModel):
    """Response payload for POST /api/quiz/submit."""
    model_config = ConfigDict(extra="ignore")

    total_questions: int
    correct_count: int
    score_percentage: float
    chapter_breakdown: Dict[str, Dict[str, int]]
    results: List[QuestionResult]
