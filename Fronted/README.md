# 🎬 VidSage AI — Cinematic Video Intelligence

A Netflix / JioHotstar-inspired, fully animated platform where users upload an **audio/video file** or paste a **YouTube URL**, receive an AI-generated **cinematic summary**, and then **chat** with the content via a RAG-grounded assistant.

> Frontend is production-ready. Backend hooks for **LangChain Agents + LLM + RAG** are clearly marked in `js/analyze.js` for drop-in integration.

---

## ✅ Currently Completed Features

### 1. Landing Page (`index.html`) — cinematic streaming-service theme
- **3D Dot-Globe Hero** — vanilla Three.js port of the provided React `globe-hero.tsx` component (wireframe sphere + 900-point red dot lattice + violet inner sphere, same rotation speeds `y += 0.004, x += 0.0012, z += 0.0004`), with pause-when-offscreen performance optimization
- Bold, bright, shining hero typography — animated gradient text (`Understood.`), blurred glow duplicate layer, and growing underline (exactly mirroring the demo component's motion choreography)
- Floating ember particles, pulsing ambient orbs, animated stat counters (98% / 40× / 12+)
- **Showcase strip** with wide Ken Burns cinematic theater background + poster-style hover cards
- **How It Works** — 4-step animated pipeline (Ingest → Transcribe → Understand → Converse) with gradient timeline
- **Feature Reel** — 6 glassmorphic feature cards over a home-cinema background
- **AI Assistant section** — features the user's uploaded chatbot image with floating animation + glow halo
- **Upload / URL bar** with tab switch:
  - YouTube URL input with regex validation (`youtube.com`, `youtu.be`, shorts, embed)
  - Drag-&-drop dropzone with file chips describing exactly what to upload: **Video** MP4/MKV/MOV/WEBM/AVI · **Audio** MP3/WAV/M4A/AAC/FLAC · **Max 500 MB** · **Max 3 hours** — with client-side extension + size validation and friendly error messages
- **Language selection modal** — after submitting a URL or file, the user must choose **English 🇬🇧 or Hinglish 🇮🇳** (with style previews); choice is passed as `&lang=` to the workspace
- Scroll-reveal animations throughout (IntersectionObserver), sticky glass navbar with animated link underlines

### 2. Analysis Workspace (`analyze.html`) — 4 views in one panel
Layout: **~70% Summary | draggable slider | ~30% Chatbot**, plus a glowing **Extract hub** on the slider and a bottom **Raw Text drawer**.
- **Draggable split slider** — grab the divider to resize summary vs chat anywhere between 40–80% (mouse, touch, and keyboard ←/→ supported)
- **Glowing EXTRACT hub** centered on the slider — opens a flyout with 3 tabs:
  1. `extract_action_items` — checklist with timestamps
  2. `extract_key_decisions` — decisions with timestamps
  3. `extract_questions` — open questions raised in the video
- **RAW button** at the slider's bottom + a **slide-up bottom drawer** showing the original raw transcript (timestamped, verbatim, with Copy button)
- **Hinglish mode** — when `lang=hinglish`, the TL;DR, chatbot greeting and answers render in Hinglish (backend hook simply forwards `lang` to the LLM)
- Mobile: slider hidden; floating extract FAB appears instead
- **Cinematic processing overlay** simulating the real pipeline (audio extraction → Whisper → embedding → vector indexing → agent drafting) with progress bar
- **Summary panel (70%)** — premium, bold, professional report format:
  - Report hero card with metadata badges (runtime, language, compression)
  - **TL;DR** one-breath version with highlighted key phrases
  - **Key Insights** with clickable timestamp chips
  - **Chapter-by-Chapter breakdown** (collapsible `<details>` acts, screenplay-style)
  - **Notable Quotes** + **Content Signals** (animated meters: technical depth, actionability, sentiment, novelty)
  - Export actions: Print-to-PDF (print stylesheet hides chat), Copy Summary, Analyze Another
- **Chatbot panel (30%)** — faithful vanilla replica of the provided shadcn `chat-input.tsx`:
  - Auto-resizing textarea (port of `use-textarea-resize` hook: line-height math, max-height, +2px)
  - Enter-to-send / Shift+Enter newline, disabled state on empty input, round arrow-up submit button
  - Typing indicator dots, **streamed typing effect** for answers, suggested-question chips
  - Simulated RAG answers grounded in the demo summary, with timestamp citations

## 🔗 Functional Entry URIs
| Path | Purpose | Parameters |
|---|---|---|
| `index.html` | Landing page | — |
| `index.html#upload-section` | Jump to analyze bar | — |
| `analyze.html` | Summary + chat workspace | `?type=youtube&src=<url>` or `?type=file&src=<name>&size=<MB>` |

## 🗂 Data Models & Storage
- No tables used yet — the app is stateless; source info is passed via URL query params.
- (Optional future) a `analyses` table could persist summary history via the RESTful Table API.

## ⛔ Features Not Yet Implemented
- **Real backend**: actual transcription (Whisper), summarization and RAG chat require your LangChain server — the static site cannot run LLMs. Integration points are marked with `── BACKEND HOOK ──` comments:
  - `js/analyze.js → askAssistantLocal()` — replace with `POST /api/chat`
  - `js/analyze.js → runProcessing()` — replace with real job polling of `POST /api/summarize`
  - `js/main.js → goAnalyze()` — kick off upload/ingestion job here
- Actual file upload transport (static sites can't receive files server-side)
- User accounts / summary history

## 🧭 Recommended Next Steps
1. Deploy a LangChain FastAPI backend (Whisper → chunk → embed → vector store → agent) with CORS enabled
2. Swap the three marked hooks to real `fetch()` calls; stream chat via SSE
3. Persist analyses in the Table API for a "My Library" page
4. Add an embedded YouTube player synced to timestamp chips

## 🛠 Tech Stack
- HTML5 + Tailwind CSS (CDN) + custom CSS animations
- Three.js r160 (3D wireframe dot globe)
- Font Awesome 6 icons · Google Fonts (Inter + Bebas Neue)
- Vanilla JS (IntersectionObserver reveals, counters, drag-&-drop, chat engine)

## 🚀 Deployment
Go to the **Publish tab** to deploy with one click and get the live URL.
