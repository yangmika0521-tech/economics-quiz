/**
 * Adversarial Dual-Runtime, Parity, and Boundary Stress Testing Harness.
 * Executed via Node.js v24 to stress-test static/js/app.js directly in a headless environment.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const APP_JS_PATH = path.join(PROJECT_ROOT, 'static', 'js', 'app.js');
const QUESTIONS_JSON_PATH = path.join(PROJECT_ROOT, 'data', 'questions.json');

// Read source files
const rawQuestionsData = JSON.parse(fs.readFileSync(QUESTIONS_JSON_PATH, 'utf8'));
let baseJs = fs.readFileSync(APP_JS_PATH, 'utf8');

// Instrument app.js to expose internal state and algorithms for testing
baseJs = baseJs.replace(
  /\}\)\(\);?\s*$/,
  'window.__TEST_EXPORTS__ = { state, dom, clientSampleQuestions, clientEvaluateSubmission, resolveMediaUrl, formatOptionHtml, escapeHtml, renderMarkdownTable, initDualRuntime, activateStaticMode, startQuiz, checkAndSubmitQuiz, executeQuizSubmission }; })();'
);

function createMockEnvironment(windowOverrides = {}, fetchImpl = null) {
  const domCache = {};
  const mockElement = (id = '') => {
    if (!domCache[id]) {
      domCache[id] = {
        id,
        addEventListener: () => {},
        classList: {
          classes: new Set(),
          add(c) { this.classes.add(c); },
          remove(c) { this.classes.delete(c); },
          toggle(c, force) {
            if (force !== undefined) {
              force ? this.add(c) : this.remove(c);
            } else {
              this.classes.has(c) ? this.remove(c) : this.add(c);
            }
          },
          contains(c) { return this.classes.has(c); },
        },
        querySelector: () => mockElement(),
        querySelectorAll: () => [],
        appendChild: () => {},
        innerHTML: '',
        textContent: '',
        style: {},
        dataset: {},
        setAttribute: () => {},
        removeAttribute: () => {},
      };
    }
    return domCache[id];
  };

  const mergedLocation = Object.assign(
    {
      hostname: 'localhost',
      pathname: '/',
      protocol: 'http:',
      href: 'http://localhost/',
    },
    windowOverrides.location || {}
  );
  const win = Object.assign({}, windowOverrides, { location: mergedLocation });

  const sandbox = {
    console: {
      log: () => {},
      warn: () => {},
      error: () => {},
      info: () => {},
    },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    setInterval: setInterval,
    clearInterval: clearInterval,
    window: win,
    document: {
      addEventListener: () => {},
      getElementById: (id) => mockElement(id),
      querySelectorAll: () => [],
      createElement: (tag) => mockElement(tag),
    },
    fetch: fetchImpl,
    AbortController: global.AbortController,
  };
  sandbox.window.document = sandbox.document;

  const script = new vm.Script(baseJs);
  const context = vm.createContext(sandbox);
  script.runInContext(context);

  return { sandbox, exp: sandbox.window.__TEST_EXPORTS__ };
}

// ============================================================================
// TEST 1: Dual-Runtime Fallback Scenarios
// ============================================================================

async function testDualRuntimeFallback() {
  console.log('--- TEST 1: Dual-Runtime Fallback & Network/API Failure Simulation ---');

  // Scenario 1.1: Network Failure (fetch rejects)
  {
    const { exp } = createMockEnvironment({}, async (url) => {
      if (url === '/api/chapters') throw new Error('TypeError: Failed to fetch (Network offline)');
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.initDualRuntime();
    if (exp.state.runtimeMode !== 'static') {
      throw new Error(`[Scenario 1.1 Fail] Expected runtimeMode 'static', got: ${exp.state.runtimeMode}`);
    }
    if (exp.state.rawQuestionsPool.length !== 585) {
      throw new Error(`[Scenario 1.1 Fail] Expected 585 questions loaded, got: ${exp.state.rawQuestionsPool.length}`);
    }
    if (exp.state.allChapters.length !== 6) {
      throw new Error(`[Scenario 1.1 Fail] Expected 6 chapters loaded, got: ${exp.state.allChapters.length}`);
    }
    console.log('  [PASS] Scenario 1.1: Network failure smoothly falls back to Static Mode');
  }

  // Scenario 1.2: Server 500 Internal Server Error
  {
    const { exp } = createMockEnvironment({}, async (url) => {
      if (url === '/api/chapters') return { ok: false, status: 500, json: async () => ({ error: 'Internal Error' }) };
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.initDualRuntime();
    if (exp.state.runtimeMode !== 'static') {
      throw new Error(`[Scenario 1.2 Fail] Expected 'static', got: ${exp.state.runtimeMode}`);
    }
    console.log('  [PASS] Scenario 1.2: HTTP 500 on /api/chapters falls back to Static Mode');
  }

  // Scenario 1.3: Server 404 Not Found
  {
    const { exp } = createMockEnvironment({}, async (url) => {
      if (url === '/api/chapters') return { ok: false, status: 404, json: async () => ({ detail: 'Not Found' }) };
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.initDualRuntime();
    if (exp.state.runtimeMode !== 'static') {
      throw new Error(`[Scenario 1.3 Fail] Expected 'static', got: ${exp.state.runtimeMode}`);
    }
    console.log('  [PASS] Scenario 1.3: HTTP 404 on /api/chapters falls back to Static Mode');
  }

  // Scenario 1.4: Connection Timeout (>1800ms abort)
  {
    const { exp } = createMockEnvironment({}, async (url, opts) => {
      if (url === '/api/chapters') {
        return new Promise((resolve, reject) => {
          opts.signal.addEventListener('abort', () => reject(new Error('AbortError: The operation was aborted')));
        });
      }
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.initDualRuntime();
    if (exp.state.runtimeMode !== 'static') {
      throw new Error(`[Scenario 1.4 Fail] Expected 'static', got: ${exp.state.runtimeMode}`);
    }
    console.log('  [PASS] Scenario 1.4: Request timeout on /api/chapters falls back to Static Mode');
  }

  // Scenario 1.5: GitHub Pages Hostname Detection
  {
    let apiCalled = false;
    const { exp } = createMockEnvironment({ location: { hostname: 'my-org.github.io' } }, async (url) => {
      if (url === '/api/chapters') {
        apiCalled = true;
        return { ok: true, status: 200, json: async () => ({ chapters: [] }) };
      }
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.initDualRuntime();
    if (apiCalled) {
      throw new Error('[Scenario 1.5 Fail] /api/chapters should NOT be called on *.github.io!');
    }
    if (exp.state.runtimeMode !== 'static') {
      throw new Error(`[Scenario 1.5 Fail] Expected 'static', got: ${exp.state.runtimeMode}`);
    }
    console.log('  [PASS] Scenario 1.5: GitHub Pages hostname activates Static Mode without pinging API');
  }

  // Scenario 1.6: File Protocol Detection
  {
    let apiCalled = false;
    const { exp } = createMockEnvironment({ location: { protocol: 'file:' } }, async (url) => {
      if (url === '/api/chapters') {
        apiCalled = true;
        return { ok: true, status: 200, json: async () => ({ chapters: [] }) };
      }
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.initDualRuntime();
    if (apiCalled) {
      throw new Error('[Scenario 1.6 Fail] /api/chapters should NOT be called under file: protocol!');
    }
    if (exp.state.runtimeMode !== 'static') {
      throw new Error(`[Scenario 1.6 Fail] Expected 'static', got: ${exp.state.runtimeMode}`);
    }
    console.log('  [PASS] Scenario 1.6: file: protocol activates Static Mode without pinging API');
  }

  // Scenario 1.7: Relative path resolution for data/questions.json
  {
    let requestedUrl = null;
    const { exp } = createMockEnvironment({ location: { pathname: '/myrepo/static/index.html' } }, async (url) => {
      requestedUrl = url;
      if (url.includes('questions.json')) return { ok: true, status: 200, json: async () => rawQuestionsData };
      throw new Error('Unexpected URL: ' + url);
    });

    await exp.activateStaticMode();
    if (requestedUrl !== '../data/questions.json') {
      throw new Error(`[Scenario 1.7 Fail] Expected '../data/questions.json' when in /static/, got: ${requestedUrl}`);
    }
    console.log('  [PASS] Scenario 1.7: Correctly resolved ../data/questions.json when hosted inside /static/');
  }
}

// ============================================================================
// TEST 2: Client-Side Sampling & Boundary Clamping
// ============================================================================

function testSamplingAndClamping() {
  console.log('--- TEST 2: Client-Side Sampling & Boundary Clamping ---');
  const { exp } = createMockEnvironment();
  const pool = rawQuestionsData.questions;

  // 2.1: Non-positive counts clamp to 1
  for (const nonPos of [0, -1, -50, -9999]) {
    const sampled = exp.clientSampleQuestions(pool, ['Ch_01'], nonPos);
    if (sampled.length !== 1) {
      throw new Error(`[Clamping Fail] Count ${nonPos} should clamp to 1, got length: ${sampled.length}`);
    }
  }
  console.log('  [PASS] 2.1: Non-positive counts (0, -1, -50, -9999) correctly clamp to 1');

  // 2.2: Count exceeding available pool clamps to pool size
  // Ch_01 has 113 questions
  const ch1Questions = pool.filter(q => q.chapter_id === 'Ch_01');
  if (ch1Questions.length !== 113) {
    throw new Error(`Expected 113 questions in Ch_01, got ${ch1Questions.length}`);
  }

  for (const overflow of [113, 114, 500, 10000]) {
    const sampled = exp.clientSampleQuestions(pool, ['Ch_01'], overflow);
    if (sampled.length !== 113) {
      throw new Error(`[Clamping Fail] Overflow count ${overflow} on Ch_01 should clamp to 113, got ${sampled.length}`);
    }
    const idSet = new Set(sampled.map(q => q.id));
    if (idSet.size !== 113) {
      throw new Error(`[Deduplication Fail] Expected 113 unique IDs, got ${idSet.size}`);
    }
  }
  console.log('  [PASS] 2.2: Overflow counts (114, 500, 10000) correctly clamp to exact pool size (113)');

  // 2.3: Zero duplicates across 1,000 randomized sampling iterations
  const allChapterIds = ['Ch_01', 'Ch_02', 'Ch_03', 'Ch_04', 'Ch_05', 'Ch_06'];
  for (let i = 0; i < 1000; i++) {
    // Pick random count between 1 and 60
    const count = Math.floor(Math.random() * 60) + 1;
    // Pick 1 to 3 random chapters
    const numChapters = Math.floor(Math.random() * 3) + 1;
    const shuffledCh = [...allChapterIds].sort(() => Math.random() - 0.5).slice(0, numChapters);

    const sampled = exp.clientSampleQuestions(pool, shuffledCh, count);
    const idSet = new Set(sampled.map(q => q.id));

    if (idSet.size !== sampled.length) {
      throw new Error(`[Duplicate Detected at iter ${i}] Sampled ${sampled.length} has duplicates! Unique: ${idSet.size}`);
    }
    // Verify all sampled belong to requested chapters
    const chSet = new Set(shuffledCh);
    for (const q of sampled) {
      if (!chSet.has(q.chapter_id)) {
        throw new Error(`[Chapter Leak Detected] Question ${q.id} has chapter ${q.chapter_id}, expected one of: ${shuffledCh}`);
      }
    }
  }
  console.log('  [PASS] 2.3: Zero duplicates verified across 1,000 randomized sampling iterations');

  // 2.4: Empty chapter selection or empty pool returns empty array
  if (exp.clientSampleQuestions(pool, [], 10).length !== 0) {
    throw new Error('[Empty Fail] Empty chapter list should return empty array');
  }
  if (exp.clientSampleQuestions([], ['Ch_01'], 10).length !== 0) {
    throw new Error('[Empty Fail] Empty pool should return empty array');
  }
  if (exp.clientSampleQuestions(pool, ['Ch_NonExistent'], 10).length !== 0) {
    throw new Error('[Empty Fail] Non-existent chapter should return empty array');
  }
  console.log('  [PASS] 2.4: Empty chapter list / empty pool / unknown chapter cleanly returns []');
}

// ============================================================================
// TEST 3: Scoring & Evaluation Parity
// ============================================================================

function testScoringParity() {
  console.log('--- TEST 3: Client-Side Scoring & Evaluation Edge Cases ---');
  const { exp } = createMockEnvironment();
  const pool = rawQuestionsData.questions;

  // Sample a fixed set of 20 questions
  const sample20 = exp.clientSampleQuestions(pool, ['Ch_01', 'Ch_02'], 20);

  // 3.1: 100% Perfect Score
  {
    const perfectAnswers = {};
    sample20.forEach(q => { perfectAnswers[q.id] = q.correct_answer; });
    const res = exp.clientEvaluateSubmission(sample20, perfectAnswers);
    if (res.correct_count !== 20 || res.score_percentage !== 100.0) {
      throw new Error(`[Score Fail] Perfect score expected 20/20 (100.0%), got ${res.correct_count} (${res.score_percentage}%)`);
    }
    if (res.results.some(r => !r.is_correct)) {
      throw new Error('[Score Fail] Some questions marked incorrect in 100% submission!');
    }
    console.log('  [PASS] 3.1: 100% perfect score evaluates accurately (20/20 = 100.0%)');
  }

  // 3.2: 0% Zero Score
  {
    const zeroAnswers = {};
    const wrongMap = { a: 'b', b: 'c', c: 'd', d: 'a' };
    sample20.forEach(q => { zeroAnswers[q.id] = wrongMap[q.correct_answer.toLowerCase()] || 'a'; });
    const res = exp.clientEvaluateSubmission(sample20, zeroAnswers);
    if (res.correct_count !== 0 || res.score_percentage !== 0.0) {
      throw new Error(`[Score Fail] Zero score expected 0/20 (0.0%), got ${res.correct_count} (${res.score_percentage}%)`);
    }
    if (res.results.some(r => r.is_correct)) {
      throw new Error('[Score Fail] Some questions marked correct in 0% submission!');
    }
    console.log('  [PASS] 3.2: 0% zero score evaluates accurately (0/20 = 0.0%)');
  }

  // 3.3: Empty Submission
  {
    const res = exp.clientEvaluateSubmission(sample20, {});
    if (res.correct_count !== 0 || res.score_percentage !== 0.0) {
      throw new Error(`[Empty Submission Fail] Expected 0/20, got ${res.correct_count}`);
    }
    if (res.results.length !== 20) {
      throw new Error(`[Empty Submission Fail] Expected 20 result items, got ${res.results.length}`);
    }
    console.log('  [PASS] 3.3: Empty answers dictionary evaluates safely to 0/20 without exceptions');
  }

  // 3.4: Case-Insensitivity & Whitespace Trimming
  {
    const mixedAnswers = {};
    sample20.forEach((q, idx) => {
      if (idx % 2 === 0) {
        // Uppercase with surrounding whitespace
        mixedAnswers[q.id] = `  ${q.correct_answer.toUpperCase()} \t `;
      } else {
        // Wrong answer
        mixedAnswers[q.id] = 'x';
      }
    });
    const res = exp.clientEvaluateSubmission(sample20, mixedAnswers);
    if (res.correct_count !== 10 || res.score_percentage !== 50.0) {
      throw new Error(`[Case/Whitespace Fail] Expected 10/20 (50.0%), got ${res.correct_count} (${res.score_percentage}%)`);
    }
    console.log('  [PASS] 3.4: Case-insensitivity and whitespace trimming verified (10/20 = 50.0%)');
  }

  // 3.5: Chapter Breakdown Arithmetic
  {
    const randomAnswers = {};
    sample20.forEach(q => {
      randomAnswers[q.id] = Math.random() > 0.5 ? q.correct_answer : 'z';
    });
    const res = exp.clientEvaluateSubmission(sample20, randomAnswers);
    let sumCorrect = 0;
    let sumTotal = 0;
    Object.values(res.chapter_breakdown).forEach(stat => {
      sumCorrect += stat.correct;
      sumTotal += stat.total;
    });
    if (sumTotal !== res.total_questions || sumCorrect !== res.correct_count) {
      throw new Error(`[Breakdown Arithmetic Fail] Sum of breakdown (${sumCorrect}/${sumTotal}) != overall (${res.correct_count}/${res.total_questions})`);
    }
    console.log('  [PASS] 3.5: Chapter breakdown arithmetic perfectly matches overall totals');
  }
}

// ============================================================================
// TEST 4: Relative Path Resolution for GitHub Pages Subfolder Hosting
// ============================================================================

function testRelativePathResolution() {
  console.log('--- TEST 4: Relative Path Resolution & Subfolder Hosting ---');
  const { exp } = createMockEnvironment();

  // Test resolveMediaUrl under various formats
  const cases = [
    { in: '/static/media/ch02_fig01.png', exp: './static/media/ch02_fig01.png' },
    { in: './static/media/ch02_fig01.png', exp: './static/media/ch02_fig01.png' },
    { in: 'static/media/ch02_fig01.png', exp: './static/media/ch02_fig01.png' },
    { in: 'https://cdn.example.com/fig.png', exp: 'https://cdn.example.com/fig.png' },
    { in: 'http://cdn.example.com/fig.png', exp: 'http://cdn.example.com/fig.png' },
    { in: '', exp: '' },
    { in: null, exp: '' },
    { in: undefined, exp: '' },
  ];

  for (const c of cases) {
    const out = exp.resolveMediaUrl(c.in);
    if (out !== c.exp) {
      throw new Error(`[Media URL Resolver Fail] Input '${c.in}' -> expected '${c.exp}', got '${out}'`);
    }
  }
  console.log('  [PASS] 4.1: resolveMediaUrl() normalizes root-relative and relative paths to ./static/...');

  // Test formatOptionHtml with embedded <img> tags
  const imgOption = 'Look at the curve <img src="/static/media/ch02_fig02.png" alt="fig">';
  const formatted = exp.formatOptionHtml(imgOption);
  if (!formatted.includes('src="./static/media/ch02_fig02.png"')) {
    throw new Error(`[Option HTML Fail] Absolute src not converted to relative! Got: ${formatted}`);
  }
  console.log('  [PASS] 4.2: formatOptionHtml() adjusts embedded <img src="/static/..."> to ./static/...');

  // Verify that all 72 diagrams referenced in data/questions.json exist on disk
  const mediaDir = path.join(PROJECT_ROOT, 'static', 'media');
  const imgUrls = new Set();
  rawQuestionsData.questions.forEach(q => {
    if (q.image_url) imgUrls.add(q.image_url);
    if (q.options) {
      Object.values(q.options).forEach(opt => {
        if (typeof opt === 'string') {
          const match = opt.match(/src=["']([^"']+)["']/);
          if (match) imgUrls.add(match[1]);
        }
      });
    }
  });

  console.log(`  Checking ${imgUrls.size} unique image references against disk...`);
  for (const rawUrl of imgUrls) {
    const cleanFileName = path.basename(rawUrl);
    const diskPath = path.join(mediaDir, cleanFileName);
    if (!fs.existsSync(diskPath)) {
      throw new Error(`[Missing Diagram File] Referenced diagram does not exist on disk: ${diskPath}`);
    }
  }
  console.log(`  [PASS] 4.3: All ${imgUrls.size} unique referenced diagram images exist on disk in static/media/`);
}

// ============================================================================
// Main Execution
// ============================================================================

async function runAll() {
  console.log('==============================================================================');
  console.log('=== EMPIRICAL CHALLENGER ADVERSARIAL STRESS TEST (NODE.JS) ===');
  console.log('==============================================================================');

  await testDualRuntimeFallback();
  testSamplingAndClamping();
  testScoringParity();
  testRelativePathResolution();

  console.log('==============================================================================');
  console.log('>>> ALL ADVERSARIAL NODE.JS STRESS TESTS PASSED CLEANLY (EXIT 0) <<<');
  console.log('==============================================================================');
}

runAll().catch(err => {
  console.error('\n!!! ADVERSARIAL STRESS TEST FAILED !!!\n', err);
  process.exit(1);
});
