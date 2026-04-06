"""
Project-75A — Tool Implementations
ArXiv search, ChromaDB vector store, and PDF export utilities.
"""

import logging
import time
import uuid
from io import BytesIO
from typing import Optional

import arxiv
import chromadb
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table,
    TableStyle,
)

from config import get_settings

logger = logging.getLogger("project75a.tools")

# ═══════════════════════════════════════════
# ARXIV SEARCH TOOL
# ═══════════════════════════════════════════


class ArxivSearchTool:
    """
    Searches ArXiv for academic papers with rate limiting and retry logic.
    """

    _last_request_time: float = 0.0

    @classmethod
    def _rate_limit(cls) -> None:
        """Enforce minimum delay between ArXiv API requests."""
        settings = get_settings()
        elapsed = time.time() - cls._last_request_time
        if elapsed < settings.ARXIV_RATE_LIMIT_SECONDS:
            sleep_time = settings.ARXIV_RATE_LIMIT_SECONDS - elapsed
            logger.debug(f"ArXiv rate limit: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        cls._last_request_time = time.time()

    @classmethod
    def search(cls, query: str, max_results: Optional[int] = None) -> list[dict]:
        """
        Search ArXiv and return structured paper metadata.

        Args:
            query: Search query string.
            max_results: Override for max results (defaults to settings).

        Returns:
            List of dicts with keys: id, title, authors, abstract, published, pdf_url
        """
        settings = get_settings()
        if max_results is None:
            max_results = settings.ARXIV_MAX_RESULTS

        cls._rate_limit()

        papers = []
        retries = 3

        for attempt in range(retries):
            try:
                client = arxiv.Client()
                search = arxiv.Search(
                    query=query,
                    max_results=max_results,
                    sort_by=arxiv.SortCriterion.Relevance,
                )

                for result in client.results(search):
                    papers.append(
                        {
                            "id": result.entry_id,
                            "title": result.title,
                            "authors": [a.name for a in result.authors[:5]],
                            "abstract": result.summary,
                            "published": (
                                result.published.strftime("%Y-%m-%d")
                                if result.published
                                else "Unknown"
                            ),
                            "pdf_url": result.pdf_url or "",
                        }
                    )

                logger.info(
                    f"ArXiv search returned {len(papers)} papers for: '{query[:60]}...'"
                )
                return papers

            except Exception as e:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"ArXiv search attempt {attempt + 1}/{retries} failed: {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)

        logger.error(f"ArXiv search failed after {retries} attempts for: '{query}'")
        return []


# ═══════════════════════════════════════════
# CHROMADB MANAGER
# ═══════════════════════════════════════════


class ChromaManager:
    """
    Singleton manager for ChromaDB persistent vector store.
    Each research session gets its own collection.
    """

    _instance: Optional["ChromaManager"] = None
    _client: Optional[chromadb.PersistentClient] = None

    def __new__(cls) -> "ChromaManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            settings = get_settings()
            self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            logger.info(f"ChromaDB initialized at {settings.CHROMA_PERSIST_DIR}")
        return self._client

    def get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """Get or create a named collection."""
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_papers(
        self, papers: list[dict], collection_name: str
    ) -> None:
        """
        Upsert paper abstracts into a ChromaDB collection.
        Uses the paper ID as the document ID to avoid duplicates.
        """
        if not papers:
            return

        collection = self.get_or_create_collection(collection_name)

        ids = []
        documents = []
        metadatas = []

        for paper in papers:
            doc_id = paper["id"].split("/")[-1]  # arXiv ID
            ids.append(doc_id)
            documents.append(
                f"Title: {paper['title']}\n"
                f"Authors: {', '.join(paper['authors'])}\n"
                f"Published: {paper['published']}\n\n"
                f"Abstract: {paper['abstract']}"
            )
            metadatas.append(
                {
                    "title": paper["title"],
                    "authors": ", ".join(paper["authors"]),
                    "published": paper["published"],
                    "pdf_url": paper.get("pdf_url", ""),
                }
            )

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(
            f"Upserted {len(papers)} papers into collection '{collection_name}'"
        )

    def query_relevant(
        self,
        query: str,
        collection_name: str,
        n_results: int = 5,
    ) -> list[dict]:
        """
        Query the collection for relevant paper context.

        Returns:
            List of dicts with 'document' and 'metadata' keys.
        """
        collection = self.get_or_create_collection(collection_name)

        # Guard against querying empty collection
        if collection.count() == 0:
            logger.warning(f"Collection '{collection_name}' is empty, no results.")
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
        )

        output = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = (
                    results["metadatas"][0][i] if results["metadatas"] else {}
                )
                output.append({"document": doc, "metadata": meta})

        logger.debug(
            f"ChromaDB query returned {len(output)} results for '{query[:60]}...'"
        )
        return output

    def delete_collection(self, collection_name: str) -> None:
        """Remove a collection (cleanup after research)."""
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection '{collection_name}'")
        except Exception as e:
            logger.warning(f"Failed to delete collection '{collection_name}': {e}")


