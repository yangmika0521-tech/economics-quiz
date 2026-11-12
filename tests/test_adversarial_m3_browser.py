"""
tests/test_adversarial_m3_browser.py
=============================================================================
Adversarial Empirical Browser Stress Harness for Milestone 3 UI/UX:
- Viewport responsiveness (320px, 375px, 414px, 768px, 1024px, 1440px, 1920px)
- Touch target ergonomics (minimum 44px x 44px)
- Drawer toggle transitions, backdrop dismiss, ESC key handling
- Guardrail modal edge cases (unattempted questions, all attempted, submit anyway, chip navigation)
- Diagram zoom lightbox modal and image URL resolution
- Keyboard navigation (A-D, 1-4, Left/P, Right/N, F) & input suppression
- Dual-runtime execution (FastAPI backend mode vs static fallback mode)
=============================================================================
"""

import threading
import time
import socket
import pytest
from app.main import app
import uvicorn

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    """Spins up live FastAPI server on a free port in a background daemon thread."""
    port = find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    
    # Wait for server to start
    time.sleep(1.0)
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.should_exit = True


@pytest.fixture
def driver():
    """Provides a headless Chrome WebDriver configured for clean test execution."""
    if not SELENIUM_AVAILABLE:
        pytest.skip("Selenium not available")
        
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()


def set_viewport(driver, width, height):
    """Sets exact device viewport using Chrome DevTools Protocol (CDP)."""
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'width': int(width),
        'height': int(height),
        'deviceScaleFactor': 2 if width < 600 else 1,
        'mobile': bool(width < 768)
    })


