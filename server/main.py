"""
Project-75A — FastAPI Application
Main entry point with SSE streaming, CORS, health checks, and PDF export.
"""

import json
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from config import get_settings
from graph import build_research_graph
from utils.tools import PDFExporter

# ═══════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════


def setup_logging() -> None:
    """Configure structured JSON-like logging."""
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.LOG_LEVEL)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    root_logger.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


logger = logging.getLogger("project75a.main")

# ═══════════════════════════════════════════
# COMPILED GRAPH (lazy singleton)
# ═══════════════════════════════════════════

_compiled_graph = None


def get_graph():
    """Lazy-init the compiled LangGraph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_research_graph()
    return _compiled_graph


# ═══════════════════════════════════════════
# IN-MEMORY RESEARCH STORE
# ═══════════════════════════════════════════

# Stores completed research documents for PDF download
# Key: research_id, Value: {"topic": str, "document": str}
_research_store: dict[str, dict] = {}


# ═══════════════════════════════════════════
# APP LIFECYCLE
# ═══════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    logger.info("=" * 60)
    logger.info("Project-75A Backend starting...")
    logger.info("=" * 60)

    settings = get_settings()
    logger.info(f"Model: {settings.GEMINI_MODEL}")
    logger.info(f"Max revisions: {settings.MAX_REVISIONS}")
    logger.info(f"ArXiv max results: {settings.ARXIV_MAX_RESULTS}")
    logger.info(f"ChromaDB dir: {settings.CHROMA_PERSIST_DIR}")
    logger.info(f"CORS origins: {settings.CORS_ORIGINS}")

    # Pre-compile the graph
    get_graph()
    logger.info("LangGraph pipeline compiled and ready.")

    yield

    logger.info("Project-75A Backend shutting down.")


# ═══════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════

app = FastAPI(
    title="Project-75A",
    description="Agentic AI Research Platform — Multi-agent intelligence powered by Gemini & LangGraph",
    version="0.75a",
    lifespan=lifespan,
)

# ── CORS ──
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════


class ResearchRequest(BaseModel):
    """Request body for initiating a research session."""

    topic: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The research topic to investigate.",
        examples=["Quantum computing applications in drug discovery"],
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.75a"
    model: str = ""
    graph_ready: bool = False


# ═══════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version="0.75a",
        model=settings.GEMINI_MODEL,
        graph_ready=_compiled_graph is not None,
    )


def _format_sse(event_type: str, data: dict) -> str:
    """Format a server-sent event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _run_research_pipeline(topic: str) -> AsyncGenerator[str, None]:
    """
    Execute the LangGraph research pipeline and yield SSE events.

    This runs the graph synchronously (LangGraph invocation) but streams
    accumulated events from the state after execution, plus intermediary
    events during streaming of chunks.
    """
    research_id = uuid.uuid4().hex[:12]

    logger.info(f"[Pipeline] Starting research '{research_id}' for: {topic}")

    # Emit start event
    yield _format_sse("START_THINKING", {"topic": topic, "research_id": research_id})

    # Initial state
    initial_state = {
        "topic": topic,
        "research_id": research_id,
        "search_query": "",
        "sub_tasks": {},
        "sections": {},
        "compiled_document": "",
        "auditor_feedback": "",
        "auditor_verdict": "",
        "revision_targets": [],
        "revision_count": 0,
        "sources": [],
        "events": [],
    }

    graph = get_graph()

    try:
        # Stream using LangGraph's stream interface for node-by-node updates
        compiled_doc = ""
        all_sources = []

        for chunk in graph.stream(initial_state, stream_mode="updates"):
            # Each chunk is {node_name: state_update_dict}
            for node_name, update in chunk.items():
                logger.info(f"[Pipeline] Node completed: {node_name}")

                # Track compiled document and sources from node updates
                if "compiled_document" in update and update["compiled_document"]:
                    compiled_doc = update["compiled_document"]
                if "sources" in update and update["sources"]:
                    all_sources.extend(update["sources"])

                # Extract and yield any new events from this update
                new_events = update.get("events", [])
                for event in new_events:
                    evt = dict(event)  # Copy to avoid mutating state
                    event_type = evt.pop("type", "AGENT_ACTIVE")
                    yield _format_sse(event_type, evt)

        if not compiled_doc:
            yield _format_sse(
                "ERROR",
                {
                    "message": "Pipeline completed but no document was generated.",
                    "code": "EMPTY_DOCUMENT",
                },
            )
            return

        sources_count = len(all_sources)

        # Store for PDF download
        _research_store[research_id] = {
            "topic": topic,
            "document": compiled_doc,
        }

        # Final document event
        yield _format_sse(
            "FINAL_DOC",
            {
                "document": compiled_doc,
                "research_id": research_id,
                "sources_count": sources_count,
            },
        )

        logger.info(
            f"[Pipeline] Research '{research_id}' complete. "
            f"Document: {len(compiled_doc)} chars, Sources: {sources_count}"
        )

    except Exception as e:
        logger.exception(f"[Pipeline] Error during research '{research_id}': {e}")
        yield _format_sse(
            "ERROR",
            {
                "message": str(e),
                "code": "PIPELINE_ERROR",
            },
        )


@app.post("/api/research")
async def start_research(request: ResearchRequest):
    """
    Start a new research session. Returns a Server-Sent Events stream.

    Event types:
    - START_THINKING: Research initiated
    - AGENT_ACTIVE: An agent node is currently processing
    - SECTION_COMPLETE: A worker finished a section
    - AUDITOR_REVISION: Auditor requested revisions
    - FINAL_DOC: Complete research document
    - ERROR: Pipeline error
    """
    logger.info(f"[API] Research request received: {request.topic[:80]}")

    return StreamingResponse(
        _run_research_pipeline(request.topic),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/research/{research_id}/pdf")
async def download_pdf(research_id: str):
    """Download the completed research as a styled PDF."""
    if research_id not in _research_store:
        raise HTTPException(
            status_code=404,
            detail=f"Research '{research_id}' not found. It may have expired.",
        )

    entry = _research_store[research_id]
    pdf_bytes = PDFExporter.export(
        markdown_content=entry["document"],
        title=entry["topic"],
    )

    filename = f"project75a_research_{research_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ═══════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
