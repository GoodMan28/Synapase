"""
Project-75A — LangGraph StateGraph Definition
Defines the multi-agent research pipeline:
  Frontier → 5 Parallel Workers → Compiler → Auditor (loop) → END
"""

import json
import logging
import operator
import random
import uuid
from typing import Annotated, Any, Literal


def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer: merge two dicts, with b's values taking priority on conflict."""
    return {**a, **b}

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from config import get_settings
from utils.prompts import (
    AUDITOR_SYSTEM_PROMPT,
    AUDITOR_USER_PROMPT,
    COMPILER_SYSTEM_PROMPT,
    COMPILER_USER_PROMPT,
    FRONTIER_SYSTEM_PROMPT,
    FRONTIER_USER_PROMPT,
    WORKER_REVISION_PROMPT,
    WORKER_SYSTEM_PROMPT,
    WORKER_USER_PROMPT,
)
from utils.tools import ArxivSearchTool, ChromaManager

logger = logging.getLogger("project75a.graph")

# ═══════════════════════════════════════════
# STATE DEFINITION
# ═══════════════════════════════════════════

SECTION_IDS = [
    "introduction",
    "literature_review",
    "methodology",
    "discussion",
    "conclusion",
]

SECTION_DISPLAY_NAMES = {
    "introduction": "Introduction",
    "literature_review": "Literature Review",
    "methodology": "Methodology",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}


class ResearchState(TypedDict):
    """Full state for the research pipeline graph."""

    # ── Input ──
    topic: str  # User's original research topic
    research_id: str  # Unique ID for this research session

    # ── Frontier outputs ──
    search_query: str  # Optimized ArXiv search query
    sub_tasks: dict[str, str]  # section_id → sub-task instruction

    # ── Worker outputs ──
    # Annotated so parallel workers can each write their own section key
    sections: Annotated[dict[str, str], _merge_dicts]  # section_id → markdown

    # ── Compiler output ──
    compiled_document: str  # Full compiled markdown document

    # ── Auditor outputs ──
    auditor_feedback: str  # Auditor's overall assessment
    auditor_verdict: str  # "APPROVED" | "REVISION_NEEDED"
    revision_targets: list[str]  # Section IDs needing revision
    revision_count: int  # Number of revision cycles completed

    # ── Metadata ──
    # Annotated so parallel workers can each append their paper sources
    sources: Annotated[list[dict], operator.add]  # Collected ArXiv paper metadata
    events: Annotated[list[dict], operator.add]  # SSE events (append-only)


# ═══════════════════════════════════════════
# LLM FACTORY
# ═══════════════════════════════════════════


def _get_llm() -> ChatGoogleGenerativeAI:
    """Create a Gemini LLM instance using a randomly selected API key."""
    settings = get_settings()
    keys = settings.api_keys
    chosen_key = random.choice(keys)
    logger.debug(f"[LLM] Using API key index {keys.index(chosen_key) + 1}/{len(keys)}")
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=chosen_key,
        temperature=settings.GEMINI_TEMPERATURE,
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
    )


def _emit_event(event_type: str, **data) -> dict:
    """Create an SSE event dict."""
    return {"type": event_type, **data}


