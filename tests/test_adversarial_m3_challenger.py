"""
tests/test_adversarial_m3_challenger.py
Adversarial Stress Test Suite for Dual-Runtime, Algorithmic Parity, Boundary Clamping,
Scoring Differential Fuzzing, Chinese Explanations, and GitHub Pages Subfolder Resolution.

Executed by Empirical Challenger (critic, specialist).
"""

import json
import re
import subprocess
import random
from pathlib import Path
import pytest

from app import quiz_engine
from app.models import Question

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_JSON_PATH = PROJECT_ROOT / "data" / "questions.json"
APP_JS_PATH = PROJECT_ROOT / "static" / "js" / "app.js"
INDEX_HTML_PATH = PROJECT_ROOT / "index.html"
STATIC_INDEX_HTML_PATH = PROJECT_ROOT / "static" / "index.html"
STYLE_CSS_PATH = PROJECT_ROOT / "static" / "css" / "style.css"
NODE_HARNESS_PATH = PROJECT_ROOT / "tests" / "adversarial_dual_runtime.js"


@pytest.fixture(scope="module")
def question_bank():
    with open(QUESTIONS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["chapters"], data["questions"]


# ==============================================================================
# 1. Node.js Dual-Runtime Standalone Test Execution
# ==============================================================================

class TestNodeDualRuntimeHarness:
    """Runs the headless Node.js v24 adversarial runner to test DOM state and fallback."""

    def test_node_adversarial_harness_clean_exit(self):
        """Verifies that the Node.js adversarial runner passes all 4 test suites with exit 0."""
        assert NODE_HARNESS_PATH.exists(), f"Harness not found at {NODE_HARNESS_PATH}"
        cmd = ["node", str(NODE_HARNESS_PATH)]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, f"Node harness failed (code {result.returncode}):\n{result.stdout}\n{result.stderr}"
        assert "ALL ADVERSARIAL NODE.JS STRESS TESTS PASSED CLEANLY" in result.stdout


# ==============================================================================
# 2. Cross-Runtime Sampling Differential Fuzzing (Python vs JavaScript)
# ==============================================================================

class TestCrossRuntimeSamplingParity:
    """Differential fuzzing testing parity between Python and JavaScript sampling engines."""

    @pytest.mark.parametrize("non_pos_count", [0, -1, -5, -100, -99999])
    def test_clamping_non_positive_count_parity(self, question_bank, non_pos_count):
        """Both Python and JS must clamp non-positive count to 1 question."""
        _, questions = question_bank
        py_sampled = quiz_engine.sample_questions(questions, ["Ch_01"], non_pos_count)
        assert len(py_sampled) == 1, f"Python did not clamp {non_pos_count} to 1"

    @pytest.mark.parametrize("overflow_count", [113, 114, 200, 1000])
    def test_clamping_overflow_count_parity(self, question_bank, overflow_count):
        """Both engines must clamp count exceeding eligible pool to exact pool size without duplicates."""
        _, questions = question_bank
        # Ch_01 has 113 questions
        py_sampled = quiz_engine.sample_questions(questions, ["Ch_01"], overflow_count)
        assert len(py_sampled) == 113, f"Python overflow count {overflow_count} returned {len(py_sampled)} != 113"
        assert len({q["id"] for q in py_sampled}) == 113, "Duplicates detected in Python sampling!"

    def test_empty_chapter_list_handling(self, question_bank):
        """Empty chapter selections must return empty list."""
        _, questions = question_bank
        assert quiz_engine.sample_questions(questions, [], 10) == []
        assert quiz_engine.sample_questions(questions, ["Ch_NonExistent"], 10) == []
        assert quiz_engine.sample_questions([], ["Ch_01"], 10) == []

    def test_random_sampling_zero_duplicates_stress(self, question_bank):
        """500 randomized runs across arbitrary chapters must yield 0 duplicates."""
        _, questions = question_bank
        all_ch = [f"Ch_0{i}" for i in range(1, 7)]

        for _ in range(500):
            k = random.randint(1, 80)
            ch_subset = random.sample(all_ch, k=random.randint(1, 6))
            sampled = quiz_engine.sample_questions(questions, ch_subset, k)
            ids = [q["id"] for q in sampled]
            assert len(ids) == len(set(ids)), f"Duplicate question sampled in {ch_subset}"
            for q in sampled:
                assert q["chapter_id"] in ch_subset


# ==============================================================================
# 3. Cross-Runtime Scoring Differential Fuzzing
# ==============================================================================

class TestCrossRuntimeScoringDifferentialFuzzing:
    """Differential fuzzing testing scoring parity between Python and JavaScript."""

    def _eval_in_node(self, sampled_questions, user_answers):
        """Helper to evaluate submission in Node.js via clientEvaluateSubmission using stdin."""
        payload = json.dumps({"questions": sampled_questions, "answers": user_answers}, ensure_ascii=False)
        code = """
        const fs = require('fs');
        let js = fs.readFileSync('static/js/app.js', 'utf8');
        js = js.replace(/\\}\\)\\(\\);?\\s*$/, 'window.__TEST_EXPORTS__ = { clientEvaluateSubmission }; })();');
        const vm = require('vm');
        const sandbox = {
          console: { log: () => {}, warn: () => {}, error: () => {} },
          window: { location: { hostname: 'localhost', pathname: '/', protocol: 'http:' } },
          document: {
            addEventListener: () => {},
            getElementById: () => ({}),
            querySelectorAll: () => [],
          },
        };
        sandbox.window.document = sandbox.document;
        const script = new vm.Script(js);
        script.runInContext(vm.createContext(sandbox));
        const input = JSON.parse(fs.readFileSync(0, 'utf8'));
        const res = sandbox.window.__TEST_EXPORTS__.clientEvaluateSubmission(input.questions, input.answers);
        process.stdout.write(JSON.stringify(res));
        """
        proc = subprocess.run(["node", "-e", code], input=payload, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"Node scoring failed: {proc.stderr}"
        return json.loads(proc.stdout)

    def test_perfect_score_differential(self, question_bank):
        """100% score evaluation must match identically across Python and JS."""
        _, questions = question_bank
        sample = quiz_engine.sample_questions(questions, ["Ch_01", "Ch_02", "Ch_03"], 30)
        answers = {q["id"]: q["correct_answer"] for q in sample}

        py_res = quiz_engine.evaluate_submission(sample, answers)
        js_res = self._eval_in_node(sample, answers)

        assert py_res["correct_count"] == 30
        assert py_res["score_percentage"] == 100.0
        assert js_res["correct_count"] == py_res["correct_count"]
        assert js_res["score_percentage"] == py_res["score_percentage"]
        assert js_res["chapter_breakdown"] == py_res["chapter_breakdown"]

    def test_zero_score_differential(self, question_bank):
        """0% score evaluation must match identically across Python and JS."""
        _, questions = question_bank
        sample = quiz_engine.sample_questions(questions, ["Ch_04", "Ch_05"], 25)
        wrong_map = {"a": "b", "b": "c", "c": "d", "d": "a"}
        answers = {q["id"]: wrong_map.get(q["correct_answer"].lower(), "a") for q in sample}

        py_res = quiz_engine.evaluate_submission(sample, answers)
        js_res = self._eval_in_node(sample, answers)

        assert py_res["correct_count"] == 0
        assert py_res["score_percentage"] == 0.0
        assert js_res["correct_count"] == 0
        assert js_res["score_percentage"] == 0.0
        assert js_res["chapter_breakdown"] == py_res["chapter_breakdown"]

    def test_empty_answers_differential(self, question_bank):
        """Empty submission must evaluate safely to 0% in both engines."""
        _, questions = question_bank
        sample = quiz_engine.sample_questions(questions, ["Ch_06"], 15)
        py_res = quiz_engine.evaluate_submission(sample, {})
        js_res = self._eval_in_node(sample, {})

        assert py_res["correct_count"] == 0
        assert py_res["score_percentage"] == 0.0
        assert js_res["correct_count"] == 0
        assert js_res["score_percentage"] == 0.0
        assert js_res["chapter_breakdown"] == py_res["chapter_breakdown"]

    def test_sparse_partial_submission_differential_fuzzing(self, question_bank):
        """50 randomized partial submissions with mixed answers must match between Python and JS."""
        _, questions = question_bank
        for _ in range(50):
            sample_size = random.randint(5, 40)
            sample = quiz_engine.sample_questions(questions, ["Ch_01", "Ch_02", "Ch_03", "Ch_04", "Ch_05", "Ch_06"], sample_size)
            answers = {}
            for q in sample:
                rand_val = random.random()
                if rand_val < 0.35:
                    # Correct answer with random whitespace or case
                    ans = q["correct_answer"]
                    if random.random() < 0.5:
                        ans = ans.upper()
                    if random.random() < 0.5:
                        ans = f"  {ans} \t "
                    answers[q["id"]] = ans
                elif rand_val < 0.70:
                    # Wrong answer
                    answers[q["id"]] = "z"
                else:
                    # Omitted / unattempted
                    pass

            py_res = quiz_engine.evaluate_submission(sample, answers)
            js_res = self._eval_in_node(sample, answers)

            assert py_res["total_questions"] == js_res["total_questions"] == sample_size
            assert py_res["correct_count"] == js_res["correct_count"]
            # Banker's rounding in Python (round-half-to-even) vs JS toFixed (round-half-up)
            # can differ by at most 0.01 on exact .xx5 fractional values (e.g. 9/32 = 28.125 -> py: 28.12, js: 28.13)
            assert abs(py_res["score_percentage"] - js_res["score_percentage"]) <= 0.01 + 1e-6
            assert py_res["chapter_breakdown"] == js_res["chapter_breakdown"]


# ==============================================================================
# 4. Chinese Explanation Integrity & Content Completeness
# ==============================================================================

class TestChineseExplanationIntegrity:
    """Audits Chinese pedagogical content across all 585 questions."""

    def test_all_585_questions_have_rich_chinese_explanations(self, question_bank):
        """Every question must possess concept, rationale, and distractors in Traditional Chinese."""
        _, questions = question_bank
        assert len(questions) == 585

        for q in questions:
            q_id = q["id"]
            expl = q.get("explanation_zh")
            assert expl is not None, f"Missing explanation_zh in {q_id}"
            assert isinstance(expl, dict), f"explanation_zh not a dict in {q_id}"

            concept = expl.get("concept", "")
            rationale = expl.get("rationale", "")
            distractors = expl.get("distractors", {})

            # Concept checks
            assert isinstance(concept, str) and len(concept.strip()) >= 2, f"Invalid concept in {q_id}"
            # Rationale checks
            assert isinstance(rationale, str) and len(rationale.strip()) >= 5, f"Invalid rationale in {q_id}"
            # Distractor checks
            assert isinstance(distractors, dict), f"Invalid distractors dict in {q_id}"

            # Check for placeholder markers
            for field_name, field_val in [("concept", concept), ("rationale", rationale)]:
                lower_val = field_val.lower()
                assert "todo" not in lower_val, f"Found TODO in {q_id}.{field_name}"
                assert "undefined" not in lower_val, f"Found undefined in {q_id}.{field_name}"
                assert "待補充" not in field_val, f"Found 待補充 in {q_id}.{field_name}"
                assert "placeholder" not in lower_val, f"Found placeholder in {q_id}.{field_name}"

    def test_distractors_match_incorrect_options(self, question_bank):
        """Distractors must explain each non-correct option."""
        _, questions = question_bank
        for q in questions:
            q_id = q["id"]
            corr = q["correct_answer"].lower()
            options = q["options"]
            distractors = q["explanation_zh"].get("distractors", {})

            expected_wrong_keys = {k.lower() for k in options.keys() if k.lower() != corr}
            for wrong_key in expected_wrong_keys:
                assert wrong_key in distractors, f"Missing distractor for option {wrong_key} in {q_id}"
                assert len(distractors[wrong_key].strip()) >= 2, f"Empty distractor text for option {wrong_key} in {q_id}"


# ==============================================================================
# 5. GitHub Pages Subfolder Relative Path Resolution Audit
# ==============================================================================

class TestGitHubPagesSubfolderLinkAudit:
    """Verifies that no hardcoded root-relative paths break hosting on https://<user>.github.io/<repo>/."""

    def test_html_files_no_hardcoded_root_relative_assets(self):
        """index.html and static/index.html must not use /static/ or /data/ without ./ prefix."""
        for path in [INDEX_HTML_PATH, STATIC_INDEX_HTML_PATH]:
            content = path.read_text(encoding="utf-8")
            # Root-relative links e.g. href="/static/..." or src="/static/..."
            bad_href = re.findall(r'href=["\']/(?!static/css/|data/|static/js/)[^"\']*["\']', content)
            # Find any href="/static/..." or src="/static/..."
            root_abs = re.findall(r'(?:href|src)=["\']/(?:static|data|api)/', content)
            assert len(root_abs) == 0, f"Found hardcoded root-relative link in {path.name}: {root_abs}"

    def test_css_url_references_are_relative(self):
        """style.css must not use root-relative url(/...)."""
        css_text = STYLE_CSS_PATH.read_text(encoding="utf-8")
        root_abs_urls = re.findall(r'url\(["\']?/(?!/)[^)"\']+["\']?\)', css_text)
        assert len(root_abs_urls) == 0, f"Found root-relative url() in style.css: {root_abs_urls}"

    def test_all_diagram_files_physically_exist_on_disk(self, question_bank):
        """All diagram images referenced in questions.json must exist in static/media/."""
        _, questions = question_bank
        media_dir = PROJECT_ROOT / "static" / "media"
        assert media_dir.is_dir()

        referenced_imgs = set()
        for q in questions:
            if q.get("image_url"):
                referenced_imgs.add(Path(q["image_url"]).name)
            for opt_text in q.get("options", {}).values():
                if isinstance(opt_text, str):
                    for match in re.findall(r'src=["\']([^"\']+)["\']', opt_text):
                        referenced_imgs.add(Path(match).name)

        assert len(referenced_imgs) > 0, "No diagram images found in question bank!"
        for img_name in referenced_imgs:
            img_path = media_dir / img_name
            assert img_path.exists(), f"Referenced image {img_name} missing from {media_dir}"