@pytest.mark.skipif(not SELENIUM_AVAILABLE, reason="Selenium required for browser tests")
class TestMobileViewportAndResponsiveness:
    """Stress-tests viewports from 320px narrow mobile up to 1920px desktop."""

    @pytest.mark.parametrize("width,height", [
        (320, 568),   # iPhone SE (1st gen)
        (375, 667),   # iPhone SE (2nd/3rd gen)
        (414, 896),   # iPhone XR / Plus
        (768, 1024),  # iPad Portrait
        (1024, 768),  # iPad Landscape
        (1440, 900),  # Standard Desktop
        (1920, 1080), # 1080p Desktop
    ])
    def test_no_horizontal_overflow_in_setup_view(self, driver, live_server, width, height):
        set_viewport(driver, width, height)
        driver.get(live_server + "/")
        time.sleep(0.5)

        client_w = driver.execute_script("return document.documentElement.clientWidth;")
        scroll_w = driver.execute_script("return document.documentElement.scrollWidth;")
        assert scroll_w <= client_w, f"Horizontal overflow in Setup View at {width}px: scrollWidth={scroll_w} > clientWidth={client_w}"

    @pytest.mark.parametrize("width,height", [
        (320, 568),
        (375, 667),
        (414, 896),
        (768, 1024),
        (1024, 768),
        (1440, 900),
        (1920, 1080),
    ])
    def test_no_horizontal_overflow_in_quiz_view(self, driver, live_server, width, height):
        set_viewport(driver, width, height)
        driver.get(live_server + "/")
        time.sleep(0.5)

        # Start quiz
        btn_start = driver.find_element(By.ID, "btn-start-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
        time.sleep(0.5)

        client_w = driver.execute_script("return document.documentElement.clientWidth;")
        scroll_w = driver.execute_script("return document.documentElement.scrollWidth;")
        assert scroll_w <= client_w, f"Horizontal overflow in Quiz View at {width}px: scrollWidth={scroll_w} > clientWidth={client_w}"

    @pytest.mark.parametrize("width,height", [
        (320, 568),
        (375, 667),
        (414, 896),
        (768, 1024),
        (1440, 900),
    ])
    def test_no_horizontal_overflow_in_review_view(self, driver, live_server, width, height):
        set_viewport(driver, width, height)
        driver.get(live_server + "/")
        time.sleep(0.5)

        # Start quiz
        btn_start = driver.find_element(By.ID, "btn-start-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
        time.sleep(0.4)

        # Submit quiz via guardrail confirmation
        btn_submit = driver.find_element(By.ID, "btn-submit-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_submit)
        time.sleep(0.3)
        btn_confirm = driver.find_element(By.ID, "btn-guardrail-confirm")
        driver.execute_script("arguments[0].click();", btn_confirm)
        time.sleep(0.5)

        client_w = driver.execute_script("return document.documentElement.clientWidth;")
        scroll_w = driver.execute_script("return document.documentElement.scrollWidth;")
        assert scroll_w <= client_w, f"Horizontal overflow in Review View at {width}px: scrollWidth={scroll_w} > clientWidth={client_w}"


@pytest.mark.skipif(not SELENIUM_AVAILABLE, reason="Selenium required for browser tests")
class TestTouchTargetErgonomics:
    """Verifies that primary interactive buttons meet minimum touch target sizing (>= 44px)."""

    def test_primary_action_buttons_sizing(self, driver, live_server):
        set_viewport(driver, 375, 667)
        driver.get(live_server + "/")
        time.sleep(0.5)

        # Setup view: Start button, chips, and chapter cards
        start_btn = driver.find_element(By.ID, "btn-start-quiz")
        assert start_btn.rect['height'] >= 44, f"Start button height {start_btn.rect['height']} < 44px"

        chips = driver.find_elements(By.CLASS_NAME, "btn-chip")
        for idx, chip in enumerate(chips):
            assert chip.rect['height'] >= 44, f"Quick chip #{idx} height {chip.rect['height']} < 44px"

        count_chips = driver.find_elements(By.CLASS_NAME, "btn-count-chip")
        for idx, c_chip in enumerate(count_chips):
            assert c_chip.rect['height'] >= 44, f"Count chip #{idx} height {c_chip.rect['height']} < 44px"

        chapter_cards = driver.find_elements(By.CLASS_NAME, "chapter-card")
        for idx, card in enumerate(chapter_cards):
            assert card.rect['height'] >= 44, f"Chapter card #{idx} height {card.rect['height']} < 44px"

        # Start Quiz
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", start_btn)
        time.sleep(0.5)

        # Quiz view interactive controls
        flag_btn = driver.find_element(By.ID, "btn-flag-q")
        assert flag_btn.rect['height'] >= 44, f"Flag button height {flag_btn.rect['height']} < 44px"

        palette_toggle = driver.find_element(By.ID, "btn-toggle-palette")
        assert palette_toggle.rect['height'] >= 44, f"Palette toggle height {palette_toggle.rect['height']} < 44px"

        prev_btn = driver.find_element(By.ID, "btn-prev-q")
        next_btn = driver.find_element(By.ID, "btn-next-q")
        submit_btn = driver.find_element(By.ID, "btn-submit-quiz")
        assert prev_btn.rect['height'] >= 44, f"Prev button height {prev_btn.rect['height']} < 44px"
        assert next_btn.rect['height'] >= 44, f"Next button height {next_btn.rect['height']} < 44px"
        assert submit_btn.rect['height'] >= 44, f"Submit button height {submit_btn.rect['height']} < 44px"

        # Options
        options = driver.find_elements(By.CLASS_NAME, "option-item")
        for i, opt in enumerate(options):
            assert opt.rect['height'] >= 44, f"Option #{i} height {opt.rect['height']} < 44px"

        # Open Palette Drawer
        driver.execute_script("arguments[0].click();", palette_toggle)
        time.sleep(0.3)

        close_palette_btn = driver.find_element(By.ID, "btn-close-palette")
        assert close_palette_btn.rect['height'] >= 44 and close_palette_btn.rect['width'] >= 44, \
            f"Palette close button size {close_palette_btn.rect} < 44x44px"

        palette_btns = driver.find_elements(By.CLASS_NAME, "palette-btn")
        for i, p_btn in enumerate(palette_btns):
            assert p_btn.rect['height'] >= 44 and p_btn.rect['width'] >= 44, \
                f"Palette button #{i} size {p_btn.rect} < 44x44px"


@pytest.mark.skipif(not SELENIUM_AVAILABLE, reason="Selenium required for browser tests")
class TestDrawerAndModalInteractions:
    """Tests drawer and modal opening, closing, backdrop dismiss, and ESC handling."""

    def test_palette_drawer_lifecycle_and_dismissal(self, driver, live_server):
        set_viewport(driver, 375, 667)
        driver.get(live_server + "/")
        time.sleep(0.5)

        # Start Quiz
        btn_start = driver.find_element(By.ID, "btn-start-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
        time.sleep(0.5)

        drawer = driver.find_element(By.ID, "palette-drawer")
        btn_toggle = driver.find_element(By.ID, "btn-toggle-palette")
        backdrop = driver.find_element(By.ID, "palette-backdrop")
        btn_close = driver.find_element(By.ID, "btn-close-palette")

        # 1. Open drawer
        driver.execute_script("arguments[0].click();", btn_toggle)
        time.sleep(0.2)
        assert "open" in drawer.get_attribute("class")
        assert drawer.get_attribute("aria-hidden") == "false"

        # 2. Dismiss via backdrop click
        driver.execute_script("arguments[0].click();", backdrop)
        time.sleep(0.2)
        assert "open" not in drawer.get_attribute("class")
        assert drawer.get_attribute("aria-hidden") == "true"

        # 3. Open drawer -> Close via Close Button (✕)
        driver.execute_script("arguments[0].click();", btn_toggle)
        time.sleep(0.2)
        driver.execute_script("arguments[0].click();", btn_close)
        time.sleep(0.2)
        assert "open" not in drawer.get_attribute("class")

        # 4. Open drawer -> Dismiss via Escape key
        driver.execute_script("arguments[0].click();", btn_toggle)
        time.sleep(0.2)
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.2)
        assert "open" not in drawer.get_attribute("class")

    def test_guardrail_modal_logic_and_chip_navigation(self, driver, live_server):
        set_viewport(driver, 375, 667)
        driver.get(live_server + "/")
        time.sleep(0.5)

        btn_start = driver.find_element(By.ID, "btn-start-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
        time.sleep(0.5)

        # Answer only question 1
        options = driver.find_elements(By.CLASS_NAME, "option-item")
        driver.execute_script("arguments[0].click();", options[0])
        time.sleep(0.2)

        # Attempt to submit -> Guardrail modal must appear because questions are unattempted
        btn_submit = driver.find_element(By.ID, "btn-submit-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_submit)
        time.sleep(0.3)

        guardrail = driver.find_element(By.ID, "guardrail-modal")
        assert "open" in guardrail.get_attribute("class")
        count_elem = driver.find_element(By.ID, "guardrail-count")
        unanswered_count = int(count_elem.text.strip())
        assert unanswered_count > 0

        # Check chips in guardrail list
        chips = driver.find_elements(By.CLASS_NAME, "chip-q")
        assert len(chips) == unanswered_count

        # Click chip for question 2 -> should close modal and navigate to Q2
        driver.execute_script("arguments[0].click();", chips[0])
        time.sleep(0.3)
        assert "open" not in guardrail.get_attribute("class")

        # Reopen guardrail -> Test Cancel button ("繼續作答")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_submit)
        time.sleep(0.2)
        btn_cancel = driver.find_element(By.ID, "btn-guardrail-cancel")
        driver.execute_script("arguments[0].click();", btn_cancel)
        time.sleep(0.2)
        assert "open" not in guardrail.get_attribute("class")

        # Reopen guardrail -> Test ESC key dismissal
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_submit)
        time.sleep(0.2)
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.2)
        assert "open" not in guardrail.get_attribute("class")

    def test_guardrail_modal_bypass_when_all_answered(self, driver, live_server):
        """Verifies that when 100% of questions are answered, the guardrail modal is bypassed."""
        set_viewport(driver, 1024, 768)
        driver.get(live_server + "/")
        time.sleep(0.5)

        # Set count to 1 question via chip
        driver.execute_script("document.querySelector('[data-count=\"10\"]').click();")
        # Set count explicitly to 2 and dispatch change event to update state
        driver.execute_script("document.getElementById('input-count').value = '2'; document.getElementById('input-count').dispatchEvent(new Event('change'));")
        driver.execute_script("document.getElementById('slider-count').value = '2';")
        btn_start = driver.find_element(By.ID, "btn-start-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
        time.sleep(0.5)

        # Answer Q1
        opts1 = driver.find_elements(By.CLASS_NAME, "option-item")
        driver.execute_script("arguments[0].click();", opts1[0])
        time.sleep(0.2)

        # Go to Q2 and answer
        btn_next = driver.find_element(By.ID, "btn-next-q")
        driver.execute_script("arguments[0].click();", btn_next)
        time.sleep(0.2)
        opts2 = driver.find_elements(By.CLASS_NAME, "option-item")
        driver.execute_script("arguments[0].click();", opts2[1])
        time.sleep(0.2)

        # Submit quiz
        btn_submit = driver.find_element(By.ID, "btn-submit-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_submit)
        time.sleep(0.5)

        # Guardrail modal should NEVER have opened, and view-review should be active
        guardrail = driver.find_element(By.ID, "guardrail-modal")
        assert "open" not in guardrail.get_attribute("class"), "Guardrail modal should not open when all questions are answered"
        view_review = driver.find_element(By.ID, "view-review")
        assert "active" in view_review.get_attribute("class"), "Review view should immediately activate"

    def test_diagram_lightbox_modal_and_dismissal(self, driver, live_server):
        set_viewport(driver, 375, 667)
        driver.get(live_server + "/")
        time.sleep(0.5)

        test_img_url = "./static/media/ch02_fig1.png"
        driver.execute_script(f"window.appOpenDiagram('{test_img_url}');")
        time.sleep(0.3)

        diag_modal = driver.find_element(By.ID, "diagram-modal")
        assert "open" in diag_modal.get_attribute("class")
        modal_img = driver.find_element(By.ID, "diagram-modal-img")
        assert "ch02_fig1.png" in modal_img.get_attribute("src")

        # Dismiss via ESC
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.2)
        assert "open" not in diag_modal.get_attribute("class")

        # Reopen and dismiss via backdrop
        driver.execute_script(f"window.appOpenDiagram('{test_img_url}');")
        time.sleep(0.2)
        diag_backdrop = driver.find_element(By.ID, "diagram-backdrop")
        driver.execute_script("arguments[0].click();", diag_backdrop)
        time.sleep(0.2)
        assert "open" not in diag_modal.get_attribute("class")


@pytest.mark.skipif(not SELENIUM_AVAILABLE, reason="Selenium required for browser tests")
class TestKeyboardNavigationMatrix:
    """Tests keyboard shortcuts A-D, 1-4, Left/Right/P/N, F, and input field suppression."""

    def test_keyboard_option_selection_and_navigation(self, driver, live_server):
        set_viewport(driver, 1024, 768)
        driver.get(live_server + "/")
        time.sleep(0.5)

        btn_start = driver.find_element(By.ID, "btn-start-quiz")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
        time.sleep(0.5)

        body = driver.find_element(By.TAG_NAME, "body")

        # Press 'b' to select option B
        body.send_keys("b")
        time.sleep(0.2)
        options = driver.find_elements(By.CLASS_NAME, "option-item")
        assert "selected" in options[1].get_attribute("class"), "Option B should be selected after pressing 'b'"

        # Press '4' to switch to option D
        body.send_keys("4")
        time.sleep(0.2)
        options = driver.find_elements(By.CLASS_NAME, "option-item")
        assert "selected" in options[3].get_attribute("class"), "Option D should be selected after pressing '4'"

        # Press 'f' to toggle flag
        body.send_keys("f")
        time.sleep(0.2)
        flag_btn = driver.find_element(By.ID, "btn-flag-q")
        assert "active" in flag_btn.get_attribute("class"), "Flag button should be active after pressing 'f'"

        # Press 'n' to go to next question
        current_num_before = driver.find_element(By.ID, "current-q-num").text.strip()
        body.send_keys("n")
        time.sleep(0.2)
        current_num_after = driver.find_element(By.ID, "current-q-num").text.strip()
        assert int(current_num_after) == int(current_num_before) + 1, "Should advance to next question on 'n'"

        # Press ArrowLeft to go back to previous question
        body.send_keys(Keys.ARROW_LEFT)
        time.sleep(0.2)
        current_num_back = driver.find_element(By.ID, "current-q-num").text.strip()
        assert current_num_back == current_num_before, "Should return to previous question on ArrowLeft"

        # Verify flag state persisted on question 1
        flag_btn = driver.find_element(By.ID, "btn-flag-q")
        assert "active" in flag_btn.get_attribute("class"), "Flag state should persist on question 1"

    def test_keyboard_shortcuts_suppressed_when_typing_in_input(self, driver, live_server):
        set_viewport(driver, 1024, 768)
        driver.get(live_server + "/")
        time.sleep(0.5)

        # On setup view, focus inside number input
        input_count = driver.find_element(By.ID, "input-count")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].focus();", input_count)
        time.sleep(0.1)
        input_count.send_keys("1")
        time.sleep(0.1)

        # Verify we remain in setup view and no quiz shortcuts fired
        view_setup = driver.find_element(By.ID, "view-setup")
        assert "active" in view_setup.get_attribute("class")


@pytest.mark.skipif(not SELENIUM_AVAILABLE, reason="Selenium required for browser tests")
class TestDualRuntimeModes:
    """Verifies dual runtime: FastAPI backend mode vs Static fallback mode."""

    def test_fastapi_backend_mode_detection(self, driver, live_server):
        driver.get(live_server + "/")
        time.sleep(0.8)
        badge = driver.find_element(By.ID, "runtime-badge")
        assert "badge-api" in badge.get_attribute("class")
        assert "FastAPI" in badge.text

    def test_static_fallback_mode_execution(self, driver):
        """Spins up a pure static HTTP server without /api and verifies static fallback."""
        import http.server
        import socketserver
        
        port = find_free_port()
        class StaticHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
                
        httpd = socketserver.TCPServer(('127.0.0.1', port), StaticHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        
        try:
            driver.get(f"http://127.0.0.1:{port}/")
            time.sleep(1.5)
            badge = driver.find_element(By.ID, "runtime-badge")
            assert "badge-static" in badge.get_attribute("class")
            assert "GitHub Pages" in badge.text

            # Test that static quiz session can start and complete fully
            btn_start = driver.find_element(By.ID, "btn-start-quiz")
            driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_start)
            time.sleep(0.5)

            # Answer Q1
            opts = driver.find_elements(By.CLASS_NAME, "option-item")
            driver.execute_script("arguments[0].click();", opts[0])
            time.sleep(0.2)

            # Submit quiz
            btn_submit = driver.find_element(By.ID, "btn-submit-quiz")
            driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn_submit)
            time.sleep(0.3)
            btn_confirm = driver.find_element(By.ID, "btn-guardrail-confirm")
            driver.execute_script("arguments[0].click();", btn_confirm)
            time.sleep(0.5)

            # Review view should be active with score calculated client-side
            view_review = driver.find_element(By.ID, "view-review")
            assert "active" in view_review.get_attribute("class")
            score_text = driver.find_element(By.ID, "review-score-num").text.strip()
            assert score_text.isdigit()
        finally:
            httpd.shutdown()
