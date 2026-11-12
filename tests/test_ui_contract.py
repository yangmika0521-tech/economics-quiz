"""
tests/test_ui_contract.py
Automated Contract, RWD, and Dual-Runtime Verification Tests for Milestone 3.

Verifies:
1. HTML Structure & Layout Contracts (root index.html & static/index.html).
2. Mobile-First Responsive Design (RWD) & Touch Target CSS Contracts.
3. Client-Side SPA State Machine, Dual-Runtime, & Keyboard Shortcut Contracts in app.js.
4. FastAPI Static Delivery & Media Binding Integration.
5. Client-Side Sampling & Evaluation Algorithmic Parity with app.quiz_engine.
"""

import json
import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
INDEX_HTML_PATH = PROJECT_ROOT / "index.html"
STATIC_INDEX_HTML_PATH = STATIC_DIR / "index.html"
STYLE_CSS_PATH = STATIC_DIR / "css" / "style.css"
APP_JS_PATH = STATIC_DIR / "js" / "app.js"
QUESTIONS_JSON_PATH = PROJECT_ROOT / "data" / "questions.json"
DEPLOYMENT_MD_PATH = PROJECT_ROOT / "DEPLOYMENT.md"


# ==============================================================================
# 1. HTML Structure & Layout Contracts
# ==============================================================================

class TestHtmlStructureContract:
    """Verifies that index.html and static/index.html fulfill the UI structure contract."""

    def test_both_index_html_files_exist_and_non_empty(self):
        """Both root index.html and static/index.html must exist and contain content."""
        assert INDEX_HTML_PATH.exists(), "Root index.html is missing"
        assert STATIC_INDEX_HTML_PATH.exists(), "static/index.html is missing"
        assert INDEX_HTML_PATH.stat().st_size > 1000, "Root index.html is too small"
        assert STATIC_INDEX_HTML_PATH.stat().st_size > 1000, "static/index.html is too small"

    def test_html_meta_viewport_and_charset(self):
        """Both HTML files must specify viewport for RWD and UTF-8 charset."""
        for path in [INDEX_HTML_PATH, STATIC_INDEX_HTML_PATH]:
            content = path.read_text(encoding="utf-8")
            assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in content or \
                   'name="viewport"' in content, f"Missing viewport in {path.name}"
            assert 'charset="UTF-8"' in content or 'charset="utf-8"' in content, f"Missing charset in {path.name}"
            assert "<title>經濟學 互動式評量與題庫測驗系統</title>" in content, f"Title mismatch in {path.name}"

    def test_relative_asset_links_for_github_pages(self):
        """Asset links must use relative paths (./static/...) so GitHub Pages repo subpaths work."""
        for path in [INDEX_HTML_PATH, STATIC_INDEX_HTML_PATH]:
            content = path.read_text(encoding="utf-8")
            assert 'href="./static/css/style.css"' in content, f"CSS must use relative path in {path.name}"
            assert 'src="./static/js/app.js"' in content, f"JS must use relative path in {path.name}"

    def test_three_main_spa_views_exist(self):
        """The three primary SPA view containers must be present in HTML."""
        content = STATIC_INDEX_HTML_PATH.read_text(encoding="utf-8")
        assert 'id="view-setup"' in content, "Missing #view-setup container"
        assert 'id="view-quiz"' in content, "Missing #view-quiz container"
        assert 'id="view-review"' in content, "Missing #view-review container"

    def test_modals_and_drawers_markup_present(self):
        """Question palette drawer, guardrail modal, and diagram zoom lightbox must be present."""
        content = STATIC_INDEX_HTML_PATH.read_text(encoding="utf-8")
        # Palette Drawer
        assert 'id="palette-drawer"' in content, "Missing #palette-drawer"
        assert 'id="palette-grid"' in content, "Missing #palette-grid"
        assert 'id="btn-close-palette"' in content, "Missing #btn-close-palette"

        # Guardrail Modal
        assert 'id="guardrail-modal"' in content, "Missing #guardrail-modal"
        assert 'id="btn-guardrail-cancel"' in content, "Missing #btn-guardrail-cancel"
        assert 'id="btn-guardrail-confirm"' in content, "Missing #btn-guardrail-confirm"

        # Diagram Zoom Modal
        assert 'id="diagram-modal"' in content, "Missing #diagram-modal"
        assert 'id="diagram-modal-img"' in content, "Missing #diagram-modal-img"
        assert 'id="btn-close-diagram"' in content, "Missing #btn-close-diagram"

    def test_setup_view_required_controls(self):
        """Setup view must contain chapter grid, quick selectors, count input/slider, and start button."""
        content = STATIC_INDEX_HTML_PATH.read_text(encoding="utf-8")
        assert 'id="chapter-list"' in content
        assert 'id="pool-count"' in content
        assert 'id="btn-select-all"' in content
        assert 'id="btn-select-ch1-3"' in content
        assert 'id="btn-select-ch4-6"' in content
        assert 'id="btn-select-reset"' in content
        assert 'id="slider-count"' in content
        assert 'id="input-count"' in content
        assert 'id="btn-start-quiz"' in content
        assert 'name="quiz-mode"' in content

    def test_quiz_view_required_controls(self):
        """Quiz view must contain timer, flag button, stem, context table, diagram container, options, and nav."""
        content = STATIC_INDEX_HTML_PATH.read_text(encoding="utf-8")
        assert 'id="quiz-timer"' in content
        assert 'id="btn-flag-q"' in content
        assert 'id="btn-toggle-palette"' in content
        assert 'id="question-stem"' in content
        assert 'id="question-context-table"' in content
        assert 'id="question-diagram-container"' in content
        assert 'id="question-options"' in content
        assert 'id="btn-prev-q"' in content
        assert 'id="btn-next-q"' in content
        assert 'id="btn-submit-quiz"' in content

    def test_review_view_required_controls(self):
        """Review view must contain score summary, chapter breakdown, filters, practice missed, and review list."""
        content = STATIC_INDEX_HTML_PATH.read_text(encoding="utf-8")
        assert 'id="review-score-num"' in content
        assert 'id="review-percentage"' in content
        assert 'id="chapter-breakdown-list"' in content
        assert 'id="btn-filter-all"' in content
        assert 'id="btn-filter-wrong"' in content
        assert 'id="btn-filter-flagged"' in content
        assert 'id="btn-practice-missed"' in content
        assert 'id="btn-new-quiz"' in content
        assert 'id="review-list"' in content


