"""Natural-language question answering grounded in PubMed abstracts.

This is a retrieval surface, not a reasoning one. Every answer is composed only
from abstracts fetched for the question at hand, each claim carries the number of
the source it came from, and the sources are returned alongside so a reviewer can
read the paper rather than trust the summary. Nothing here writes to a case
record, and no answer is a regulatory or clinical determination — the workflow in
the rest of the application remains the place where decisions are made.

When no LLM is configured the service still answers, extractively: the same
retrieved articles with their own opening sentences, clearly labelled as
retrieval without synthesis. That keeps the feature usable offline and makes the
degraded mode obvious instead of silent.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Article
from app.services.pubmed.client import PubMedArticleDTO, PubMedClient

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 45.0
MAX_ABSTRACT_CHARS = 1800

NOTICE = (
    "Answers are composed only from the PubMed abstracts listed as sources. "
    "This is a literature-retrieval aid, not a clinical or regulatory "
    "determination, and it is not part of the validated review workflow."
)

ANSWER_SYSTEM = """You answer medical and pharmacovigilance questions for a \
qualified safety reviewer, using only the numbered sources supplied.

Rules:
- Use only the supplied abstracts. Never add facts from your own knowledge.
- Cite the source number in square brackets after each claim, like [2]. Cite \
every claim.
- If the sources do not answer the question, say so plainly and describe what \
they do cover. Do not speculate to fill the gap.
- Report what the literature states. Do not give treatment, dosing or \
prescribing recommendations, and do not address the reader as a patient.
- Note disagreement between sources when it exists rather than averaging it away.
- Prose, not bullet lists, unless the question asks for an enumeration. Aim for \
120-220 words.
- Plain text only. No markdown headings or bold."""

QUERY_SYSTEM = """Translate the reviewer's question into a single PubMed search \
query.

