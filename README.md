<div align="center">

<img src="./screenshots/Screenshot 2026-09-13 191116.png" alt="VisionNote AI — Cinematic Video Intelligence" width="100%"/>

# VisionNote AI

### Cinematic Video Intelligence & Meeting RAG Engine

**Upload audio/video or a YouTube link — get a full transcript, executive summary, and chat with your media using Retrieval-Augmented Generation (RAG).**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3.x-1C3C3C)](https://www.langchain.com/)
[![Whisper](https://img.shields.io/badge/Transcription-Whisper%20%7C%20Sarvam-000000)](https://openai.com/research/whisper)
[![Mistral](https://img.shields.io/badge/Inference-Mistral-FA520F)](https://mistral.ai/)
[![FAISS](https://img.shields.io/badge/Vector_DB-FAISS-1C3C3C)](https://github.com/facebookresearch/faiss)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)

</div>

---

## 📖 Table of Contents

1. [Overview](#-overview)
2. [System Architecture](#-system-architecture)
3. [The RAG Pipeline — Deep Dive](#-the-rag-pipeline--deep-dive)
4. [Backend API Reference](#-backend-api-reference)
5. [Project Structure](#-project-structure)
6. [Tech Stack](#-tech-stack)
7. [Getting Started](#-getting-started)
8. [License](#-license)

---

## 🌟 Overview

**VisionNote AI** is an enterprise-grade AI Meeting Intelligence Assistant. Users can upload media files (audio/video) or provide a YouTube URL. The backend orchestrates a complex async pipeline to transcribe the media (via Whisper/Sarvam), index the transcript into a per-session FAISS vector store, and extract key insights (action items, decisions, summaries). Finally, it allows users to chat seamlessly with their video through an evidence-based, hallucination-free RAG engine powered by Mistral and LangChain.

This project is built around a robust, asynchronous **FastAPI backend** that drives the intelligence, while a sleek frontend provides the cinematic UX.

---

## 🏛️ System Architecture

The architecture relies on a highly decoupled async pipeline ensuring seamless user experience even for large video files.

```mermaid
flowchart TB
    subgraph Client["🖥️ Frontend UI"]
        A1["Upload / Link Input"]
        A2["Status Polling Overlay"]
        A3["Chat / Summary Dashboard"]
    end

    subgraph API["⚙️ FastAPI Backend (main.py)"]
        direction TB
        R1["POST /api/upload"]
        R2["POST /api/analyze<br/>(Starts Pipeline)"]
        R3["GET /api/status/{id}"]
        R4["POST /api/chat<br/>(RAG Chat)"]
    end

    subgraph Pipeline["🔄 Async Processing Pipeline"]
        P1["Audio Extraction<br/>& Download"]
        P2["Transcription Engine<br/>(Whisper/Sarvam)"]
        P3["Vector Indexing<br/>(FAISS)"]
        P4["Insight Extraction<br/>(LLM Summaries)"]
    end

    subgraph AI["🤖 Inference & LLMs"]
        MISTRAL["Mistral AI<br/>(Chat / Extract)"]
        EMBED["Embeddings<br/>(Vectorization)"]
    end

    %% Flow
    A1 -- "multipart/form-data" --> R1
    A1 -- "Session Params" --> R2
    R2 -- "Spawns async job" --> Pipeline
    A2 -. "Polls status" .-> R3
    
    Pipeline --> P1 --> P2 --> P3 --> P4
    
    P3 <--> EMBED
    P4 <--> MISTRAL
    
    A3 -- "Query" --> R4
    R4 -- "Retrieve Chunks" --> P3
    R4 -- "Prompt + Context" --> MISTRAL
    MISTRAL -- "Grounded Answer" --> R4
    R4 -- "JSON" --> A3

    style Client fill:#0f172a,color:#fff,stroke:#38bdf8
    style API fill:#111827,color:#fff,stroke:#22d3ee
    style Pipeline fill:#111827,color:#fff,stroke:#f97316
    style AI fill:#111827,color:#fff,stroke:#ef4444
```

---

## 🔍 The RAG Pipeline — Deep Dive

The **chat with your video** feature uses strict, evidence-based prompt engineering to prevent hallucinations. The AI acts as a professional business analyst.

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant F as FastAPI (/api/chat)
    participant VS as FAISS (Per-Session Store)
    participant LLM as Mistral LLM (LangChain)

    U->>F: POST /api/chat { question, session_id }
    F->>F: Load session & validate
    F->>VS: Retrieve relevant transcript chunks
    VS-->>F: Top-K source documents
    alt no chunks found
        F-->>U: "I could not find this information in the meeting transcript."
    end
    F->>F: Format chunks into context
    F->>LLM: SystemPrompt (No Hallucination) + Context + Question
    Note over LLM: Grounding rules enforced:<br/>Extracts Decisions, Action Items,<br/>and refuses ungrounded facts.
    LLM-->>F: Markdown Answer + Citations
    F-->>U: 200 OK { answer, citations }
```

### RAG Highlights
- **Per-Session Retrievers**: FAISS vector stores are isolated per session. No cross-user or cross-meeting data leakage.
- **Citation Extraction**: Source chunks are preserved and returned to the frontend.
- **Evidence-Only System Prompt**: The system is explicitly instructed to output *"I could not find this information"* if the context doesn't support the answer.

---

## 🔌 Backend API Reference

The FastAPI backend exposes the following core routes (interactive docs at `http://localhost:8000/docs`):

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload` | Streams media to disk, returns `upload_id` |
| `POST` | `/api/analyze` | Kicks off the async processing pipeline (returns `202 Accepted`) |
| `GET` | `/api/status/{id}` | Polls pipeline progress for the frontend overlay |
| `GET` | `/api/summary/{id}` | Retrieves the final generated title and markdown summary |
| `POST` | `/api/chat` | The RAG Chat interface (`{ question, session_id }` → `{ answer, citations }`) |
| `GET` | `/api/extract/{id}/{kind}`| Fetches specific insights (e.g., `action_items`, `decisions`) |
| `GET` | `/api/health` | Liveness probe and config validation warnings |

---

## 📂 Project Structure

```text
VisionNote Ai/
├── backend/
│   ├── main.py                  # FastAPI entrypoint, HTTP routes
│   ├── requirements.txt         # Python dependencies
│   ├── app/
│   │   ├── config.py            # Environment configurations
│   │   ├── core/                # Core logic (audio, extractor, rag_engine, vector_store)
│   │   ├── schemas.py           # Pydantic models & validation
│   │   └── services/            # Pipeline orchestrator and session store
│   ├── uploads/                 # Temporary storage for uploaded media
│   └── vector_db/               # FAISS indices stored per session
├── Fronted/
│   ├── index.html               # Cinematic UI
│   └── js/                      # Frontend API integration
└── screenshots/
    └── Screenshot 2026-09-13 191116.png
```

---

## 🚀 Tech Stack

- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Async Python)
- **AI Orchestration:** [LangChain](https://www.langchain.com/)
- **Large Language Model:** [Mistral AI](https://mistral.ai/)
- **Transcription:** OpenAI Whisper / Sarvam
- **Vector Database:** [FAISS](https://github.com/facebookresearch/faiss) (Local, rapid similarity search)
- **Frontend:** Vanilla HTML/JS with high-end cinematic CSS

---

## 🛠️ Getting Started

### Prerequisites
- Python 3.11+
- API Keys for Mistral (and transcription services if required)

### Setup Instructions

1. **Navigate to the backend**
   ```bash
   cd backend
   ```

2. **Create a virtual environment & install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   Copy `.env.example` to `.env` and fill in your API keys.
   ```bash
   cp .env.example .env
   ```

4. **Run the Development Server**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

The backend is now running at **`http://localhost:8000`**. You can explore the API documentation at **`http://localhost:8000/docs`**.

---

## 📄 License

Distributed under the MIT License.
