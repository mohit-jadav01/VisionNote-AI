/* ══════════ VisionNote AI — Landing Page (Globe Hero + Real API Integration) ══════════
 *
 * API Integration:
 *   File upload: POST /api/upload  (multipart)  → { upload_id }
 *                POST /api/analyze { type:'file', src:upload_id, lang } → { session_id }
 *   YouTube URL: POST /api/analyze { type:'youtube', src:url, lang }    → { session_id }
 *   Both redirect to:  analyze.html?session_id=XXX&lang=YYY
 * ══════════════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── API base URL — change this if your backend runs on a different port ── */
  const API_BASE = 'http://localhost:8000';

  /* ---------- 1. THREE.JS DOT-GLOBE HERO ---------- */
  function initGlobe() {
    const wrap = document.getElementById('globe-canvas-wrap');
    if (!wrap || typeof THREE === 'undefined') return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, wrap.clientWidth / wrap.clientHeight, 0.1, 100);
    camera.position.set(0, 0, 3);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(wrap.clientWidth, wrap.clientHeight);
    wrap.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const point = new THREE.PointLight(0xffffff, 1);
    point.position.set(10, 10, 10);
    scene.add(point);

    const group = new THREE.Group();

    const wireSphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.35, 64, 64),
      new THREE.MeshBasicMaterial({ color: 0xf5f5f7, transparent: true, opacity: 0.12, wireframe: true })
    );
    group.add(wireSphere);

    const dotCount = 900;
    const positions = new Float32Array(dotCount * 3);
    for (let i = 0; i < dotCount; i++) {
      const phi = Math.acos(2 * Math.random() - 1);
      const theta = Math.random() * Math.PI * 2;
      const r = 1.36;
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.cos(phi);
      positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    }
    const dotGeo = new THREE.BufferGeometry();
    dotGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const dots = new THREE.Points(dotGeo, new THREE.PointsMaterial({
      color: 0xe50914, size: 0.018, transparent: true, opacity: 0.85, sizeAttenuation: true
    }));
    group.add(dots);

    const inner = new THREE.Mesh(
      new THREE.SphereGeometry(1.05, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0x7c3aed, transparent: true, opacity: 0.05, wireframe: true })
    );
    group.add(inner);

    scene.add(group);

    const speed = 0.004;
    let raf = null;

    function animate() {
      raf = requestAnimationFrame(animate);
      group.rotation.y += speed;
      group.rotation.x += speed * 0.3;
      group.rotation.z += speed * 0.1;
      inner.rotation.y -= speed * 0.6;
      renderer.render(scene, camera);
    }
    animate();

    window.addEventListener('resize', () => {
      camera.aspect = wrap.clientWidth / wrap.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(wrap.clientWidth, wrap.clientHeight);
    });

    new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { if (raf === null) animate(); }
      else { cancelAnimationFrame(raf); raf = null; }
    }, { threshold: 0 }).observe(wrap);
  }

  /* ---------- 2. FLOATING PARTICLES ---------- */
  function initParticles() {
    const host = document.getElementById('hero-particles');
    if (!host) return;
    const tones = ['', 'cyan', 'violet'];
    for (let i = 0; i < 26; i++) {
      const p = document.createElement('span');
      p.className = 'particle ' + tones[i % 3];
      const s = 2 + Math.random() * 5;
      p.style.cssText = `width:${s}px;height:${s}px;left:${Math.random() * 100}%;bottom:-10px;` +
        `animation-duration:${9 + Math.random() * 14}s;animation-delay:${Math.random() * 12}s;`;
      host.appendChild(p);
    }
  }

  /* ---------- 3. NAVBAR SCROLL STATE ---------- */
  function initNavbar() {
    const nav = document.getElementById('navbar');
    const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- 4. SCROLL REVEAL ---------- */
  function initReveal() {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll('.reveal-scroll').forEach(el => io.observe(el));
  }

  /* ---------- 5. ANIMATED COUNTERS ---------- */
  function initCounters() {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        const el = e.target, target = +el.dataset.count, dur = 1600, t0 = performance.now();
        (function tick(t) {
          const p = Math.min((t - t0) / dur, 1);
          el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
          if (p < 1) requestAnimationFrame(tick);
        })(t0);
        io.unobserve(el);
      });
    }, { threshold: 0.6 });
    document.querySelectorAll('.stat-num').forEach(el => io.observe(el));
  }

  /* ---------- 6. UPLOAD / URL LOGIC ---------- */
  const MAX_SIZE_MB = 500;
  const ALLOWED_EXT = ['mp4', 'mkv', 'mov', 'webm', 'avi', 'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg'];

  function showError(msg) {
    const el = document.getElementById('upload-error');
    el.textContent = msg; el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 7000);
  }

  function isYouTubeUrl(url) {
    return /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/)|youtu\.be\/)[\w-]{6,}/.test(url.trim());
  }

  /* Language-selection gate */
  let pendingParams = null;
  let pendingFile = null;  // holds actual File object for upload

  function goAnalyze(params, file) {
    pendingParams = params;
    pendingFile = file || null;
    openLangModal();
  }

  function openLangModal() {
    const m = document.getElementById('lang-modal');
    m.classList.remove('hidden');
    m.classList.add('open');
  }
  function closeLangModal() {
    const m = document.getElementById('lang-modal');
    m.classList.add('hidden');
    m.classList.remove('open');
  }

  /* ── Real API: start analysis and navigate to analyze.html ── */
  async function startAnalysis(type, src, lang) {
    const urlSubmitBtn = document.getElementById('url-submit-btn');
    const analyzeFileBtn = document.getElementById('analyze-file-btn');
    const errEl = document.getElementById('upload-error');

    // Disable buttons while working
    if (urlSubmitBtn) urlSubmitBtn.disabled = true;
    if (analyzeFileBtn) analyzeFileBtn.disabled = true;
    errEl.classList.add('hidden');

    try {
      let uploadId = src;

      // Step 1: If it's a file, upload it first
      if (type === 'file' && pendingFile) {
        const formData = new FormData();
        formData.append('file', pendingFile);

        const uploadRes = await fetch(`${API_BASE}/api/upload`, {
          method: 'POST',
          body: formData,
        });

        if (!uploadRes.ok) {
          const err = await uploadRes.json().catch(() => ({ detail: 'Upload failed.' }));
          throw new Error(err.detail || `Upload error ${uploadRes.status}`);
        }
        const uploadData = await uploadRes.json();
        uploadId = uploadData.upload_id;
      }

      // Step 2: Start analysis
      const analyzeRes = await fetch(`${API_BASE}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, src: uploadId, lang }),
      });

      if (!analyzeRes.ok) {
        const err = await analyzeRes.json().catch(() => ({ detail: 'Analysis start failed.' }));
        throw new Error(err.detail || `Analyze error ${analyzeRes.status}`);
      }

      const analyzeData = await analyzeRes.json();
      const sessionId = analyzeData.session_id;

      // Navigate to the analysis workspace
      window.location.href = `analyze.html?session_id=${encodeURIComponent(sessionId)}&lang=${encodeURIComponent(lang)}`;

    } catch (err) {
      showError(`⚠ ${err.message}`);
      if (urlSubmitBtn) urlSubmitBtn.disabled = false;
      if (analyzeFileBtn) analyzeFileBtn.disabled = false;
    }
  }

  function initLangModal() {
    document.querySelectorAll('.lang-option').forEach(btn => btn.addEventListener('click', () => {
      if (!pendingParams) return closeLangModal();
      const lang = btn.dataset.lang;
      closeLangModal();
      startAnalysis(pendingParams.type, pendingParams.src, lang);
    }));
    document.getElementById('lang-cancel').addEventListener('click', closeLangModal);
    document.getElementById('lang-backdrop').addEventListener('click', closeLangModal);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLangModal(); });
  }

  function initUpload() {
    const tabUrl = document.getElementById('tab-url');
    const tabFile = document.getElementById('tab-file');
    const panelUrl = document.getElementById('panel-url');
    const panelFile = document.getElementById('panel-file');

    function switchTab(toFile) {
      tabUrl.classList.toggle('tab-active', !toFile);
      tabFile.classList.toggle('tab-active', toFile);
      panelUrl.classList.toggle('hidden', toFile);
      panelFile.classList.toggle('hidden', !toFile);
    }
    tabUrl.addEventListener('click', () => switchTab(false));
    tabFile.addEventListener('click', () => switchTab(true));

    // URL form
    document.getElementById('url-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const url = document.getElementById('youtube-url-input').value;
      if (!isYouTubeUrl(url)) return showError('⚠ Please paste a valid YouTube link (youtube.com or youtu.be).');
      goAnalyze({ type: 'youtube', src: url.trim() }, null);
    });

    // File selection
    const dz = document.getElementById('dropzone');
    const input = document.getElementById('file-input');
    let currentFile = null;

    function handleFile(file) {
      if (!file) return;
      const ext = file.name.split('.').pop().toLowerCase();
      if (!ALLOWED_EXT.includes(ext)) return showError(`⚠ ".${ext}" isn't supported. Use: ${ALLOWED_EXT.join(', ').toUpperCase()}.`);
      if (file.size > MAX_SIZE_MB * 1024 * 1024) return showError(`⚠ File is ${(file.size / 1048576).toFixed(0)} MB — the limit is ${MAX_SIZE_MB} MB.`);
      currentFile = file;
      document.getElementById('file-name').textContent = file.name;
      document.getElementById('file-size').textContent = (file.size / 1048576).toFixed(1) + ' MB · ready to analyze';
      document.getElementById('file-selected').classList.remove('hidden');
    }

    input.addEventListener('change', () => handleFile(input.files[0]));
    ['dragover', 'dragenter'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('dragover'); }));
    dz.addEventListener('drop', e => handleFile(e.dataTransfer.files[0]));

    document.getElementById('analyze-file-btn').addEventListener('click', () => {
      if (!currentFile) return showError('⚠ Choose a file first.');
      goAnalyze({ type: 'file', src: currentFile.name }, currentFile);
    });
  }

  /* ---------- boot ---------- */
  document.addEventListener('DOMContentLoaded', () => {
    initGlobe();
    initParticles();
    initNavbar();
    initReveal();
    initCounters();
    initUpload();
    initLangModal();
  });
})();
