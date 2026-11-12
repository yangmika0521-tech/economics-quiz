/**
 * Economics Interactive Evaluation & Quiz Practice System
 * Single-Page Application (SPA) State Machine & Dual-Runtime Client
 * 
 * Supports:
 * - Dynamic Backend Mode: FastAPI (/api/chapters, /api/quiz/new, /api/quiz/submit)
 * - Pure Client-Side Static Mode: GitHub Pages / Local Static Fallback (./data/questions.json)
 * - Mobile-First Responsive UI, Touch Navigation, Keyboard Shortcuts & Guardrail Modals
 */

(function () {
  'use strict';

  // =========================================================================
  // State Machine Definition
  // =========================================================================

  const state = {
    runtimeMode: 'detecting', // 'api' | 'static'
    allChapters: [],          // Chapter metadata list
    rawQuestionsPool: [],     // All questions (used in static mode)
    selectedChapterIds: new Set(),
    requestedCount: 20,
    selectedMode: 'practice', // 'practice' | 'exam'
    
    // Active Quiz Session
    currentQuiz: {
      sessionId: null,
      mode: 'practice',
      questions: [],
      userAnswers: {},       // questionId -> 'a' | 'b' | 'c' | 'd'
      flaggedQuestionIds: new Set(),
      currentIndex: 0,
      startTime: null,
      timerInterval: null,
      elapsedSeconds: 0,
    },

    // Review / Submission Result
    submissionResult: null,
    currentReviewFilter: 'all', // 'all' | 'wrong' | 'flagged'
  };

  // =========================================================================
  // DOM Elements Cache
  // =========================================================================

  const dom = {
    // Header & Runtime Badge
    runtimeBadge: document.getElementById('runtime-badge'),
    btnNavHome: document.getElementById('btn-nav-home'),

    // Views
    viewSetup: document.getElementById('view-setup'),
    viewQuiz: document.getElementById('view-quiz'),
    viewReview: document.getElementById('view-review'),

    // Setup View Controls
    chapterList: document.getElementById('chapter-list'),
    poolCount: document.getElementById('pool-count'),
    btnSelectAll: document.getElementById('btn-select-all'),
    btnSelectCh1_3: document.getElementById('btn-select-ch1-3'),
    btnSelectCh4_6: document.getElementById('btn-select-ch4-6'),
    btnSelectReset: document.getElementById('btn-select-reset'),
    countDisplay: document.getElementById('count-display'),
    sliderCount: document.getElementById('slider-count'),
    inputCount: document.getElementById('input-count'),
    countChips: document.querySelectorAll('.btn-count-chip'),
    btnCountAll: document.getElementById('btn-count-all'),
    modeRadios: document.querySelectorAll('input[name="quiz-mode"]'),
    btnStartQuiz: document.getElementById('btn-start-quiz'),

    // Quiz View Controls
    quizModeTag: document.getElementById('quiz-mode-tag'),
    currentQChapter: document.getElementById('current-q-chapter'),
    currentQNum: document.getElementById('current-q-num'),
    totalQNum: document.getElementById('total-q-num'),
    quizTimer: document.getElementById('quiz-timer'),
    btnFlagQ: document.getElementById('btn-flag-q'),
    flagText: document.getElementById('flag-text'),
    btnTogglePalette: document.getElementById('btn-toggle-palette'),
    paletteSummaryCount: document.getElementById('palette-summary-count'),
    quizProgressBar: document.getElementById('quiz-progress-bar'),

    // Question Card
    stemQNumber: document.getElementById('stem-q-number'),
    questionStem: document.getElementById('question-stem'),
    questionContextTable: document.getElementById('question-context-table'),
    questionDiagramContainer: document.getElementById('question-diagram-container'),
    questionDiagramImg: document.getElementById('question-diagram-img'),
    questionOptions: document.getElementById('question-options'),

    // Quiz Navigation
    btnPrevQ: document.getElementById('btn-prev-q'),
    btnNextQ: document.getElementById('btn-next-q'),
    btnSubmitQuiz: document.getElementById('btn-submit-quiz'),

    // Review View Controls
    reviewScoreNum: document.getElementById('review-score-num'),
    reviewTotalNum: document.getElementById('review-total-num'),
    reviewPercentage: document.getElementById('review-percentage'),
    reviewTierBadge: document.getElementById('review-tier-badge'),
    reviewTimeElapsed: document.getElementById('review-time-elapsed'),
    reviewModeLabel: document.getElementById('review-mode-label'),
    reviewFlaggedCount: document.getElementById('review-flagged-count'),
    chapterBreakdownList: document.getElementById('chapter-breakdown-list'),
    btnFilterAll: document.getElementById('btn-filter-all'),
    btnFilterWrong: document.getElementById('btn-filter-wrong'),
    btnFilterFlagged: document.getElementById('btn-filter-flagged'),
    filterAllCount: document.getElementById('filter-all-count'),
    filterWrongCount: document.getElementById('filter-wrong-count'),
    filterFlaggedCount: document.getElementById('filter-flagged-count'),
    btnPracticeMissed: document.getElementById('btn-practice-missed'),
    btnNewQuiz: document.getElementById('btn-new-quiz'),
    reviewList: document.getElementById('review-list'),

    // Drawer & Modals
    paletteDrawer: document.getElementById('palette-drawer'),
    paletteBackdrop: document.getElementById('palette-backdrop'),
    btnClosePalette: document.getElementById('btn-close-palette'),
    drawerStats: document.getElementById('drawer-stats'),
    paletteGrid: document.getElementById('palette-grid'),

    guardrailModal: document.getElementById('guardrail-modal'),
    guardrailBackdrop: document.getElementById('guardrail-backdrop'),
    guardrailCount: document.getElementById('guardrail-count'),
    guardrailList: document.getElementById('guardrail-list'),
    btnGuardrailCancel: document.getElementById('btn-guardrail-cancel'),
    btnGuardrailConfirm: document.getElementById('btn-guardrail-confirm'),

    diagramModal: document.getElementById('diagram-modal'),
    diagramBackdrop: document.getElementById('diagram-backdrop'),
    btnCloseDiagram: document.getElementById('btn-close-diagram'),
    diagramModalImg: document.getElementById('diagram-modal-img'),
    diagramModalCaption: document.getElementById('diagram-modal-caption'),
  };

  // =========================================================================
  // Helper Utilities
  // =========================================================================

  /** Resolves media URL to handle GitHub Pages subpaths and relative environments. */
  function resolveMediaUrl(rawUrl) {
    if (!rawUrl) return '';
    if (rawUrl.startsWith('http://') || rawUrl.startsWith('https://')) return rawUrl;
    // Strip leading ./ or /
    const clean = rawUrl.replace(/^\.?\//, '');
    return './' + clean;
  }

  /** Resolves option text content that might contain embedded HTML <img> tags. */
  function formatOptionHtml(text) {
    if (!text) return '';
    if (typeof text !== 'string') return String(text);
    if (text.includes('<img')) {
      // Adjust any absolute /static/ paths to relative ./static/
      return text.replace(/src=["']\/?static\//g, 'src="./static/');
    }
    return escapeHtml(text);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /** Formats seconds into MM:SS. */
  function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  /** Converts a markdown-style table string into a styled HTML table. */
  function renderMarkdownTable(mdText) {
    if (!mdText) return '';
    const lines = mdText.trim().split('\n');
    let caption = '';
    const headers = [];
    const rows = [];
    let inTable = false;

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;

      if (line.startsWith('|') && line.endsWith('|')) {
        inTable = true;
        const cells = line.slice(1, -1).split('|').map(c => c.trim());
        // Skip separator line like |---|---|
        if (cells.every(c => /^:?-+:?$/.test(c))) {
          continue;
        }
        if (headers.length === 0) {
          headers.push(...cells);
        } else {
          rows.push(cells);
        }
      } else {
        if (!inTable) {
          caption += (caption ? ' ' : '') + line;
        }
      }
    }

    if (headers.length > 0) {
      let html = '<div class="table-responsive">';
      if (caption) {
        html += `<div class="table-caption">📋 ${escapeHtml(caption)}</div>`;
      }
      html += '<table class="context-table"><thead><tr>';
      headers.forEach(h => {
        html += `<th>${escapeHtml(h)}</th>`;
      });
      html += '</tr></thead><tbody>';
      rows.forEach(r => {
        html += '<tr>';
        r.forEach(c => {
          html += `<td>${escapeHtml(c)}</td>`;
        });
        html += '</tr>';
      });
      html += '</tbody></table></div>';
      return html;
    }

    return `<pre class="context-pre">${escapeHtml(mdText)}</pre>`;
  }

  // =========================================================================
  // Dual-Runtime Auto-Detection & Fallback Logic
  // =========================================================================

  /** Updates the visual runtime mode badge. */
  function updateRuntimeBadge(mode) {
    state.runtimeMode = mode;
    const badge = dom.runtimeBadge;
    if (!badge) return;

    badge.className = 'runtime-badge';
    const textSpan = badge.querySelector('.badge-text');

    if (mode === 'api') {
      badge.classList.add('badge-api');
      badge.title = 'FastAPI 動態後端連線正常';
      if (textSpan) textSpan.textContent = '🟢 API 連線模式 (FastAPI)';
    } else {
      badge.classList.add('badge-static');
      badge.title = '純靜態運行 (GitHub Pages / 離線模式)';
      if (textSpan) textSpan.textContent = '🌐 靜態運行模式 (GitHub Pages)';
    }
  }

  /**
   * Automatically detects the environment and initializes the question bank.
   * Tests GET /api/chapters; falls back to ./data/questions.json if unreachable.
   */
  async function initDualRuntime() {
    const isGitHubPages = window.location.hostname.endsWith('github.io');
    const isFileProto = window.location.protocol === 'file:';

    // If clearly in static hosting without backend, skip API ping
    if (isGitHubPages || isFileProto) {
      console.log('[Dual-Runtime] Detected GitHub Pages or file protocol -> Activating Static Mode');
      await activateStaticMode();
      return;
    }

    // Try pinging FastAPI /api/chapters with timeout
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1800);

      const resp = await fetch('/api/chapters', { signal: controller.signal });
      clearTimeout(timeoutId);

      if (resp.ok) {
        const data = await resp.json();
        if (data && Array.isArray(data.chapters) && data.chapters.length > 0) {
          state.allChapters = data.chapters;
          updateRuntimeBadge('api');
          console.log('[Dual-Runtime] FastAPI Backend connected successfully (API Mode)');
          renderChapterCards();
          return;
        }
      }
    } catch (err) {
      console.warn('[Dual-Runtime] FastAPI API endpoint unavailable or timed out:', err.message);
    }

    // Fallback to Static Mode
    console.log('[Dual-Runtime] Switching to Client-Side Static Mode...');
    await activateStaticMode();
  }

  /** Loads data/questions.json directly and activates static mode. */
  async function activateStaticMode() {
    updateRuntimeBadge('static');
    
    // Resolve relative path for data/questions.json
    let dataUrl = './data/questions.json';
    if (window.location.pathname.includes('/static/')) {
      dataUrl = '../data/questions.json';
    }

    try {
      const resp = await fetch(dataUrl);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status} fetching ${dataUrl}`);
      }
      const data = await resp.json();
      state.allChapters = data.chapters || [];
      state.rawQuestionsPool = data.questions || [];
      console.log(`[Dual-Runtime] Loaded ${state.rawQuestionsPool.length} questions across ${state.allChapters.length} chapters.`);
      renderChapterCards();
    } catch (err) {
      console.error('[Dual-Runtime] Failed to load static question bank:', err);
      if (dom.chapterList) {
        dom.chapterList.innerHTML = `
          <div class="loading-state" style="color: var(--color-danger);">
            ❌ 無法載入題庫資料 (${escapeHtml(err.message)})。<br>
            請確認 data/questions.json 檔案路徑正確。
          </div>
        `;
      }
    }
  }

  // =========================================================================
  // Client-Side Sampling & Evaluation Algorithms (Matching app.quiz_engine)
  // =========================================================================

  /**
   * Randomly samples questions without replacement from the pool, with boundary clamping.
   * Strictly matches Python app.quiz_engine.sample_questions() logic.
   */
  function clientSampleQuestions(pool, chapterIds, count) {
    if (!chapterIds || chapterIds.length === 0 || !pool || pool.length === 0) {
      return [];
    }

    const chSet = new Set(chapterIds);
    const eligible = pool.filter(q => chSet.has(q.chapter_id));

    if (eligible.length === 0) {
      return [];
    }

    let effectiveCount = count;
    if (effectiveCount <= 0) {
      effectiveCount = 1;
    } else if (effectiveCount > eligible.length) {
      effectiveCount = eligible.length;
    }

    // Fisher-Yates shuffle on copy
    const copy = [...eligible];
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const temp = copy[i];
      copy[i] = copy[j];
      copy[j] = temp;
    }

    return copy.slice(0, effectiveCount);
  }

  /**
   * Evaluates user submissions, calculates score, and generates diagnostics.
   * Strictly matches Python app.quiz_engine.evaluate_submission() logic.
   */
  function clientEvaluateSubmission(sampledQuestions, userAnswers) {
    const total = sampledQuestions.length;
    let correctCount = 0;
    const chapterBreakdown = {};
    const results = [];

    for (const q of sampledQuestions) {
      const qId = q.id;
      const chId = q.chapter_id || 'Unknown';
      const userAns = (userAnswers && userAnswers[qId]) ? String(userAnswers[qId]).trim().toLowerCase() : null;
      const correctAns = q.correct_answer ? String(q.correct_answer).trim().toLowerCase() : '';

      const isCorrect = (userAns !== null && userAns === correctAns);
      if (isCorrect) correctCount++;

      // Track chapter breakdown
      if (!chapterBreakdown[chId]) {
        chapterBreakdown[chId] = { correct: 0, total: 0 };
      }
      chapterBreakdown[chId].total++;
      if (isCorrect) {
        chapterBreakdown[chId].correct++;
      }

      // Build diagnostic result item
      results.push({
        question_id: qId,
        stem: q.stem,
        user_answer: userAns,
        correct_answer: correctAns,
        is_correct: isCorrect,
        image_url: q.image_url || null,
        context_table: q.context_table || null,
        explanation_zh: q.explanation_zh || null,
      });
    }

    const scorePct = total > 0 ? Number(((correctCount / total) * 100).toFixed(2)) : 0.0;

    return {
      total_questions: total,
      correct_count: correctCount,
      score_percentage: scorePct,
      chapter_breakdown: chapterBreakdown,
      results: results,
    };
  }

  // =========================================================================
  // VIEW 1: SETUP & CONFIGURATION LOGIC
  // =========================================================================

  /** Renders chapter selection cards. */
  function renderChapterCards() {
    if (!dom.chapterList) return;
    dom.chapterList.innerHTML = '';

    if (state.allChapters.length === 0) {
      dom.chapterList.innerHTML = '<div class="loading-state">暫無章節資料</div>';
      return;
    }

    // Select all chapters by default initially
    state.selectedChapterIds = new Set(state.allChapters.map(c => c.id));

    state.allChapters.forEach(ch => {
      const card = document.createElement('label');
      card.className = 'chapter-card selected';
      card.dataset.chapterId = ch.id;

      card.innerHTML = `
        <input type="checkbox" class="chapter-checkbox" value="${ch.id}" checked>
        <div class="chapter-info">
          <div class="chapter-header-line">
            <span class="chapter-num-badge">Ch ${ch.number}</span>
            <span class="chapter-count-badge">${ch.total_questions} 題</span>
          </div>
          <div class="chapter-title-zh">${escapeHtml(ch.title_zh)}</div>
          <div class="chapter-title-en">${escapeHtml(ch.title_en)}</div>
        </div>
      `;

      const checkbox = card.querySelector('.chapter-checkbox');
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) {
          state.selectedChapterIds.add(ch.id);
          card.classList.add('selected');
        } else {
          state.selectedChapterIds.delete(ch.id);
          card.classList.remove('selected');
        }
        onChapterSelectionChanged();
      });

      dom.chapterList.appendChild(card);
    });

    onChapterSelectionChanged();
  }

  /** Computes the total selectable question pool count based on selected chapters. */
  function getSelectedPoolSize() {
    return state.allChapters
      .filter(c => state.selectedChapterIds.has(c.id))
      .reduce((sum, c) => sum + c.total_questions, 0);
  }

  /** Triggered when chapter selection changes to adjust pool count and clamp slider bounds. */
  function onChapterSelectionChanged() {
    const poolSize = getSelectedPoolSize();
    if (dom.poolCount) dom.poolCount.textContent = poolSize;
    if (dom.btnCountAll) dom.btnCountAll.textContent = `全部 (${poolSize} 題)`;

    // Update quick chips active state
    updateQuickSelectorChips();

    // Clamp count slider and input
    const maxCount = Math.max(1, poolSize);
    if (dom.sliderCount) dom.sliderCount.max = maxCount;
    if (dom.inputCount) dom.inputCount.max = maxCount;

    let currentVal = parseInt(dom.inputCount.value, 10) || 20;
    if (currentVal > poolSize && poolSize > 0) {
      currentVal = poolSize;
    } else if (currentVal <= 0) {
      currentVal = 1;
    }
    setQuestionCount(currentVal);
  }

  /** Sets the question count and synchronizes slider, input, and chips. */
  function setQuestionCount(count) {
    const poolSize = getSelectedPoolSize();
    let clamped = count;
    if (count === 'all' || count > poolSize) {
      clamped = poolSize > 0 ? poolSize : 1;
    } else if (count <= 0) {
      clamped = 1;
    }

    state.requestedCount = clamped;
    if (dom.countDisplay) dom.countDisplay.textContent = clamped;
    if (dom.inputCount) dom.inputCount.value = clamped;
    if (dom.sliderCount) dom.sliderCount.value = clamped;

    // Highlight matching chip if any
    dom.countChips.forEach(chip => {
      const chipVal = chip.dataset.count;
      if (chipVal === 'all') {
        chip.classList.toggle('active', clamped === poolSize);
      } else {
        chip.classList.toggle('active', parseInt(chipVal, 10) === clamped);
      }
    });
  }

  /** Updates quick chapter selector buttons state. */
  function updateQuickSelectorChips() {
    const totalChapters = state.allChapters.length;
    const selectedCount = state.selectedChapterIds.size;

    dom.btnSelectAll?.classList.toggle('active', selectedCount === totalChapters);

    const ch1_3_ids = new Set(['Ch_01', 'Ch_02', 'Ch_03']);
    const isCh1_3 = selectedCount === 3 && [...state.selectedChapterIds].every(id => ch1_3_ids.has(id));
    dom.btnSelectCh1_3?.classList.toggle('active', isCh1_3);

    const ch4_6_ids = new Set(['Ch_04', 'Ch_05', 'Ch_06']);
    const isCh4_6 = selectedCount === 3 && [...state.selectedChapterIds].every(id => ch4_6_ids.has(id));
    dom.btnSelectCh4_6?.classList.toggle('active', isCh4_6);
  }

  /** Applies chapter selection filter. */
  function applyChapterSelection(filterFn) {
    state.selectedChapterIds.clear();
    const cards = dom.chapterList.querySelectorAll('.chapter-card');

    cards.forEach(card => {
      const chId = card.dataset.chapterId;
      const checkbox = card.querySelector('.chapter-checkbox');
      const isSelected = filterFn(chId);

      checkbox.checked = isSelected;
      if (isSelected) {
        state.selectedChapterIds.add(chId);
        card.classList.add('selected');
      } else {
        card.classList.remove('selected');
      }
    });

    onChapterSelectionChanged();
  }

  /** Starts a new quiz session with validation. */
  async function startQuiz() {
    if (state.selectedChapterIds.size === 0) {
      alert('請至少勾選一個欲測驗的章節！');
      return;
    }

    const count = state.requestedCount;
    const chapterIds = Array.from(state.selectedChapterIds);
    const mode = state.selectedMode;

    dom.btnStartQuiz.disabled = true;
    dom.btnStartQuiz.innerHTML = '<span class="spinner"></span> 準備試題中...';

    try {
      let sessionData = null;

      if (state.runtimeMode === 'api') {
        const resp = await fetch('/api/quiz/new', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chapter_ids: chapterIds,
            question_count: count,
            mode: mode,
          }),
        });

        if (!resp.ok) {
          throw new Error(`建立測驗失敗 (HTTP ${resp.status})`);
        }
        sessionData = await resp.json();
      } else {
        // Static mode
        const sampled = clientSampleQuestions(state.rawQuestionsPool, chapterIds, count);
        if (sampled.length === 0) {
          throw new Error('選取的章節中無可用試題！');
        }
        sessionData = {
          session_id: 'static-session-' + Date.now(),
          mode: mode,
          total_questions: sampled.length,
          questions: sampled,
        };
      }

      // Initialize quiz state
      initializeQuizSession(sessionData);
      switchView('quiz');
    } catch (err) {
      console.error('[Quiz Start] Error:', err);
      alert(`測驗啟動失敗：${err.message}`);
    } finally {
      dom.btnStartQuiz.disabled = false;
      dom.btnStartQuiz.innerHTML = '🚀 開始測驗 (Start Quiz)';
    }
  }

  // =========================================================================
  // VIEW 2: INTERACTIVE QUIZ LOGIC & CONTROLS
  // =========================================================================

  /** Sets up the active quiz session and starts timer. */
  function initializeQuizSession(sessionData) {
    state.currentQuiz = {
      sessionId: sessionData.session_id,
      mode: sessionData.mode || state.selectedMode,
      questions: sessionData.questions,
      userAnswers: {},
      flaggedQuestionIds: new Set(),
      currentIndex: 0,
      startTime: Date.now(),
      timerInterval: null,
      elapsedSeconds: 0,
    };

    // Update Header Tag & Totals
    if (dom.quizModeTag) {
      dom.quizModeTag.textContent = state.currentQuiz.mode === 'exam' ? '⏱️ 正式測驗' : '📖 練習模式';
    }
    if (dom.totalQNum) {
      dom.totalQNum.textContent = state.currentQuiz.questions.length;
    }

    // Start Timer
    startQuizTimer();

    // Render Question & Palette
    renderCurrentQuestion();
    renderPaletteButtons();
  }

  /** Starts the quiz timer. */
  function startQuizTimer() {
    if (state.currentQuiz.timerInterval) {
      clearInterval(state.currentQuiz.timerInterval);
    }
    state.currentQuiz.elapsedSeconds = 0;
    if (dom.quizTimer) dom.quizTimer.textContent = '00:00';

    state.currentQuiz.timerInterval = setInterval(() => {
      state.currentQuiz.elapsedSeconds++;
      if (dom.quizTimer) {
        dom.quizTimer.textContent = formatTime(state.currentQuiz.elapsedSeconds);
      }
    }, 1000);
  }

  /** Stops the quiz timer. */
  function stopQuizTimer() {
    if (state.currentQuiz.timerInterval) {
      clearInterval(state.currentQuiz.timerInterval);
      state.currentQuiz.timerInterval = null;
    }
  }

  /** Renders the current question card. */
  function renderCurrentQuestion() {
    const qIndex = state.currentQuiz.currentIndex;
    const qList = state.currentQuiz.questions;
    const q = qList[qIndex];
    if (!q) return;

    // Update progress numbers
    if (dom.currentQNum) dom.currentQNum.textContent = qIndex + 1;
    if (dom.stemQNumber) dom.stemQNumber.textContent = qIndex + 1;
    if (dom.currentQChapter) {
      const chNum = q.chapter_id.replace('Ch_0', '第 ').replace('Ch_', '第 ') + ' 章';
      dom.currentQChapter.textContent = chNum;
    }

    // Update Progress Bar
    if (dom.quizProgressBar) {
      const pct = ((qIndex + 1) / qList.length) * 100;
      dom.quizProgressBar.style.width = `${pct}%`;
    }

    // Update Flag button state
    const isFlagged = state.currentQuiz.flaggedQuestionIds.has(q.id);
    if (dom.btnFlagQ) {
      dom.btnFlagQ.classList.toggle('active', isFlagged);
      if (dom.flagText) {
        dom.flagText.textContent = isFlagged ? '已標記此題' : '標記此題';
      }
    }

    // Render Stem
    if (dom.questionStem) {
      dom.questionStem.textContent = q.stem;
    }

    // Render Context Table
    if (dom.questionContextTable) {
      if (q.context_table) {
        dom.questionContextTable.innerHTML = renderMarkdownTable(q.context_table);
        dom.questionContextTable.classList.remove('hidden');
      } else {
        dom.questionContextTable.innerHTML = '';
        dom.questionContextTable.classList.add('hidden');
      }
    }

    // Render Diagram Image
    if (dom.questionDiagramContainer && dom.questionDiagramImg) {
      if (q.image_url) {
        const resolvedUrl = resolveMediaUrl(q.image_url);
        dom.questionDiagramImg.src = resolvedUrl;
        dom.questionDiagramImg.alt = `第 ${qIndex + 1} 題經濟學圖表`;
        dom.questionDiagramContainer.classList.remove('hidden');
        
        // Click to open diagram modal
        dom.questionDiagramContainer.onclick = () => {
          openDiagramModal(resolvedUrl, `第 ${qIndex + 1} 題：${q.stem.substring(0, 35)}...`);
        };
      } else {
        dom.questionDiagramImg.src = '';
        dom.questionDiagramContainer.classList.add('hidden');
        dom.questionDiagramContainer.onclick = null;
      }
    }

    // Render Options A, B, C, D
    renderQuestionOptions(q);

    // Update Nav Buttons
    if (dom.btnPrevQ) {
      dom.btnPrevQ.disabled = (qIndex === 0);
    }
    if (dom.btnNextQ) {
      const isLast = (qIndex === qList.length - 1);
      dom.btnNextQ.innerHTML = isLast 
        ? '交卷 📋 <span class="shortcut-hint">[Enter]</span>' 
        : '下一題 ➡️ <span class="shortcut-hint">[N / →]</span>';
    }

    // Update Palette active state
    updatePaletteStatus();
  }

  /** Renders options for the active question. */
  function renderQuestionOptions(q) {
    if (!dom.questionOptions) return;
    dom.questionOptions.innerHTML = '';

    const currentAnswer = state.currentQuiz.userAnswers[q.id];
    const optionKeys = ['a', 'b', 'c', 'd'];

    optionKeys.forEach(key => {
      const optText = q.options ? q.options[key] : '';
      if (!optText && optText !== '') return;

      const item = document.createElement('label');
      item.className = 'option-item';
      item.dataset.optionKey = key;
      if (currentAnswer === key) {
        item.classList.add('selected');
      }

      item.innerHTML = `
        <input type="radio" name="active-q-option" value="${key}" class="option-radio" ${currentAnswer === key ? 'checked' : ''}>
        <span class="option-key-badge">${key.toUpperCase()}</span>
        <div class="option-content">${formatOptionHtml(optText)}</div>
      `;

      item.addEventListener('click', (e) => {
        // If clicking on an image inside option, open lightbox
        if (e.target.tagName.toLowerCase() === 'img') {
          openDiagramModal(e.target.src, `選項 ${key.toUpperCase()} 圖表`);
          return;
        }
        selectOption(key);
      });

      dom.questionOptions.appendChild(item);
    });
  }

  /** Selects an option for the current question. */
  function selectOption(key) {
    const qIndex = state.currentQuiz.currentIndex;
    const q = state.currentQuiz.questions[qIndex];
    if (!q) return;

    state.currentQuiz.userAnswers[q.id] = key;

    // Update UI option items
    const optionItems = dom.questionOptions.querySelectorAll('.option-item');
    optionItems.forEach(item => {
      const isSelected = item.dataset.optionKey === key;
      item.classList.toggle('selected', isSelected);
      const radio = item.querySelector('.option-radio');
      if (radio) radio.checked = isSelected;
    });

    // Update Palette badge
    updatePaletteStatus();
  }

  /** Toggles flag on current question. */
  function toggleFlagCurrentQuestion() {
    const qIndex = state.currentQuiz.currentIndex;
    const q = state.currentQuiz.questions[qIndex];
    if (!q) return;

    if (state.currentQuiz.flaggedQuestionIds.has(q.id)) {
      state.currentQuiz.flaggedQuestionIds.delete(q.id);
    } else {
      state.currentQuiz.flaggedQuestionIds.add(q.id);
    }

    const isFlagged = state.currentQuiz.flaggedQuestionIds.has(q.id);
    if (dom.btnFlagQ) {
      dom.btnFlagQ.classList.toggle('active', isFlagged);
      if (dom.flagText) {
        dom.flagText.textContent = isFlagged ? '已標記此題' : '標記此題';
      }
    }

    updatePaletteStatus();
  }

  /** Navigates to a specific question index. */
  function goToQuestion(index) {
    if (index < 0 || index >= state.currentQuiz.questions.length) return;
    state.currentQuiz.currentIndex = index;
    renderCurrentQuestion();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function nextQuestion() {
    const qIndex = state.currentQuiz.currentIndex;
    if (qIndex < state.currentQuiz.questions.length - 1) {
      goToQuestion(qIndex + 1);
    } else {
      // Last question: trigger submit flow
      checkAndSubmitQuiz();
    }
  }

  function prevQuestion() {
    const qIndex = state.currentQuiz.currentIndex;
    if (qIndex > 0) {
      goToQuestion(qIndex - 1);
    }
  }

  // =========================================================================
  // QUESTION PALETTE DRAWER
  // =========================================================================

  /** Generates question buttons inside the palette drawer. */
  function renderPaletteButtons() {
    if (!dom.paletteGrid) return;
    dom.paletteGrid.innerHTML = '';

    const questions = state.currentQuiz.questions;
    questions.forEach((q, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'palette-btn unanswered';
      btn.dataset.index = idx;
      btn.dataset.questionId = q.id;
      btn.textContent = idx + 1;
      btn.title = `跳轉至第 ${idx + 1} 題`;

      btn.addEventListener('click', () => {
        goToQuestion(idx);
        closePaletteDrawer();
      });

      dom.paletteGrid.appendChild(btn);
    });

    updatePaletteStatus();
  }

  /** Updates classes and statistics for palette buttons and counter. */
  function updatePaletteStatus() {
    const questions = state.currentQuiz.questions;
    const userAnswers = state.currentQuiz.userAnswers;
    const flagged = state.currentQuiz.flaggedQuestionIds;
    const currentIdx = state.currentQuiz.currentIndex;

    let answeredCount = 0;

    questions.forEach((q, idx) => {
      const btn = dom.paletteGrid?.querySelector(`.palette-btn[data-index="${idx}"]`);
      if (!btn) return;

      const isAnswered = Boolean(userAnswers[q.id]);
      if (isAnswered) answeredCount++;
      const isCurrent = (idx === currentIdx);
      const isFlagged = flagged.has(q.id);

      btn.className = 'palette-btn';
      if (isAnswered) btn.classList.add('answered');
      else btn.classList.add('unanswered');

      if (isCurrent) btn.classList.add('current');
      if (isFlagged) btn.classList.add('flagged');
    });

    const total = questions.length;
    const summaryText = `${answeredCount}/${total}`;

    if (dom.paletteSummaryCount) dom.paletteSummaryCount.textContent = summaryText;
    if (dom.drawerStats) dom.drawerStats.textContent = `已答 ${answeredCount} / ${total} 題`;
  }

  function openPaletteDrawer() {
    if (!dom.paletteDrawer) return;
    dom.paletteDrawer.classList.add('open');
    dom.paletteDrawer.setAttribute('aria-hidden', 'false');
  }

  function closePaletteDrawer() {
    if (!dom.paletteDrawer) return;
    dom.paletteDrawer.classList.remove('open');
    dom.paletteDrawer.setAttribute('aria-hidden', 'true');
  }

  // =========================================================================
  // SUBMISSION GUARDRAIL MODAL
  // =========================================================================

  /** Checks for unattempted questions before submitting. */
  function checkAndSubmitQuiz() {
    const questions = state.currentQuiz.questions;
    const userAnswers = state.currentQuiz.userAnswers;

    const unansweredIndices = [];
    questions.forEach((q, idx) => {
      if (!userAnswers[q.id]) {
        unansweredIndices.push(idx + 1);
      }
    });

    if (unansweredIndices.length > 0) {
      // Show guardrail modal
      openGuardrailModal(unansweredIndices);
    } else {
      // All answered -> proceed to submit
      executeQuizSubmission();
    }
  }

  function openGuardrailModal(unansweredIndices) {
    if (!dom.guardrailModal) return;

    if (dom.guardrailCount) dom.guardrailCount.textContent = unansweredIndices.length;
    if (dom.guardrailList) {
      dom.guardrailList.innerHTML = '';
      unansweredIndices.forEach(num => {
        const chip = document.createElement('span');
        chip.className = 'chip-q';
        chip.textContent = `第 ${num} 題`;
        chip.style.cursor = 'pointer';
        chip.title = `點擊直接作答第 ${num} 題`;
        chip.addEventListener('click', () => {
          closeGuardrailModal();
          goToQuestion(num - 1);
        });
        dom.guardrailList.appendChild(chip);
      });
    }

    dom.guardrailModal.classList.add('open');
    dom.guardrailModal.setAttribute('aria-hidden', 'false');
  }

  function closeGuardrailModal() {
    if (!dom.guardrailModal) return;
    dom.guardrailModal.classList.remove('open');
    dom.guardrailModal.setAttribute('aria-hidden', 'true');
  }

  /** Executes quiz submission to API or static evaluator. */
  async function executeQuizSubmission() {
    closeGuardrailModal();
    stopQuizTimer();

    const sessionId = state.currentQuiz.sessionId;
    const answers = state.currentQuiz.userAnswers;
    const questions = state.currentQuiz.questions;

    // Show loading state on submit button
    if (dom.btnSubmitQuiz) {
      dom.btnSubmitQuiz.disabled = true;
      dom.btnSubmitQuiz.textContent = '評分計算中...';
    }

    try {
      let result = null;

      if (state.runtimeMode === 'api') {
        const resp = await fetch('/api/quiz/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            answers: answers,
          }),
        });

        if (!resp.ok) {
          throw new Error(`交卷評分失敗 (HTTP ${resp.status})`);
        }
        result = await resp.json();
      } else {
        // Client-side evaluation
        result = clientEvaluateSubmission(questions, answers);
      }

      state.submissionResult = result;
      renderReviewView();
      switchView('review');
    } catch (err) {
      console.error('[Quiz Submit] Error:', err);
      alert(`交卷失敗：${err.message}`);
    } finally {
      if (dom.btnSubmitQuiz) {
        dom.btnSubmitQuiz.disabled = false;
        dom.btnSubmitQuiz.textContent = '📋 立即交卷';
      }
    }
  }

  // =========================================================================
  // VIEW 3: SCORE & DIAGNOSTIC REVIEW
  // =========================================================================

  /** Renders the score hero card, chapter breakdown, and diagnostic cards. */
  function renderReviewView() {
    const res = state.submissionResult;
    if (!res) return;

    // 1. Score Summary
    if (dom.reviewScoreNum) dom.reviewScoreNum.textContent = res.correct_count;
    if (dom.reviewTotalNum) dom.reviewTotalNum.textContent = res.total_questions;
    if (dom.reviewPercentage) dom.reviewPercentage.textContent = `${res.score_percentage.toFixed(1)}%`;
    if (dom.reviewTimeElapsed) dom.reviewTimeElapsed.textContent = formatTime(state.currentQuiz.elapsedSeconds);
    if (dom.reviewModeLabel) {
      dom.reviewModeLabel.textContent = state.currentQuiz.mode === 'exam' ? '正式測驗' : '練習模式';
    }
    if (dom.reviewFlaggedCount) {
      dom.reviewFlaggedCount.textContent = state.currentQuiz.flaggedQuestionIds.size;
    }

    // Performance Tier Badge
    if (dom.reviewTierBadge) {
      const pct = res.score_percentage;
      dom.reviewTierBadge.className = 'tier-badge';
      if (pct >= 90) {
        dom.reviewTierBadge.classList.add('tier-mastery');
        dom.reviewTierBadge.textContent = '🎯 精熟卓越 (Mastery)';
      } else if (pct >= 70) {
        dom.reviewTierBadge.classList.add('tier-good');
        dom.reviewTierBadge.textContent = '📈 良好穩定 (Proficient)';
      } else {
        dom.reviewTierBadge.classList.add('tier-practice');
        dom.reviewTierBadge.textContent = '💪 需加強複習 (Needs Review)';
      }
    }

    // 2. Chapter Breakdown
    renderChapterBreakdown(res.chapter_breakdown);

    // 3. Filter Counts
    const wrongCount = res.results.filter(r => !r.is_correct).length;
    const flaggedCount = res.results.filter(r => state.currentQuiz.flaggedQuestionIds.has(r.question_id)).length;

    if (dom.filterAllCount) dom.filterAllCount.textContent = res.total_questions;
    if (dom.filterWrongCount) dom.filterWrongCount.textContent = wrongCount;
    if (dom.filterFlaggedCount) dom.filterFlaggedCount.textContent = flaggedCount;

    // Show/hide Practice Missed button
    if (dom.btnPracticeMissed) {
      dom.btnPracticeMissed.style.display = (wrongCount > 0) ? 'inline-flex' : 'none';
    }

    // 4. Render Diagnostic Cards
    state.currentReviewFilter = 'all';
    renderDiagnosticCards();
  }

  /** Renders chapter breakdown progress bars. */
  function renderChapterBreakdown(breakdown) {
    if (!dom.chapterBreakdownList) return;
    dom.chapterBreakdownList.innerHTML = '';

    if (!breakdown || Object.keys(breakdown).length === 0) {
      dom.chapterBreakdownList.innerHTML = '<p class="text-muted">無分章資料</p>';
      return;
    }

    Object.keys(breakdown).sort().forEach(chId => {
      const data = breakdown[chId];
      const pct = data.total > 0 ? (data.correct / data.total) * 100 : 0;

      let fillClass = 'fill-high';
      if (pct < 60) fillClass = 'fill-low';
      else if (pct < 80) fillClass = 'fill-med';

      const item = document.createElement('div');
      item.className = 'breakdown-item';
      item.innerHTML = `
        <div class="breakdown-header">
          <span>${chId.replace('Ch_0', '第 ').replace('Ch_', '第 ')} 章</span>
          <span><strong>${data.correct}</strong> / ${data.total} 題 (${pct.toFixed(0)}%)</span>
        </div>
        <div class="breakdown-track">
          <div class="breakdown-fill ${fillClass}" style="width: ${pct}%;"></div>
        </div>
      `;

      dom.chapterBreakdownList.appendChild(item);
    });
  }

  /** Renders diagnostic question review cards based on current filter. */
  function renderDiagnosticCards() {
    if (!dom.reviewList || !state.submissionResult) return;
    dom.reviewList.innerHTML = '';

    const results = state.submissionResult.results;
    const filter = state.currentReviewFilter;
    const flaggedSet = state.currentQuiz.flaggedQuestionIds;

    const filtered = results.filter(r => {
      if (filter === 'wrong') return !r.is_correct;
      if (filter === 'flagged') return flaggedSet.has(r.question_id);
      return true;
    });

    if (filtered.length === 0) {
      dom.reviewList.innerHTML = `
        <div class="loading-state">
          🎉 本篩選條件下沒有試題！
        </div>
      `;
      return;
    }

    filtered.forEach((r, idx) => {
      // Find original question data for options text
      const origQ = state.currentQuiz.questions.find(q => q.id === r.question_id) || {};
      const card = document.createElement('div');
      card.className = `card review-q-card ${r.is_correct ? 'is-correct-card' : 'is-wrong-card'}`;

      // Status Badge
      const statusBadgeHtml = r.is_correct
        ? '<span class="review-status-badge status-badge-correct">✔️ 答對</span>'
        : '<span class="review-status-badge status-badge-wrong">❌ 答錯</span>';

      // Options Display Rows
      let optionsHtml = '<div class="review-options-grid">';
      const optionKeys = ['a', 'b', 'c', 'd'];
      optionKeys.forEach(optKey => {
        const optText = (origQ.options && origQ.options[optKey]) ? origQ.options[optKey] : '';
        const isUserSelected = (r.user_answer === optKey);
        const isCorrectAnswer = (r.correct_answer === optKey);

        let rowClass = 'review-option-row';
        let indicatorHtml = '';

        if (isCorrectAnswer) {
          rowClass += ' answer-correct';
          indicatorHtml = '<span class="opt-indicator opt-indicator-correct">正解 ✔️</span>';
        }
        if (isUserSelected && !r.is_correct) {
          rowClass += ' user-wrong';
          indicatorHtml = '<span class="opt-indicator opt-indicator-user">您的作答 ❌</span>';
        } else if (isUserSelected && r.is_correct) {
          indicatorHtml = '<span class="opt-indicator opt-indicator-correct">您的作答 ✔️</span>';
        }

        optionsHtml += `
          <div class="${rowClass}">
            <strong>${optKey.toUpperCase()}.</strong>
            <div style="flex:1;">${formatOptionHtml(optText)}</div>
            ${indicatorHtml}
          </div>
        `;
      });
      optionsHtml += '</div>';

      // Diagram if present
      let diagramHtml = '';
      if (r.image_url) {
        const resolvedUrl = resolveMediaUrl(r.image_url);
        diagramHtml = `
          <div class="diagram-container" style="cursor: zoom-in;" onclick="window.appOpenDiagram('${resolvedUrl}')">
            <div class="diagram-box">
              <img src="${resolvedUrl}" alt="圖表" class="diagram-img" loading="lazy">
              <div class="diagram-zoom-hint">🔍 點擊放大檢視</div>
            </div>
          </div>
        `;
      }

      // Context table if present
      let tableHtml = '';
      if (r.context_table) {
        tableHtml = `<div class="context-table-wrapper">${renderMarkdownTable(r.context_table)}</div>`;
      }

      // Structured Chinese Explanation
      let explHtml = '';
      if (r.explanation_zh) {
        const exp = r.explanation_zh;
        
        // Distractors list
        let distHtml = '';
        if (exp.distractors && Object.keys(exp.distractors).length > 0) {
          distHtml = '<div class="diagnostic-box diagnostic-distractors">';
          distHtml += '<div class="diagnostic-header">⚠️ 【干擾項辨析】</div><div class="diagnostic-body">';
          Object.keys(exp.distractors).sort().forEach(k => {
            distHtml += `<div class="distractor-item"><strong>選項 ${k.toUpperCase()}：</strong>${escapeHtml(exp.distractors[k])}</div>`;
          });
          distHtml += '</div></div>';
        }

        explHtml = `
          <div class="diagnostic-explanation-container">
            ${exp.concept ? `
              <div class="diagnostic-box diagnostic-concept">
                <div class="diagnostic-header">💡 【考點核心】</div>
                <div class="diagnostic-body">${escapeHtml(exp.concept)}</div>
              </div>
            ` : ''}

            ${exp.rationale ? `
              <div class="diagnostic-box diagnostic-rationale">
                <div class="diagnostic-header">📖 【正解詳析】</div>
                <div class="diagnostic-body">${escapeHtml(exp.rationale)}</div>
              </div>
            ` : ''}

            ${distHtml}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="review-card-header">
          <div>
            <strong>第 ${idx + 1} 題</strong> 
            <span class="tag tag-chapter" style="margin-left: 0.5rem;">${r.question_id}</span>
          </div>
          <div>${statusBadgeHtml}</div>
        </div>

        <div class="review-stem">${escapeHtml(r.stem)}</div>
        ${tableHtml}
        ${diagramHtml}
        ${optionsHtml}
        ${explHtml}
      `;

      dom.reviewList.appendChild(card);
    });
  }

  /** Starts a new practice session containing ONLY the missed questions. */
  function practiceMissedOnly() {
    if (!state.submissionResult) return;
    const wrongResults = state.submissionResult.results.filter(r => !r.is_correct);

    if (wrongResults.length === 0) {
      alert('太棒了！您本次測驗沒有任何錯題！');
      return;
    }

    // Find original question objects
    const missedQuestions = [];
    wrongResults.forEach(r => {
      const q = state.currentQuiz.questions.find(orig => orig.id === r.question_id);
      if (q) missedQuestions.push(q);
    });

    const newSession = {
      session_id: 'retry-session-' + Date.now(),
      mode: 'practice',
      total_questions: missedQuestions.length,
      questions: missedQuestions,
    };

    initializeQuizSession(newSession);
    switchView('quiz');
  }

  // =========================================================================
  // DIAGRAM ZOOM LIGHTBOX MODAL
  // =========================================================================

  function openDiagramModal(src, caption) {
    if (!dom.diagramModal || !dom.diagramModalImg) return;
    dom.diagramModalImg.src = src;
    if (dom.diagramModalCaption) {
      dom.diagramModalCaption.textContent = caption || '經濟學試題圖表';
    }
    dom.diagramModal.classList.add('open');
    dom.diagramModal.setAttribute('aria-hidden', 'false');
  }

  function closeDiagramModal() {
    if (!dom.diagramModal) return;
    dom.diagramModal.classList.remove('open');
    dom.diagramModal.setAttribute('aria-hidden', 'true');
  }

  // Expose global helper for inline HTML diagram clicks
  window.appOpenDiagram = (src) => openDiagramModal(src, '經濟學試題圖表');

  // =========================================================================
  // VIEW SWITCHING STATE MACHINE
  // =========================================================================

  function switchView(viewName) {
    const views = [dom.viewSetup, dom.viewQuiz, dom.viewReview];
    views.forEach(v => {
      if (v) {
        v.classList.remove('active');
        v.classList.add('hidden');
      }
    });

    if (viewName === 'setup') {
      dom.viewSetup?.classList.remove('hidden');
      dom.viewSetup?.classList.add('active');
      dom.btnNavHome?.classList.add('hidden');
    } else if (viewName === 'quiz') {
      dom.viewQuiz?.classList.remove('hidden');
      dom.viewQuiz?.classList.add('active');
      dom.btnNavHome?.classList.remove('hidden');
    } else if (viewName === 'review') {
      dom.viewReview?.classList.remove('hidden');
      dom.viewReview?.classList.add('active');
      dom.btnNavHome?.classList.remove('hidden');
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // =========================================================================
  // KEYBOARD NAVIGATION SHORTCUTS
  // =========================================================================

  function handleKeyboardShortcuts(e) {
    // Ignore keystrokes inside input fields
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // Global ESC to close modals/drawers
    if (e.key === 'Escape') {
      closePaletteDrawer();
      closeGuardrailModal();
      closeDiagramModal();
      return;
    }

    // Only active during quiz view
    if (!dom.viewQuiz?.classList.contains('active')) return;

    const key = e.key.toLowerCase();

    // Option selection keys
    if (key === 'a' || key === '1') {
      selectOption('a');
    } else if (key === 'b' || key === '2') {
      selectOption('b');
    } else if (key === 'c' || key === '3') {
      selectOption('c');
    } else if (key === 'd' || key === '4') {
      selectOption('d');
    } else if (key === 'arrowleft' || key === 'p') {
      prevQuestion();
    } else if (key === 'arrowright' || key === 'n') {
      nextQuestion();
    } else if (key === 'f') {
      toggleFlagCurrentQuestion();
    }
  }

  // =========================================================================
  // EVENT LISTENERS & BINDINGS
  // =========================================================================

  function bindEvents() {
    // Header Navigation
    dom.btnNavHome?.addEventListener('click', () => {
      if (dom.viewQuiz?.classList.contains('active')) {
        if (confirm('測驗正在進行中，返回設定將遺失本次作答進度。確定要返回嗎？')) {
          stopQuizTimer();
          switchView('setup');
        }
      } else {
        switchView('setup');
      }
    });

    // Quick Chapter Selectors
    dom.btnSelectAll?.addEventListener('click', () => applyChapterSelection(() => true));
    dom.btnSelectCh1_3?.addEventListener('click', () => applyChapterSelection(id => ['Ch_01', 'Ch_02', 'Ch_03'].includes(id)));
    dom.btnSelectCh4_6?.addEventListener('click', () => applyChapterSelection(id => ['Ch_04', 'Ch_05', 'Ch_06'].includes(id)));
    dom.btnSelectReset?.addEventListener('click', () => applyChapterSelection(() => false));

    // Question Count Controls
    dom.sliderCount?.addEventListener('input', (e) => setQuestionCount(parseInt(e.target.value, 10)));
    dom.inputCount?.addEventListener('change', (e) => setQuestionCount(parseInt(e.target.value, 10)));

    dom.countChips?.forEach(chip => {
      chip.addEventListener('click', () => {
        const val = chip.dataset.count;
        setQuestionCount(val === 'all' ? 'all' : parseInt(val, 10));
      });
    });

    // Mode Selector
    dom.modeRadios?.forEach(radio => {
      radio.addEventListener('change', (e) => {
        if (e.target.checked) state.selectedMode = e.target.value;
      });
    });

    // Start Quiz
    dom.btnStartQuiz?.addEventListener('click', startQuiz);

    // Quiz Navigation
    dom.btnPrevQ?.addEventListener('click', prevQuestion);
    dom.btnNextQ?.addEventListener('click', nextQuestion);
    dom.btnSubmitQuiz?.addEventListener('click', checkAndSubmitQuiz);
    dom.btnFlagQ?.addEventListener('click', toggleFlagCurrentQuestion);

    // Drawer Controls
    dom.btnTogglePalette?.addEventListener('click', openPaletteDrawer);
    dom.btnClosePalette?.addEventListener('click', closePaletteDrawer);
    dom.paletteBackdrop?.addEventListener('click', closePaletteDrawer);

    // Guardrail Modal Controls
    dom.btnGuardrailCancel?.addEventListener('click', closeGuardrailModal);
    dom.btnGuardrailConfirm?.addEventListener('click', executeQuizSubmission);
    dom.guardrailBackdrop?.addEventListener('click', closeGuardrailModal);

    // Diagram Modal Controls
    dom.btnCloseDiagram?.addEventListener('click', closeDiagramModal);
    dom.diagramBackdrop?.addEventListener('click', closeDiagramModal);

    // Review Filters
    dom.btnFilterAll?.addEventListener('click', () => {
      state.currentReviewFilter = 'all';
      updateFilterButtons();
      renderDiagnosticCards();
    });
    dom.btnFilterWrong?.addEventListener('click', () => {
      state.currentReviewFilter = 'wrong';
      updateFilterButtons();
      renderDiagnosticCards();
    });
    dom.btnFilterFlagged?.addEventListener('click', () => {
      state.currentReviewFilter = 'flagged';
      updateFilterButtons();
      renderDiagnosticCards();
    });

    // Review Action Buttons
    dom.btnPracticeMissed?.addEventListener('click', practiceMissedOnly);
    dom.btnNewQuiz?.addEventListener('click', () => switchView('setup'));

    // Keyboard Shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);
  }

  function updateFilterButtons() {
    dom.btnFilterAll?.classList.toggle('active', state.currentReviewFilter === 'all');
    dom.btnFilterWrong?.classList.toggle('active', state.currentReviewFilter === 'wrong');
    dom.btnFilterFlagged?.classList.toggle('active', state.currentReviewFilter === 'flagged');
  }

  // =========================================================================
  // APP INITIALIZATION
  // =========================================================================

  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    initDualRuntime();
  });

})();
