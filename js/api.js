/* ══════════ VidSage AI — Backend API client (drop-in adapter) ══════════
 *
 * Wire the frontend to the FastAPI backend (backend/main.py).
 *
 * Usage in js/analyze.js — replace the local simulations:
 *
 *   1. On page load (processing overlay):
 *        const { session_id } = await VidSageAPI.analyze({ type: srcType, src, lang });
 *        await VidSageAPI.pollStatus(session_id, (step) => {
 *          label.textContent = step.label;
 *          bar.style.width = step.percent + '%';
 *        });
 *        const summary = await VidSageAPI.getSummary(session_id);
 *
 *   2. In sendMessage() — replace askAssistantLocal(q):
 *        const { answer } = await VidSageAPI.chat(q, session_id);
 *
 *   3. Extract hub tabs:
 *        const { content } = await VidSageAPI.extract(session_id, 'action_items');
 *
 * Set API_BASE to '' when the frontend is served by the FastAPI app itself
 * (backend/static/), or to 'http://localhost:8000' during split development.
 * ═══════════════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  const API_BASE = global.VIDSAGE_API_BASE || '';

  async function request(path, options = {}) {
    const res = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* noop */ }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  const VidSageAPI = {
    /** Upload a local media file. Returns { upload_id, filename, size_bytes }. */
    async upload(file) {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(API_BASE + '/api/upload', { method: 'POST', body: form });
      if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed');
      return res.json();
    },

    /** Start the async pipeline. body = { type:'youtube'|'file', src, lang }. */
    analyze(body) {
      return request('/api/analyze', { method: 'POST', body: JSON.stringify(body) });
    },

    /**
     * Poll /api/status until completed/failed.
     * onStep({ label, percent }) fires on every progress change.
     * Resolves when the pipeline completes; rejects on failure.
     */
    pollStatus(sessionId, onStep, intervalMs = 1500) {
      return new Promise((resolve, reject) => {
        (async function tick() {
          try {
            const s = await request(`/api/status/${sessionId}`);
            if (s.step && onStep) onStep(s.step);
            if (s.status === 'completed') return resolve(s);
            if (s.status === 'failed') return reject(new Error(s.error || 'Analysis failed'));
            setTimeout(tick, intervalMs);
          } catch (e) { reject(e); }
        })();
      });
    },

    /** Final result: { title, summary_markdown, language, transcript_chars, source }. */
    getSummary(sessionId) {
      return request(`/api/summary/${sessionId}`);
    },

    /** RAG chat: returns { answer, citations[] }. */
    chat(question, sessionId) {
      return request('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ question, session_id: sessionId }),
      });
    },

    /** kind: 'action_items' | 'decisions' | 'questions' → { content }. */
    extract(sessionId, kind) {
      return request(`/api/extract/${sessionId}/${kind}`);
    },

    /** Raw transcript for the bottom drawer: { transcript, chars }. */
    getTranscript(sessionId) {
      return request(`/api/transcript/${sessionId}`);
    },

    /** Free server resources when the user leaves the workspace. */
    deleteSession(sessionId) {
      return request(`/api/session/${sessionId}`, { method: 'DELETE' });
    },

    /** Backend liveness + configuration warnings. */
    health() {
      return request('/api/health');
    },
  };

  global.VidSageAPI = VidSageAPI;
})(window);