Return only the query, no explanation. Use Boolean operators and quoted phrases. \
Prefer ingredient and MeSH-style vocabulary over brand names. Keep it broad \
enough to return results — two or three concepts joined with AND is usually \
right. Never add date filters."""

_STOPWORDS = {
    "a", "about", "after", "all", "am", "an", "and", "any", "are", "as", "at",
    "be", "been", "between", "but", "by", "can", "could", "did", "do", "does",
    "for", "from", "give", "had", "has", "have", "how", "i", "if", "in", "into",
    "is", "it", "its", "may", "me", "much", "my", "of", "on", "or", "our", "out",
    "should", "so", "some", "tell", "than", "that", "the", "their", "there",
    "these", "they", "this", "those", "to", "up", "us", "use", "used", "using",
    "was", "we", "were", "what", "when", "where", "which", "who", "why", "will",
    "with", "would", "you", "your",
}


@dataclass
class AssistantSource:
    """One cited paper. `article_id` is set when we already monitor it, so the
    reviewer can jump straight to its detection report instead of PubMed."""

    number: int
    pmid: str
    title: str
    journal: str | None
    pub_date: str | None
    url: str
    abstract: str | None
    article_id: int | None = None


@dataclass
class AssistantAnswer:
    question: str
    answer: str
    sources: list[AssistantSource] = field(default_factory=list)
    pubmed_query: str = ""
    total_matches: int = 0
    model_id: str = ""
    synthesised: bool = False
    notice: str = NOTICE
    warning: str | None = None


def _keyword_query(question: str) -> str:
    """Fallback question-to-query translation.

    Keeps words PubMed can match on and drops the interrogative scaffolding, so
    "what are the risks of mupirocin in infants" becomes a query rather than a
    sentence PubMed scores poorly.
    """
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-']*", question.lower())
    kept = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    if not kept:
        # Nothing but stopwords: let PubMed's own relevance engine try.
        return question.strip()
    return " AND ".join(dict.fromkeys(kept))


async def _llm_text(system: str, user: str, *, max_tokens: int) -> tuple[str, str] | None:
    """One chat completion returning plain text, or None if unavailable.

    Deliberately does not retry. A reviewer is waiting on this, and a stale
    answer minutes later is worse than the extractive fallback shown promptly.
    """
    settings = get_settings()
    if settings.llm_mock or not settings.llm_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            model = str(data.get("model") or settings.llm_model)
            return (content, model) if content else None
    except Exception as exc:
        logger.warning("assistant LLM call failed: %s: %s", type(exc).__name__, exc)
        return None


def _clean_query(raw: str) -> str:
    """Strip the wrappers a model sometimes puts around a query."""
    text = raw.strip().strip("`").strip()
    if text.lower().startswith("query:"):
        text = text[6:].strip()
    # A model that ignored the instruction and explained itself: take line one.
    return text.splitlines()[0].strip() if text else text


def _first_sentences(text: str, count: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(p for p in parts[:count] if p).strip()


def _extractive_answer(sources: list[AssistantSource]) -> str:
    """Answer without an LLM: say so, then hand over the evidence."""
    if not sources:
        return (
            "No PubMed records matched this question, so there is nothing to "
            "summarise. Try naming the active ingredient rather than a brand, or "
            "broadening the question."
        )
    lines = [
        "Language-model synthesis is not configured, so this is the retrieved "
        "literature rather than a written answer. The opening lines of each "
        "abstract are shown; read the sources below for the full picture.",
        "",
    ]
    for source in sources:
        opening = _first_sentences(source.abstract or "") or "No abstract available."
        lines.append(f"[{source.number}] {opening}")
    return "\n".join(lines)


def _known_article_ids(db: Session, pmids: list[str]) -> dict[str, int]:
    if not pmids:
        return {}
    rows = db.execute(
        select(Article.pmid, Article.id).where(Article.pmid.in_(pmids))
    ).all()
    return {str(pmid): int(article_id) for pmid, article_id in rows}


def _to_sources(
    db: Session, articles: list[PubMedArticleDTO]
) -> list[AssistantSource]:
    known = _known_article_ids(db, [a.pmid for a in articles])
    sources: list[AssistantSource] = []
    for index, article in enumerate(articles, start=1):
        sources.append(
            AssistantSource(
                number=index,
                pmid=article.pmid,
                title=article.title,
                journal=article.journal,
                pub_date=article.pub_date.isoformat() if article.pub_date else None,
                url=article.pubmed_url,
                abstract=article.abstract,
                article_id=known.get(article.pmid),
            )
        )
    return sources


def _grounding_payload(question: str, sources: list[AssistantSource]) -> str:
    blocks = [f"QUESTION: {question}", "", "SOURCES:"]
    for source in sources:
        abstract = (source.abstract or "No abstract available.")[:MAX_ABSTRACT_CHARS]
        blocks.append(
            f"[{source.number}] {source.title}\n"
            f"    Journal: {source.journal or 'not stated'}"
            f" | PMID {source.pmid}\n"
            f"    Abstract: {abstract}"
        )
    return "\n".join(blocks)


async def ask(db: Session, question: str, *, limit: int = 6) -> AssistantAnswer:
    """Answer `question` from PubMed, with citations."""
    question = question.strip()
    if not question:
        raise ValueError("A question is required")

    heuristic = _keyword_query(question)
    translated = await _llm_text(
        QUERY_SYSTEM, question, max_tokens=200
    )
    pubmed_query = heuristic
    if translated:
        candidate = _clean_query(translated[0])
        if candidate:
            pubmed_query = candidate

    warning: str | None = None
    articles: list[PubMedArticleDTO] = []
    total = 0
    try:
        async with PubMedClient() as client:
            # Relevance rather than recency: the best answer to a question is
            # rarely just the newest paper about it.
            result = await client.esearch(
                pubmed_query, retmax=limit, sort="relevance"
            )
            total = result.count
            if not result.pmids and pubmed_query != heuristic:
                # The model's query was too narrow — fall back to keywords
                # rather than reporting no evidence.
                result = await client.esearch(
                    heuristic, retmax=limit, sort="relevance"
                )
                if result.pmids:
                    pubmed_query = heuristic
                    total = result.count
            if result.pmids:
                articles = await client.efetch(result.pmids[:limit])
    except Exception as exc:
        logger.warning("assistant PubMed search failed: %s", exc)
        warning = getattr(exc, "user_message", None) or (
            "PubMed could not be reached, so this answer has no sources behind it."
        )

    sources = _to_sources(db, articles)

    synthesised = False
    model_id = ""
    answer = ""
    if sources:
        t0 = time.perf_counter()
        result_text = await _llm_text(
            ANSWER_SYSTEM,
            _grounding_payload(question, sources),
            max_tokens=900,
        )
        if result_text:
            answer, model_id = result_text
            synthesised = True
            logger.info(
                "assistant answered in %sms with %s sources",
                round((time.perf_counter() - t0) * 1000),
                len(sources),
            )
    if not answer:
        answer = _extractive_answer(sources)
        if sources and not synthesised:
            warning = warning or (
                "Language-model synthesis was unavailable, so the retrieved "
                "abstracts are shown instead of a written answer."
            )

    return AssistantAnswer(
        question=question,
        answer=answer,
        sources=sources,
        pubmed_query=pubmed_query,
        total_matches=total,
        model_id=model_id,
        synthesised=synthesised,
        warning=warning,
    )
