/* ══════════ VisionNote AI — Analysis Workspace (Real Backend Integration)
 *
 * BACKEND ENDPOINTS USED:
 *   GET  /api/status/{session_id}          → poll pipeline progress
 *   GET  /api/summary/{session_id}         → title + markdown summary
 *   GET  /api/transcript/{session_id}      → raw transcript text
 *   GET  /api/extract/{session_id}/{kind}  → action_items | decisions | questions
 *   POST /api/chat { question, session_id }→ { answer, citations[] }
 *   GET  /api/health                       → liveness check
 * ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── API base URL — must match main.js ── */
  const API_BASE = '';

  /* ── URL params ── */
  const params = new URLSearchParams(location.search);
  const sessionId = params.get('session_id') || '';
  const lang = (params.get('lang') || 'english').toLowerCase();
  const isHinglish = lang === 'hinglish';

  /* ── Redirect to home if no session ── */
  if (!sessionId) {
    window.location.href = 'index.html';
  }

  /* ═══════════════════════════════════════
     1. PROCESSING OVERLAY — REAL POLLING
     ═══════════════════════════════════════ */
  const POLL_INTERVAL_MS = 1500;

  function runProcessing() {
    const bar = document.getElementById('processing-bar');
    const label = document.getElementById('processing-step');
    const errEl = document.getElementById('processing-error');

    function poll() {
      fetch(`${API_BASE}/api/status/${sessionId}`)
        .then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
        .then(data => {
          if (data.step) {
            label.textContent = data.step.label || '';
            bar.style.width = (data.step.percent || 0) + '%';
          }

          if (data.status === 'completed') {
            bar.style.width = '100%';
            label.textContent = 'Rolling credits…';
            setTimeout(revealWorkspace, 700);

          } else if (data.status === 'failed') {
            showProcessingError(data.error || 'Analysis failed. Please try again.');

          } else {
            // queued or processing — keep polling
            setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch(err => {
          console.warn('Status poll error:', err);
          // Retry on network error (backend may be starting up)
          setTimeout(poll, POLL_INTERVAL_MS * 2);
        });
    }

    poll();
  }

  function showProcessingError(msg) {
    const errEl = document.getElementById('processing-error');
    errEl.textContent = msg;
    errEl.classList.remove('hidden');
    document.getElementById('processing-step').textContent = 'Analysis failed.';
  }

  /* ══════════════════════════════
     2. REVEAL WORKSPACE + LOAD DATA
     ══════════════════════════════ */
  async function revealWorkspace() {
    const overlay = document.getElementById('processing-overlay');
    overlay.style.transition = 'opacity .6s ease';
    overlay.style.opacity = '0';
    setTimeout(() => overlay.remove(), 650);
    document.getElementById('workspace').style.opacity = '1';
    initReveal();

    // Load all data in parallel
    await Promise.all([
      loadSummary(),
      loadTranscript(),
    ]);

    greet();
  }

  /* ══════════════════════════════
     3. LOAD SUMMARY FROM API
     ══════════════════════════════ */
  async function loadSummary() {
    try {
      const res = await fetch(`${API_BASE}/api/summary/${sessionId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderSummary(data);
    } catch (err) {
      console.error('Summary load failed:', err);
      renderSummaryError();
    }
  }

  function renderSummary(data) {
    // Title
    const titleEl = document.getElementById('video-title');
    if (titleEl) titleEl.textContent = (data.title || 'Analysis Complete').toUpperCase();

    // Language badge
    const langBadge = document.getElementById('meta-lang-badge');
    if (langBadge) langBadge.innerHTML = `<i class="fa-solid fa-language mr-1.5"></i>${isHinglish ? 'Hinglish' : 'English'}`;

    // Render the markdown summary
    const md = data.summary_markdown || '';
    renderMarkdownSummary(md);

    // Source badge in top bar
    const sourceLabel = document.getElementById('source-label');
    const sourceBadge = document.getElementById('source-badge');
    if (data.source && sourceLabel && sourceBadge) {
      if (data.source.type === 'youtube') {
        sourceBadge.querySelector('i').className = 'fa-brands fa-youtube text-primary';
        sourceLabel.textContent = data.source.src;
      } else {
        sourceBadge.querySelector('i').className = 'fa-solid fa-file-video text-primary';
        sourceLabel.textContent = data.source.src;
      }
      sourceBadge.classList.remove('hidden');
    }
  }

  function setMeter(id, val) {
    const span = document.getElementById(`meter-${id}`);
    const bar = document.getElementById(`bar-${id}`);
    if (span) span.textContent = val + '%';
    if (bar) bar.style.setProperty('--w', val + '%');
  }

  /* ── Convert markdown to clean readable HTML for chat bubbles ── */
  function mdToHtml(md) {
    const lines = md.split('\n');
    const out = [];
    let inUl = false, inOl = false;

    const closeLists = () => {
      if (inUl) { out.push('</ul>'); inUl = false; }
      if (inOl) { out.push('</ol>'); inOl = false; }
    };

    const inlineFormat = (s) => s
      .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code class="chat-code">$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="chat-link" target="_blank">$1</a>');

    for (let raw of lines) {
      const line = raw.trimEnd();

      // Horizontal rules  --- or ***
      if (/^[-*]{3,}\s*$/.test(line)) { closeLists(); out.push('<hr class="chat-hr">'); continue; }

      // Headings
      const hm = line.match(/^(#{1,6})\s+(.+)/);
      if (hm) {
        closeLists();
        const lvl = Math.min(hm[1].length, 4);
        const cls = ['chat-h1', 'chat-h2', 'chat-h3', 'chat-h4'][lvl - 1];
        out.push(`<p class="${cls}">${inlineFormat(escapeHtml(hm[2]))}</p>`);
        continue;
      }

      // Unordered list items
      const ulm = line.match(/^\s*[-*•]\s+(.+)/);
      if (ulm) {
        if (!inUl) { closeLists(); out.push('<ul class="chat-ul">'); inUl = true; }
        out.push(`<li>${inlineFormat(escapeHtml(ulm[1]))}</li>`);
        continue;
      }

      // Ordered list items
      const olm = line.match(/^\s*\d+\.\s+(.+)/);
      if (olm) {
        if (!inOl) { closeLists(); out.push('<ol class="chat-ol">'); inOl = true; }
        out.push(`<li>${inlineFormat(escapeHtml(olm[1]))}</li>`);
        continue;
      }

      // Blockquote
      const bqm = line.match(/^>\s*(.*)/);
      if (bqm) {
        closeLists();
        out.push(`<blockquote class="chat-bq">${inlineFormat(escapeHtml(bqm[1]))}</blockquote>`);
        continue;
      }

      // Blank line
      if (!line.trim()) { closeLists(); out.push('<br>'); continue; }

      // Regular paragraph
      closeLists();
      out.push(`<p class="chat-p">${inlineFormat(escapeHtml(line))}</p>`);
    }
    closeLists();
    return out.join('');
  }

  function renderMarkdownSummary(md) {
    // Split summary into sections for display
    const lines = md.split('\n').filter(l => l.trim());
    let tldr = '', full = '';

    // Extract TL;DR line if present
    const tldrIdx = lines.findIndex(l => l.toLowerCase().includes('tl;dr') || l.toLowerCase().includes('summary') || l.toLowerCase().startsWith('#'));
    if (tldrIdx !== -1) {
      // Use first substantial paragraph as TL;DR
      const firstPara = lines.find(l => l.trim().length > 80 && !l.startsWith('#'));
      tldr = firstPara || lines[0] || 'See full summary below.';
    } else {
      tldr = lines[0] || 'Summary generated.';
    }

    // Full summary = all content rendered
    full = md;

    // Render TL;DR
    const tldrEl = document.getElementById('tldr-text');
    if (tldrEl) {
      tldrEl.className = 'text-lg leading-relaxed text-foreground/90 font-medium';
      tldrEl.innerHTML = escapeHtml(stripMarkdown(tldr));
    }

    // Render insights from headings/bullets
    const insightsList = document.getElementById('insights-list');
    if (insightsList) {
      const bullets = lines.filter(l => l.match(/^[-*•]|^\d+\./)).slice(0, 6);
      if (bullets.length > 0) {
        insightsList.className = 'space-y-3';
        insightsList.innerHTML = bullets.map(b =>
          `<li class="insight"><p>${escapeHtml(stripMarkdown(b.replace(/^[-*•\d.]\s*/, '')))}</p></li>`
        ).join('');
      } else {
        // Pull first 3 short sentences as insights
        const sentences = full.replace(/\n/g, ' ').split(/(?<=[.!?])\s+/).filter(s => s.length > 30).slice(0, 4);
        insightsList.className = 'space-y-3';
        insightsList.innerHTML = sentences.map(s =>
          `<li class="insight"><p>${escapeHtml(stripMarkdown(s))}</p></li>`
        ).join('');
      }
    }

    // Render full summary as styled paragraphs
    const fullEl = document.getElementById('full-summary');
    if (fullEl) {
      fullEl.className = 'space-y-4';
      const rendered = lines.map(line => {
        const clean = escapeHtml(line.trim());
        if (line.startsWith('## ')) return `<h3 class="font-bold text-base text-foreground mt-4">${clean.slice(3)}</h3>`;
        if (line.startsWith('# ')) return `<h2 class="font-bold text-lg text-foreground mt-6">${clean.slice(2)}</h2>`;
        if (line.match(/^[-*•]/)) return `<p class="text-sm text-muted-foreground pl-4 border-l-2 border-accent/40">→ ${clean.slice(2)}</p>`;
        if (line.trim().length > 0) return `<p class="text-sm text-muted-foreground leading-relaxed">${clean}</p>`;
        return '';
      }).join('');
      fullEl.innerHTML = rendered || `<p class="text-sm text-muted-foreground">${escapeHtml(md)}</p>`;
    }
  }

  function renderSummaryError() {
    const titleEl = document.getElementById('video-title');
    if (titleEl) titleEl.textContent = 'SUMMARY UNAVAILABLE';
    const tldrEl = document.getElementById('tldr-text');
    if (tldrEl) {
      tldrEl.className = 'text-sm text-rose-400';
      tldrEl.textContent = 'Could not load summary. The backend may be unavailable.';
    }
  }

  function stripMarkdown(text) {
    return text.replace(/[*_`#>]/g, '').trim();
  }

  /* ══════════════════════════════
     4. LOAD TRANSCRIPT FROM API
     ══════════════════════════════ */
  async function loadTranscript() {
    try {
      const res = await fetch(`${API_BASE}/api/transcript/${sessionId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderTranscript(data.transcript || '');
    } catch (err) {
      console.error('Transcript load failed:', err);
    }
  }

  function renderTranscript(text) {
    const el = document.getElementById('rawtext-content');
    if (!el) return;
    if (!text.trim()) {
      el.innerHTML = '<p class="text-muted-foreground italic text-sm p-4">No transcript available.</p>';
      return;
    }
    // Render lines — detect [HH:MM:SS] or [MM:SS] timestamp patterns
    const lines = text.split('\n').filter(l => l.trim());
    el.innerHTML = lines.map(line => {
      const withTs = line.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
        '<span class="raw-ts">[$1]</span>');
      return `<p>${withTs}</p>`;
    }).join('');
  }

  /* ══════════════════════════════
     5. LOAD EXTRACTIONS FROM API
     ══════════════════════════════ */
  const extractCache = {};

  async function loadExtraction(kind) {
    if (extractCache[kind] !== undefined) return extractCache[kind];
    try {
      const res = await fetch(`${API_BASE}/api/extract/${sessionId}/${kind}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      extractCache[kind] = data.content || '';
      return extractCache[kind];
    } catch (err) {
      console.error(`Extract '${kind}' failed:`, err);
      return null;
    }
  }

  function renderExtraction(kind, content) {
    const exMap = { actions: 'action_items', decisions: 'decisions', questions: 'questions' };
    const panelId = kind; // 'actions' | 'decisions' | 'questions'
    const el = document.getElementById(`ex-${panelId}`);
    if (!el) return;

    if (!content) {
      el.innerHTML = '<p class="text-rose-400 text-sm italic">Could not load — backend unavailable.</p>';
      return;
    }

    const iconMap = {
      actions: 'fa-square-check text-emerald-400',
      decisions: 'fa-gavel text-amber-400',
      questions: 'fa-circle-question text-accent-cyan',
    };

    const lines = content.split('\n').filter(l => l.trim());
    el.className = 'ex-pane space-y-3';
    el.innerHTML = lines.map(line => {
      const clean = escapeHtml(line.replace(/^[-*•\d.]\s*/, '').trim());
      if (!clean) return '';
      return `<div class="ex-item">
        <i class="fa-solid ${iconMap[panelId]}"></i>
        <div><p>${clean}</p></div>
      </div>`;
    }).filter(Boolean).join('');

    if (!el.children.length) {
      el.innerHTML = '<p class="text-muted-foreground text-sm italic">No items found.</p>';
    }
  }

  /* ══════════════════════════════
     6. SCROLL REVEAL + METERS
     ══════════════════════════════ */
  function initReveal() {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); } });
    }, { threshold: 0.1, root: document.getElementById('summary-panel') });
    document.querySelectorAll('.reveal-scroll').forEach(el => io.observe(el));
  }

  function animateMeters() {
    setTimeout(() => document.querySelectorAll('.meter').forEach(m => m.classList.add('animated')), 700);
  }

  /* ══════════════════════════════
     7. CHAT — REAL RAG API
     ══════════════════════════════ */
  const messagesEl = document.getElementById('chat-messages');
  const textarea = document.getElementById('chat-textarea');
  const submitBtn = document.getElementById('chat-submit');
  let loading = false;

  function resizeTextarea() {
    textarea.style.height = '0px';
    const cs = getComputedStyle(textarea);
    const lineHeight = parseInt(cs.lineHeight, 10) || 20;
    const padding = parseInt(cs.paddingTop, 10) + parseInt(cs.paddingBottom, 10);
    const minH = lineHeight + padding;
    textarea.style.height = Math.max(textarea.scrollHeight, minH) + 2 + 'px';
  }

  function updateSubmitState() {
    submitBtn.disabled = loading || textarea.value.trim().length === 0;
  }

  textarea.addEventListener('input', () => { resizeTextarea(); updateSubmitState(); });
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (textarea.value.trim().length === 0) return;
      e.preventDefault();
      sendMessage();
    }
  });
  submitBtn.addEventListener('click', (e) => { e.preventDefault(); sendMessage(); });

  document.querySelectorAll('.sugg').forEach(btn => btn.addEventListener('click', () => {
    textarea.value = btn.textContent;
    resizeTextarea(); updateSubmitState();
    sendMessage();
  }));

  function addMessage(role, html) {
    const wrap = document.createElement('div');
    wrap.className = 'msg ' + role;
    wrap.innerHTML =
      `<span class="msg-avatar"><i class="fa-solid ${role === 'bot' ? 'fa-robot' : 'fa-user'}"></i></span>` +
      `<div class="msg-bubble">${html}</div>`;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
  }

  function addTyping() {
    return addMessage('bot', '<span class="typing-dots"><span></span><span></span><span></span></span>');
  }

  async function sendMessage() {
    const q = textarea.value.trim();
    if (!q || loading) return;
    addMessage('user', escapeHtml(q));
    textarea.value = '';
    resizeTextarea();
    loading = true; updateSubmitState();

    const typingEl = addTyping();

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, session_id: sessionId }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Chat failed.' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      // Convert markdown answer to clean HTML — no raw ** or ### in the bubble
      let answerHtml = mdToHtml(data.answer || 'No answer returned.');

      // Append citations if present
      if (data.citations && data.citations.length > 0) {
        answerHtml += '<div class="chat-citations">📍 ' +
          data.citations.map(c => `<span class="chat-cite">${escapeHtml(c)}</span>`).join('') +
          '</div>';
      }

      typeOut(typingEl.querySelector('.msg-bubble'), answerHtml, () => {
        loading = false; updateSubmitState();
      });

    } catch (err) {
      const errMsg = `⚠ ${err.message}`;
      typeOut(typingEl.querySelector('.msg-bubble'),
        `<span class="text-rose-400">${escapeHtml(errMsg)}</span>`, () => {
          loading = false; updateSubmitState();
        });
    }
  }

  // Stream-style typing effect
  function typeOut(el, html, done) {
    el.innerHTML = '';
    const full = html;
    let i = 0;
    const step = Math.max(2, Math.round(full.length / 90));
    (function tick() {
      i = Math.min(i + step, full.length);
      let slice = full.slice(0, i);
      const lastOpen = slice.lastIndexOf('<');
      if (lastOpen > slice.lastIndexOf('>')) { i = full.indexOf('>', lastOpen) + 1; slice = full.slice(0, i); }
      el.innerHTML = slice;
      messagesEl.scrollTop = messagesEl.scrollHeight;
      if (i < full.length) setTimeout(tick, 18);
      else done && done();
    })();
  }

  function greet() {
    setTimeout(() => {
      const t = addTyping();
      setTimeout(() => {
        typeOut(t.querySelector('.msg-bubble'), isHinglish
          ? `👁️ Maine <strong>is video</strong> ka har second dekha aur memory mein index kar liya hai. Kuch bhi poochho — exact timestamps ke saath jawab dunga. Neeche suggestions try karo!`
          : `👁️ I've analyzed every second of <strong>this content</strong> and indexed it into memory. Ask me anything — I'll answer with grounded, accurate responses. Try a suggestion below!`);
      }, 900);
    }, 400);
  }

  /* ══════════════════════════════
     8. SOURCE BADGE
     ══════════════════════════════ */
  function initSourceBadge() {
    // Will be updated by loadSummary when data arrives
    // Show session_id as placeholder for now
    const badge = document.getElementById('source-badge');
    const label = document.getElementById('source-label');
    if (label) label.textContent = `Session: ${sessionId.slice(0, 12)}…`;
    if (badge) badge.classList.remove('hidden');
  }

  /* ══════════════════════════════
     9. RESIZABLE SPLIT
     ══════════════════════════════ */
  function initResizer() {
    const resizer = document.getElementById('split-resizer');
    const summary = document.getElementById('summary-panel');
    const container = document.getElementById('split-container');
    if (!resizer) return;
    let dragging = false;

    function setSplit(clientX) {
      const rect = container.getBoundingClientRect();
      let pct = ((clientX - rect.left) / rect.width) * 100;
      pct = Math.min(80, Math.max(40, pct));
      summary.style.flex = `0 0 ${pct}%`;
    }

    function onMove(e) { if (!dragging) return; setSplit(e.touches ? e.touches[0].clientX : e.clientX); }
    function onUp() { if (!dragging) return; dragging = false; resizer.classList.remove('dragging'); document.body.classList.remove('resizing'); }
    function onDown(e) {
      if (e.target.closest('#extract-hub') || e.target.closest('#rawtext-trigger')) return;
      dragging = true;
      resizer.classList.add('dragging');
      document.body.classList.add('resizing');
      e.preventDefault();
    }

    resizer.addEventListener('mousedown', onDown);
    resizer.addEventListener('touchstart', onDown, { passive: false });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);

    resizer.tabIndex = 0;
    resizer.addEventListener('keydown', (e) => {
      const cur = parseFloat(summary.style.flexBasis || '70');
      if (e.key === 'ArrowLeft') summary.style.flex = `0 0 ${Math.max(40, cur - 2)}%`;
      if (e.key === 'ArrowRight') summary.style.flex = `0 0 ${Math.min(80, cur + 2)}%`;
    });
  }

  /* ══════════════════════════════
     10. EXTRACT HUB — REAL API
     ══════════════════════════════ */
  // Maps tab data-ex values to API kind values
  const kindMap = { actions: 'action_items', decisions: 'decisions', questions: 'questions' };
  const loadedKinds = new Set();

  function initExtract() {
    const flyout = document.getElementById('extract-flyout');
    const hub = document.getElementById('extract-hub');
    const fab = document.getElementById('extract-fab-mobile');
    const resizer = document.getElementById('split-resizer');

    function openFlyout() {
      if (window.innerWidth >= 1024 && resizer) {
        const r = resizer.getBoundingClientRect();
        const c = document.getElementById('split-container').getBoundingClientRect();
        flyout.style.right = (c.right - r.left + 10) + 'px';
        flyout.style.left = 'auto';
      } else {
        flyout.style.left = '50%';
        flyout.style.right = 'auto';
        flyout.style.transform = 'translateX(-50%)';
      }
      flyout.classList.remove('hidden');
      // Load the active tab's extraction
      const activeTab = flyout.querySelector('.ex-tab.ex-active');
      if (activeTab) triggerLoad(activeTab.dataset.ex);
    }
    const closeFlyout = () => flyout.classList.add('hidden');

    hub && hub.addEventListener('click', (e) => { e.stopPropagation(); flyout.classList.contains('hidden') ? openFlyout() : closeFlyout(); });
    fab && fab.addEventListener('click', (e) => { e.stopPropagation(); flyout.classList.contains('hidden') ? openFlyout() : closeFlyout(); });
    document.getElementById('extract-close').addEventListener('click', closeFlyout);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFlyout(); });
    document.addEventListener('click', e => {
      if (!flyout.classList.contains('hidden') && !flyout.contains(e.target)) closeFlyout();
    });

    // Tab switching + lazy loading
    document.querySelectorAll('.ex-tab').forEach(tab => tab.addEventListener('click', () => {
      document.querySelectorAll('.ex-tab').forEach(t => t.classList.remove('ex-active'));
      tab.classList.add('ex-active');
      document.querySelectorAll('.ex-pane').forEach(p => p.classList.add('hidden'));
      const panelId = tab.dataset.ex;
      document.getElementById('ex-' + panelId).classList.remove('hidden');
      triggerLoad(panelId);
    }));
  }

  async function triggerLoad(panelId) {
    if (loadedKinds.has(panelId)) return;
    loadedKinds.add(panelId);

    const el = document.getElementById(`ex-${panelId}`);
    if (el) el.innerHTML = '<p class="text-muted-foreground text-sm italic">Loading…</p>';

    const apiKind = kindMap[panelId];
    const content = await loadExtraction(apiKind);
    renderExtraction(panelId, content);
  }

  /* ══════════════════════════════
     11. RAW TEXT BOTTOM DRAWER
     ══════════════════════════════ */
  function initRawDrawer() {
    const drawer = document.getElementById('rawtext-drawer');
    const handle = document.getElementById('rawtext-handle');
    const trigger = document.getElementById('rawtext-trigger');

    function toggle(force) {
      const open = force !== undefined ? force : !drawer.classList.contains('open');
      drawer.classList.toggle('open', open);
      handle.setAttribute('aria-expanded', open);
    }
    handle.addEventListener('click', () => toggle());
    trigger && trigger.addEventListener('click', (e) => { e.stopPropagation(); toggle(true); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') toggle(false); });

    document.getElementById('copy-raw-btn').addEventListener('click', function () {
      navigator.clipboard.writeText(document.getElementById('rawtext-content').innerText).then(() => {
        this.innerHTML = '<i class="fa-solid fa-check mr-1.5"></i>Copied!';
        setTimeout(() => this.innerHTML = '<i class="fa-solid fa-copy mr-1.5"></i>Copy', 2000);
      });
    });
  }

  /* ══════════════════════════════
     12. COPY SUMMARY + EXPORT PDF
     ══════════════════════════════ */
  function initButtons() {
    // ─ Copy Summary ─
    const copyBtn = document.getElementById('copy-summary-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        const title = document.getElementById('video-title')?.innerText || 'Summary';
        const tldr = document.getElementById('tldr-text')?.innerText || '';
        const insights = document.getElementById('insights-list')?.innerText || '';
        const full = document.getElementById('full-summary')?.innerText || '';
        const text = `${title}\n\n${tldr}\n\n--- Key Insights ---\n${insights}\n\n--- Full Summary ---\n${full}`;
        navigator.clipboard.writeText(text).then(() => {
          this.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
          setTimeout(() => this.innerHTML = '<i class="fa-solid fa-copy"></i> Copy Summary', 2000);
        }).catch(() => {
          this.innerHTML = '<i class="fa-solid fa-xmark"></i> Failed';
          setTimeout(() => this.innerHTML = '<i class="fa-solid fa-copy"></i> Copy Summary', 2000);
        });
      });
    }

    // ─ Export PDF ─
    const pdfBtn = document.getElementById('export-pdf-btn');
    if (pdfBtn) {
      pdfBtn.addEventListener('click', async function () {
        // jsPDF loads as window.jspdf.jsPDF from CDN
        const jsPDFClass = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
        if (!jsPDFClass) {
          alert('PDF library not loaded. Please check your internet connection.');
          return;
        }

        this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating…';
        this.disabled = true;

        try {
          const doc = new jsPDFClass({ unit: 'mm', format: 'a4', orientation: 'portrait' });
          const pageW = doc.internal.pageSize.getWidth();
          const pageH = doc.internal.pageSize.getHeight();
          const margin = 18;
          const maxW = pageW - margin * 2;
          let y = margin;

          const addText = (text, size, bold, color) => {
            doc.setFontSize(size || 11);
            doc.setFont('helvetica', bold ? 'bold' : 'normal');
            doc.setTextColor(...(color || [220, 220, 220]));
            const lines = doc.splitTextToSize(text, maxW);
            for (const line of lines) {
              if (y + 8 > pageH - margin) { doc.addPage(); y = margin; }
              doc.text(line, margin, y);
              y += size ? size * 0.45 : 5;
            }
          };

          // Dark background page
          doc.setFillColor(5, 5, 8);
          doc.rect(0, 0, pageW, pageH, 'F');

          // Header accent bar
          doc.setFillColor(229, 9, 20);
          doc.rect(0, 0, pageW, 3, 'F');
          y = 12;

          // Brand
          addText('VisionNote AI — Video Summary', 9, false, [124, 58, 237]);
          y += 3;

          // Title
          const title = document.getElementById('video-title')?.innerText || 'Summary';
          addText(title, 20, true, [245, 245, 247]);
          y += 5;

          // Divider
          doc.setDrawColor(39, 39, 47);
          doc.line(margin, y, pageW - margin, y);
          y += 6;

          // One-Breath Version
          addText('The One-Breath Version', 13, true, [229, 9, 20]);
          y += 2;
          const tldr = document.getElementById('tldr-text')?.innerText || '';
          addText(tldr, 11, false, [200, 200, 210]);
          y += 6;

          // Key Insights
          doc.setDrawColor(39, 39, 47);
          doc.line(margin, y, pageW - margin, y);
          y += 6;
          addText('Key Insights', 13, true, [34, 211, 238]);
          y += 2;
          const insights = document.getElementById('insights-list')?.innerText || '';
          addText(insights, 10, false, [180, 180, 195]);
          y += 6;

          // Full Summary
          doc.setDrawColor(39, 39, 47);
          doc.line(margin, y, pageW - margin, y);
          y += 6;
          addText('Full Summary', 13, true, [124, 58, 237]);
          y += 2;
          const full = document.getElementById('full-summary')?.innerText || '';
          addText(full, 10, false, [180, 180, 195]);

          // Footer
          const pages = doc.internal.getNumberOfPages();
          for (let i = 1; i <= pages; i++) {
            doc.setPage(i);
            doc.setFillColor(5, 5, 8);
            doc.rect(0, pageH - 8, pageW, 8, 'F');
            doc.setFontSize(7);
            doc.setTextColor(80, 80, 90);
            doc.text(`VisionNote AI — Page ${i} of ${pages}`, pageW / 2, pageH - 3, { align: 'center' });
          }

          const safeName = (title || 'summary').replace(/[^a-z0-9]/gi, '_').toLowerCase().slice(0, 40);
          doc.save(`visionnote_${safeName}.pdf`);
        } finally {
          this.innerHTML = '<i class="fa-solid fa-file-pdf"></i> Export PDF';
          this.disabled = false;
        }
      });
    }
  }

  /* ── Helpers ── */
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  /* ══════════════════════════════
     BOOT
     ══════════════════════════════ */
  document.addEventListener('DOMContentLoaded', () => {
    initSourceBadge();
    updateSubmitState();
    resizeTextarea();
    initResizer();
    initExtract();
    initRawDrawer();
    initButtons();
    runProcessing();   // ← starts real backend polling
  });
})();