def _extract_text(content) -> str:
    """
    Safely extract a plain string from an LLM response content.
    Newer langchain-google-genai versions return content as a list of
    dicts (e.g. [{'type': 'text', 'text': '...'}]) instead of a bare str.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "".join(parts).strip()
    return str(content).strip()


# ═══════════════════════════════════════════
# NODE: FRONTIER AGENT
# ═══════════════════════════════════════════


def frontier_node(state: ResearchState) -> dict:
    """
    Takes the user's topic and:
    1. Generates an optimized ArXiv search query.
    2. Decomposes into 5 specialized sub-tasks.
    """
    topic = state["topic"]
    logger.info(f"[Frontier] Processing topic: {topic}")

    events = [
        _emit_event(
            "AGENT_ACTIVE",
            node="frontier",
            message=f"Decomposing research topic: {topic[:80]}...",
        )
    ]

    llm = _get_llm()
    messages = [
        SystemMessage(content=FRONTIER_SYSTEM_PROMPT),
        HumanMessage(content=FRONTIER_USER_PROMPT.format(topic=topic)),
    ]

    response = llm.invoke(messages)
    response_text = _extract_text(response.content)

    # Parse JSON — strip potential markdown fences
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"[Frontier] Failed to parse JSON response: {e}")
        logger.error(f"[Frontier] Raw response: {response_text[:500]}")
        # Fallback: generate simple sub-tasks
        parsed = {
            "search_query": topic,
            "sub_tasks": {
                sid: f"Write the {SECTION_DISPLAY_NAMES[sid]} section about {topic}."
                for sid in SECTION_IDS
            },
        }

    search_query = parsed.get("search_query", topic)
    sub_tasks = parsed.get("sub_tasks", {})

    # Ensure all 5 sections have tasks
    for sid in SECTION_IDS:
        if sid not in sub_tasks:
            sub_tasks[sid] = (
                f"Write the {SECTION_DISPLAY_NAMES[sid]} section about {topic}."
            )

    logger.info(f"[Frontier] Search query: {search_query}")
    logger.info(f"[Frontier] Sub-tasks generated for: {list(sub_tasks.keys())}")

    events.append(
        _emit_event(
            "AGENT_ACTIVE",
            node="frontier",
            message="Query decomposed into 5 research sub-tasks.",
        )
    )

    return {
        "search_query": search_query,
        "sub_tasks": sub_tasks,
        "events": events,
    }


# ═══════════════════════════════════════════
# NODE: WORKER (parameterized)
# ═══════════════════════════════════════════


def _make_worker_node(section_id: str):
    """Factory that creates a worker node function for a specific section."""

    def worker_node(state: ResearchState) -> dict:
        display_name = SECTION_DISPLAY_NAMES[section_id]
        research_id = state["research_id"]
        sub_task = state["sub_tasks"].get(section_id, f"Write about {state['topic']}")
        search_query = state.get("search_query", state["topic"])
        revision_count = state.get("revision_count", 0)
        existing_sections = state.get("sections", {})
        revision_targets = state.get("revision_targets", [])

        # ── Skip if not targeted during revision cycles ──
        if revision_count > 0 and revision_targets and section_id not in revision_targets:
            logger.info(
                f"[Worker:{display_name}] Skipping — not in revision targets "
                f"(targets: {revision_targets})"
            )
            # Return empty dict — _merge_dicts will leave the existing section intact
            return {
                "sections": {},
                "sources": [],
                "events": [
                    _emit_event(
                        "AGENT_ACTIVE",
                        node="parallel",
                        message=f"Worker: {display_name} — skipped (not targeted for revision).",
                    )
                ],
            }

        logger.info(
            f"[Worker:{display_name}] Starting "
            f"(revision={revision_count})"
        )

        events = [
            _emit_event(
                "AGENT_ACTIVE",
                node="parallel",
                message=f"Worker: {display_name} — searching ArXiv...",
            )
        ]

        # 1. Search ArXiv
        papers = ArxivSearchTool.search(
            query=f"{search_query} {display_name.lower()}"
        )

        # 2. Upsert into ChromaDB
        chroma = ChromaManager()
        collection_name = f"research_{research_id}"
        chroma.upsert_papers(papers, collection_name)

        # 3. Query for relevant context
        results = chroma.query_relevant(
            query=sub_task,
            collection_name=collection_name,
            n_results=5,
        )
        context = "\n\n---\n\n".join(
            [r["document"] for r in results]
        ) if results else "No relevant papers found. Use general knowledge."

        # 4. Generate section via LLM
        llm = _get_llm()

        previous_draft = existing_sections.get(section_id, "")
        auditor_feedback = state.get("auditor_feedback", "")

        if revision_count > 0 and previous_draft and auditor_feedback:
            # Revision mode
            user_prompt = WORKER_REVISION_PROMPT.format(
                sub_task=sub_task,
                context=context,
                previous_draft=previous_draft,
                feedback=auditor_feedback,
                section_name=display_name,
            )
            logger.info(f"[Worker:{display_name}] Revising based on auditor feedback")
        else:
            # Initial generation
            user_prompt = WORKER_USER_PROMPT.format(
                sub_task=sub_task,
                context=context,
                section_name=display_name,
            )

        messages = [
            SystemMessage(
                content=WORKER_SYSTEM_PROMPT.format(section_name=display_name)
            ),
            HumanMessage(content=user_prompt),
        ]

        response = llm.invoke(messages)
        section_text = _extract_text(response.content)

        # Collect sources from papers
        new_sources = [
            {
                "title": p["title"],
                "authors": p["authors"],
                "published": p["published"],
                "id": p["id"],
            }
            for p in papers
        ]

        events.append(
            _emit_event(
                "SECTION_COMPLETE",
                section=section_id,
                preview=section_text[:120] + "...",
            )
        )

        logger.info(
            f"[Worker:{display_name}] Generated {len(section_text)} chars"
        )

        # Return only THIS worker's section — the _merge_dicts reducer
        # will combine all parallel workers' results into the full sections dict.
        return {
            "sections": {section_id: section_text},
            "sources": new_sources,
            "events": events,
        }

    worker_node.__name__ = f"worker_{section_id}"
    return worker_node


# Create all 5 worker nodes
worker_introduction = _make_worker_node("introduction")
worker_literature_review = _make_worker_node("literature_review")
worker_methodology = _make_worker_node("methodology")
worker_discussion = _make_worker_node("discussion")
worker_conclusion = _make_worker_node("conclusion")

WORKER_NODE_MAP = {
    "introduction": "worker_introduction",
    "literature_review": "worker_literature_review",
    "methodology": "worker_methodology",
    "discussion": "worker_discussion",
    "conclusion": "worker_conclusion",
}


# ═══════════════════════════════════════════
# NODE: COMPILER
# ═══════════════════════════════════════════


def compiler_node(state: ResearchState) -> dict:
    """Aggregates the 5 worker sections into a cohesive Markdown document."""
    topic = state["topic"]
    sections = state.get("sections", {})

    logger.info("[Compiler] Aggregating sections...")

    events = [
        _emit_event(
            "AGENT_ACTIVE",
            node="compiler",
            message="Synthesizing 5 sections into cohesive document...",
        )
    ]

    # Format sources
    sources = state.get("sources", [])
    sources_text = "\n".join(
        [
            f"- {s['title']} ({', '.join(s['authors'][:3])}, {s['published']})"
            for s in sources
        ]
    ) if sources else "No sources collected."

    # Build compiler prompt
    llm = _get_llm()
    messages = [
        SystemMessage(content=COMPILER_SYSTEM_PROMPT),
        HumanMessage(
            content=COMPILER_USER_PROMPT.format(
                topic=topic,
                introduction=sections.get("introduction", "[Section missing]"),
                literature_review=sections.get("literature_review", "[Section missing]"),
                methodology=sections.get("methodology", "[Section missing]"),
                discussion=sections.get("discussion", "[Section missing]"),
                conclusion=sections.get("conclusion", "[Section missing]"),
                sources=sources_text,
            )
        ),
    ]

    response = llm.invoke(messages)
    compiled = _extract_text(response.content)

    events.append(
        _emit_event(
            "AGENT_ACTIVE",
            node="compiler",
            message=f"Document compiled — {len(compiled)} characters.",
        )
    )

    logger.info(f"[Compiler] Compiled document: {len(compiled)} chars")

    return {
        "compiled_document": compiled,
        "events": events,
    }


# ═══════════════════════════════════════════
# NODE: AUDITOR
# ═══════════════════════════════════════════


def auditor_node(state: ResearchState) -> dict:
    """
    Evaluates the compiled document for grounding and cohesion.
    Returns a verdict: APPROVED or REVISION_NEEDED.
    """
    document = state.get("compiled_document", "")
    revision_count = state.get("revision_count", 0)
    settings = get_settings()

    logger.info(
        f"[Auditor] Evaluating document (revision cycle {revision_count})..."
    )

    events = [
        _emit_event(
            "AGENT_ACTIVE",
            node="auditor",
            message=f"Evaluating grounding and cohesion (cycle {revision_count + 1})...",
        )
    ]

    llm = _get_llm()
    messages = [
        SystemMessage(content=AUDITOR_SYSTEM_PROMPT),
        HumanMessage(content=AUDITOR_USER_PROMPT.format(document=document)),
    ]

    response = llm.invoke(messages)
    response_text = _extract_text(response.content)

    # Parse JSON response
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    try:
        audit_result = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"[Auditor] Failed to parse audit JSON: {e}")
        logger.error(f"[Auditor] Raw: {response_text[:500]}")
        # Default to approval on parse failure
        audit_result = {
            "verdict": "APPROVED",
            "grounding_score": 7,
            "cohesion_score": 7,
            "overall_assessment": "Evaluation parsing failed — approving by default.",
            "section_feedback": {},
            "revision_targets": [],
        }

    verdict = audit_result.get("verdict", "APPROVED")
    revision_targets = audit_result.get("revision_targets", [])
    feedback = audit_result.get("overall_assessment", "")
    grounding = audit_result.get("grounding_score", 0)
    cohesion = audit_result.get("cohesion_score", 0)

    # Force approval if max revisions reached
    if verdict == "REVISION_NEEDED" and revision_count >= settings.MAX_REVISIONS:
        logger.warning(
            f"[Auditor] Max revisions ({settings.MAX_REVISIONS}) reached. "
            f"Forcing approval."
        )
        verdict = "APPROVED"
        feedback += (
            f" [Note: Forced approval after {settings.MAX_REVISIONS} revision cycles.]"
        )
        revision_targets = []

    if verdict == "REVISION_NEEDED":
        events.append(
            _emit_event(
                "AUDITOR_REVISION",
                targets=revision_targets,
                feedback=feedback,
                grounding_score=grounding,
                cohesion_score=cohesion,
            )
        )
    else:
        events.append(
            _emit_event(
                "AGENT_ACTIVE",
                node="auditor",
                message=f"Auditor approved — Grounding: {grounding}/10, Cohesion: {cohesion}/10",
            )
        )

    logger.info(
        f"[Auditor] Verdict: {verdict} | "
        f"Grounding: {grounding}/10, Cohesion: {cohesion}/10 | "
        f"Revision targets: {revision_targets}"
    )

    new_revision_count = (
        revision_count + 1 if verdict == "REVISION_NEEDED" else revision_count
    )

    return {
        "auditor_feedback": feedback,
        "auditor_verdict": verdict,
        "revision_targets": revision_targets,
        "revision_count": new_revision_count,
        "events": events,
    }


# ═══════════════════════════════════════════
# CONDITIONAL EDGE: ROUTE AFTER AUDITOR
# ═══════════════════════════════════════════


def route_after_auditor(
    state: ResearchState,
) -> str:
    """Decide the next step after the Auditor evaluates the document."""
    verdict = state.get("auditor_verdict", "APPROVED")

    if verdict == "APPROVED":
        logger.info("[Router] Auditor approved → END")
        return "approved"
    else:
        targets = state.get("revision_targets", [])
        logger.info(f"[Router] Revision needed → re-running workers: {targets}")
        return "revision_needed"


# ═══════════════════════════════════════════
# REVISION FAN-OUT NODE
# ═══════════════════════════════════════════


def revision_fanout_node(state: ResearchState) -> dict:
    """
    Intermediate node that runs before the workers on revision.
    Emits the AUDITOR_REVISION event for the frontend and passes state through.
    """
    targets = state.get("revision_targets", [])
    logger.info(f"[RevisionFanout] Re-running workers for: {targets}")
    return {
        "events": [
            _emit_event(
                "AGENT_ACTIVE",
                node="parallel",
                message=f"Revising sections: {', '.join(targets)}...",
            )
        ],
    }


# ═══════════════════════════════════════════
# GRAPH BUILDER
# ═══════════════════════════════════════════


def build_research_graph() -> StateGraph:
    """
    Build and compile the LangGraph research pipeline.

    Flow:
        frontier → all_workers → compiler → auditor
            ↓ (APPROVED)         ↓ (REVISION_NEEDED)
           END            revision_fanout → all_workers → compiler → auditor ...

    Note: LangGraph does not support conditional fan-out to a dynamic subset
    of parallel nodes easily. Instead, we route to a revision_fanout node
    that triggers all workers, but each worker checks if it's in revision_targets
    and skips itself if not targeted.
    """
    graph = StateGraph(ResearchState)

    # ── Add nodes ──
    graph.add_node("frontier", frontier_node)
    graph.add_node("worker_introduction", worker_introduction)
    graph.add_node("worker_literature_review", worker_literature_review)
    graph.add_node("worker_methodology", worker_methodology)
    graph.add_node("worker_discussion", worker_discussion)
    graph.add_node("worker_conclusion", worker_conclusion)
    graph.add_node("compiler", compiler_node)
    graph.add_node("auditor", auditor_node)
    graph.add_node("revision_fanout", revision_fanout_node)

    # ── Entry point ──
    graph.set_entry_point("frontier")

    # ── Frontier → all 5 workers (parallel fan-out) ──
    graph.add_edge("frontier", "worker_introduction")
    graph.add_edge("frontier", "worker_literature_review")
    graph.add_edge("frontier", "worker_methodology")
    graph.add_edge("frontier", "worker_discussion")
    graph.add_edge("frontier", "worker_conclusion")

    # ── All workers → compiler (fan-in) ──
    graph.add_edge("worker_introduction", "compiler")
    graph.add_edge("worker_literature_review", "compiler")
    graph.add_edge("worker_methodology", "compiler")
    graph.add_edge("worker_discussion", "compiler")
    graph.add_edge("worker_conclusion", "compiler")

    # ── Compiler → Auditor ──
    graph.add_edge("compiler", "auditor")

    # ── Auditor conditional edge ──
    graph.add_conditional_edges(
        "auditor",
        route_after_auditor,
        {
            "approved": END,
            "revision_needed": "revision_fanout",
        },
    )

    # ── Revision fanout → all workers again ──
    graph.add_edge("revision_fanout", "worker_introduction")
    graph.add_edge("revision_fanout", "worker_literature_review")
    graph.add_edge("revision_fanout", "worker_methodology")
    graph.add_edge("revision_fanout", "worker_discussion")
    graph.add_edge("revision_fanout", "worker_conclusion")

    compiled = graph.compile()
    logger.info("[Graph] Research pipeline compiled successfully")

    return compiled
