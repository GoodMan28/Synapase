# Project-75A — Agentic AI Research Platform

Multi-agent intelligence powered by **Gemini 1.5 Pro** and **LangGraph**. Submit any research topic and watch 5 specialized agents decompose, research, compile, and audit a comprehensive academic document in real-time.

## Architecture

```
 User Query
     │
     ▼
┌──────────┐
│ Frontier │  → Decomposes topic into 5 sub-tasks + ArXiv search query
│  Agent   │
└──────────┘
     │
     ▼ (parallel fan-out)
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│Intro│ │LitRv│ │Meth.│ │Disc.│ │Conc.│  → Each: ArXiv search → ChromaDB → Gemini generation
└─────┘ └─────┘ └─────┘ └─────┘ └─────┘
     │       │       │       │       │
     └───────┴───────┼───────┴───────┘
                     ▼ (fan-in)
              ┌──────────┐
              │ Compiler │  → Synthesizes 5 sections into cohesive document
              └──────────┘
                     │
                     ▼
              ┌──────────┐
              │ Auditor  │  → Evaluates grounding & cohesion (max 2 revision cycles)
              └──────────┘
                     │
           ┌─────────┼──────────┐
           ▼                    ▼
        APPROVED           REVISION_NEEDED
        → Output              → Back to workers
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Three.js, Vite |
| Backend | FastAPI, Python 3.14 |
| Orchestration | LangGraph, LangChain |
| LLM | Google Gemini 1.5 Pro |
| Vector Store | ChromaDB (persistent) |
| Tools | ArXiv API, ReportLab (PDF) |

## Quick Start

### 1. Clone & Setup Environment

```bash
cd Synapase

# Create .env from template
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

### 2. Install Backend Dependencies

```bash
# Activate venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

### 3. Start the Backend

```bash
cd server
python main.py
# Server runs at http://localhost:8000
```

### 4. Start the Frontend

```bash
cd client
npm install
npm run dev
# Frontend runs at http://localhost:5173
```

### 5. Use

Open `http://localhost:5173`, enter a research topic, and watch the agents work.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/research` | Start research (SSE stream) |
| `GET` | `/api/research/{id}/pdf` | Download PDF |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | ✅ | — | Google AI Studio API key |
| `GEMINI_MODEL` | ❌ | `gemini-1.5-pro` | Gemini model |
| `MAX_REVISIONS` | ❌ | `2` | Max auditor revision cycles |
| `ARXIV_MAX_RESULTS` | ❌ | `5` | Papers per ArXiv search |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level |

## License

Private — All rights reserved.