# ==============================================================================
# 2. CSS Mobile-First Responsive Design (RWD) & Touch Target Contracts
# ==============================================================================

class TestCssResponsiveAndTouchContracts:
    """Verifies that static/css/style.css meets Mobile-First and touch ergonomics standards."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        assert STYLE_CSS_PATH.exists(), "static/css/style.css is missing"
        self.css_text = STYLE_CSS_PATH.read_text(encoding="utf-8")

    def test_touch_target_minimum_size_enforced(self):
        """Interactive touch targets must be at least 44px x 44px."""
        assert "44px" in self.css_text or "--touch-target-min: 44px" in self.css_text
        assert "min-height: var(--touch-target-min)" in self.css_text or "min-height: 44px" in self.css_text
        assert ".palette-btn" in self.css_text
        assert ".option-item" in self.css_text

    def test_responsive_media_queries_present(self):
        """CSS must declare responsive breakpoints for tablet and desktop layouts."""
        media_matches = re.findall(r"@media\s*\([^)]+\)", self.css_text)
        assert len(media_matches) >= 3, f"Expected at least 3 media queries, found {len(media_matches)}"
        has_min_width = any("min-width" in m for m in media_matches)
        assert has_min_width, "Mobile-First RWD requires min-width media queries"

    def test_drawer_panel_and_backdrop_styling(self):
        """Drawer overlay, panel, and backdrop transitions must be defined."""
        assert ".drawer-overlay" in self.css_text
        assert ".drawer-panel" in self.css_text
        assert ".drawer-backdrop" in self.css_text
        assert "transform: translateX" in self.css_text

    def test_palette_status_classes_present(self):
        """Palette buttons must define distinct styles for current, answered, unanswered, flagged."""
        assert ".palette-btn.current" in self.css_text or ".palette-btn.active" in self.css_text
        assert ".palette-btn.answered" in self.css_text
        assert ".palette-btn.unanswered" in self.css_text
        assert ".palette-btn.flagged" in self.css_text

    def test_diagnostic_explanation_card_classes(self):
        """Diagnostic cards must define distinct styling for concept, rationale, and distractors."""
        assert ".diagnostic-concept" in self.css_text
        assert ".diagnostic-rationale" in self.css_text
        assert ".diagnostic-distractors" in self.css_text

    def test_guardrail_modal_classes(self):
        """Guardrail modal overlay and warning classes must be defined."""
        assert ".modal-overlay" in self.css_text
        assert ".modal-warning" in self.css_text
        assert ".alert-highlight" in self.css_text


# ==============================================================================
# 3. JavaScript SPA State Machine & Dual-Runtime Contracts
# ==============================================================================

class TestJavaScriptContracts:
    """Verifies that static/js/app.js implements dual-runtime, sampling, and navigation."""

    @pytest.fixture(autouse=True)
    def load_js(self):
        assert APP_JS_PATH.exists(), "static/js/app.js is missing"
        self.js_text = APP_JS_PATH.read_text(encoding="utf-8")

    def test_dual_runtime_auto_detection_logic(self):
        """app.js must auto-detect github.io hostname and provide smooth fallback."""
        assert "github.io" in self.js_text
        assert "initDualRuntime" in self.js_text or "detectRuntime" in self.js_text
        assert "/api/chapters" in self.js_text
        assert "questions.json" in self.js_text

    def test_relative_media_url_resolver(self):
        """app.js must implement relative media URL resolution for subfolder hosting."""
        assert "resolveMediaUrl" in self.js_text
        assert "./" in self.js_text

    def test_client_side_sampling_algorithm_present(self):
        """app.js must implement client-side question sampling matching quiz_engine."""
        assert "clientSampleQuestions" in self.js_text or "sampleQuestions" in self.js_text
        # Must include clamping and randomization
        assert "Math.random" in self.js_text

    def test_client_side_evaluation_algorithm_present(self):
        """app.js must implement client-side scoring and explanation binding."""
        assert "clientEvaluateSubmission" in self.js_text or "evaluateSubmission" in self.js_text
        assert "chapterBreakdown" in self.js_text or "chapter_breakdown" in self.js_text
        assert "is_correct" in self.js_text

    def test_keyboard_navigation_event_listener(self):
        """app.js must handle keyboard shortcuts A/B/C/D, 1-4, arrow keys, and flag."""
        assert "handleKeyboardShortcuts" in self.js_text or "keydown" in self.js_text
        assert "'a'" in self.js_text or '"a"' in self.js_text
        assert "arrowleft" in self.js_text or "ArrowLeft" in self.js_text
        assert "arrowright" in self.js_text or "ArrowRight" in self.js_text

    def test_submission_guardrail_unanswered_check(self):
        """app.js must check for unattempted questions before submission."""
        assert "checkAndSubmitQuiz" in self.js_text or "guardrail" in self.js_text
        assert "openGuardrailModal" in self.js_text or "unanswered" in self.js_text


# ==============================================================================
# 4. FastAPI Static Delivery & Integration
# ==============================================================================

class TestFastApiStaticDelivery:
    """Verifies that FastAPI serves the SPA, assets, and diagrams with correct MIME types."""

    def test_root_endpoint_delivers_spa_html(self):
        """GET / must return 200 and serve HTML containing the SPA."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "經濟學 互動式評量與題庫測驗系統" in resp.text
        assert "view-setup" in resp.text

    def test_static_css_served_with_correct_mime(self):
        """GET /static/css/style.css must return 200 with text/css."""
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]
        assert "--color-primary" in resp.text

    def test_static_js_served_with_correct_mime(self):
        """GET /static/js/app.js must return 200 with javascript MIME type."""
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200
        ct = resp.headers["content-type"].lower()
        assert "javascript" in ct

    def test_static_media_diagrams_accessible(self):
        """All diagram images referenced in data/questions.json must be accessible via /static/media/."""
        with open(QUESTIONS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        image_urls = {q["image_url"] for q in data["questions"] if q.get("image_url")}
        assert len(image_urls) > 0, "No diagram image URLs found in question bank"

        # Spot-check first 10 diagram URLs
        for img_url in list(image_urls)[:10]:
            resp = client.get(img_url)
            assert resp.status_code == 200, f"Diagram image {img_url} returned status {resp.status_code}"
            assert "image/png" in resp.headers["content-type"], f"Diagram {img_url} has unexpected content-type"

    def test_data_questions_json_accessible_for_static_fallback(self):
        """GET /data/questions.json must return 200 for local static fallback testing."""
        resp = client.get("/data/questions.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "chapters" in data
        assert "questions" in data
        assert len(data["questions"]) == 585


# ==============================================================================
# 5. Deployment Guide Documentation Contract
# ==============================================================================

class TestDeploymentGuideContract:
    """Verifies that DEPLOYMENT.md provides complete deployment and operational instructions."""

    def test_deployment_guide_exists_and_contains_sections(self):
        """DEPLOYMENT.md must exist and describe FastAPI, GitHub Pages, and Dual-Runtime."""
        assert DEPLOYMENT_MD_PATH.exists(), "DEPLOYMENT.md is missing"
        content = DEPLOYMENT_MD_PATH.read_text(encoding="utf-8")
        assert "FastAPI" in content
        assert "GitHub Pages" in content
        assert "Dual-Runtime" in content or "雙運行" in content
        assert "uvicorn app.main:app" in content
        assert "pytest" in content
        assert "e2e_test_runner.py" in content