# ═══════════════════════════════════════════
# PDF EXPORTER
# ═══════════════════════════════════════════


class PDFExporter:
    """
    Converts a Markdown research document to a styled PDF using ReportLab.
    Handles basic Markdown elements: headings, paragraphs, bold, lists.
    """

    @staticmethod
    def _build_styles() -> dict:
        """Create custom paragraph styles for the PDF."""
        base = getSampleStyleSheet()

        styles = {
            "title": ParagraphStyle(
                "DocTitle",
                parent=base["Title"],
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=28,
                spaceAfter=20,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#1a1a2e"),
            ),
            "h2": ParagraphStyle(
                "Heading2Custom",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=15,
                leading=20,
                spaceBefore=18,
                spaceAfter=8,
                textColor=colors.HexColor("#16213e"),
            ),
            "h3": ParagraphStyle(
                "Heading3Custom",
                parent=base["Heading3"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=16,
                spaceBefore=12,
                spaceAfter=6,
                textColor=colors.HexColor("#0f3460"),
            ),
            "body": ParagraphStyle(
                "BodyCustom",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                spaceAfter=8,
                alignment=TA_JUSTIFY,
                textColor=colors.HexColor("#2c2c2c"),
            ),
            "bullet": ParagraphStyle(
                "BulletCustom",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                leftIndent=20,
                spaceAfter=4,
                textColor=colors.HexColor("#2c2c2c"),
            ),
            "footer": ParagraphStyle(
                "Footer",
                parent=base["Normal"],
                fontName="Helvetica-Oblique",
                fontSize=8,
                leading=10,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#888888"),
            ),
        }
        return styles

    @staticmethod
    def _markdown_line_to_flowable(line: str, styles: dict) -> list:
        """Convert a single Markdown line to ReportLab flowable(s)."""
        stripped = line.strip()

        if not stripped:
            return [Spacer(1, 6)]

        # Bold markers → ReportLab <b> tags
        import re

        stripped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", stripped)
        stripped = re.sub(r"`(.+?)`", r"<font face='Courier' size='9'>\1</font>", stripped)

        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:]
            return [Paragraph(text, styles["title"]), Spacer(1, 4)]
        elif stripped.startswith("## "):
            text = stripped[3:]
            return [
                Spacer(1, 6),
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#e0e0e0"),
                    spaceAfter=4,
                ),
                Paragraph(text, styles["h2"]),
            ]
        elif stripped.startswith("### "):
            text = stripped[4:]
            return [Paragraph(text, styles["h3"])]
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            return [Paragraph(f"• {text}", styles["bullet"])]
        elif re.match(r"^\d+\.\s", stripped):
            return [Paragraph(stripped, styles["bullet"])]
        elif stripped.startswith("> "):
            text = stripped[2:]
            return [
                Paragraph(
                    f"<i>{text}</i>",
                    ParagraphStyle(
                        "Quote",
                        parent=styles["body"],
                        leftIndent=20,
                        textColor=colors.HexColor("#555555"),
                    ),
                )
            ]
        elif stripped.startswith("```"):
            return []  # Skip code fences (content handled as body)
        elif stripped.startswith("---") or stripped.startswith("==="):
            return [
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#cccccc"),
                    spaceBefore=6,
                    spaceAfter=6,
                )
            ]
        else:
            return [Paragraph(stripped, styles["body"])]

    @classmethod
    def export(cls, markdown_content: str, title: str = "Research Report") -> bytes:
        """
        Convert Markdown text to a PDF.

        Args:
            markdown_content: The full Markdown document.
            title: Fallback title for the PDF metadata.

        Returns:
            PDF file content as bytes.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=25 * mm,
            bottomMargin=25 * mm,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            title=title,
            author="Project-75A Multi-Agent Research Engine",
        )

        styles = cls._build_styles()
        story = []

        lines = markdown_content.split("\n")
        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                # Render code lines in monospace
                code_style = ParagraphStyle(
                    "Code",
                    parent=styles["body"],
                    fontName="Courier",
                    fontSize=9,
                    leading=12,
                    leftIndent=15,
                    backColor=colors.HexColor("#f5f5f5"),
                    textColor=colors.HexColor("#333333"),
                )
                # Escape XML chars for ReportLab
                safe_line = (
                    line.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                story.append(Paragraph(safe_line or "&nbsp;", code_style))
                continue

            flowables = cls._markdown_line_to_flowable(line, styles)
            story.extend(flowables)

        # Footer
        story.append(Spacer(1, 30))
        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.HexColor("#cccccc"),
                spaceAfter=8,
            )
        )
        story.append(
            Paragraph(
                "Generated by Project-75A Multi-Agent Research Engine",
                styles["footer"],
            )
        )

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"PDF exported: {len(pdf_bytes)} bytes, title='{title}'")
        return pdf_bytes
