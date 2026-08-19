"""Natural-language question answering grounded in PubMed abstracts.

This is a retrieval surface, not a reasoning one. Every answer is composed only
from abstracts fetched for the question at hand, and the citations are produced
by the API's own citation mechanism rather than written into prose by the model:
each cited span comes back as structured data naming the source document and
quoting the sentence it came from. In a pharmacovigilance setting that is the
difference between a claim a reviewer can check and one they have to trust.

Nothing here writes to a case record, and no answer is a regulatory or clinical
determination — the workflow in the rest of the application remains the place
where decisions are made.

Two model calls per question, each using the feature that fits it:

1.  Question resolution — a **structured output** call that resolves a follow-up
    against the conversation so far ("and in children?") into a self-contained
    question, and names the concepts it should search on. The query itself is
    assembled here from those concepts rather than written by the model, which
    keeps PubMed's phrase syntax out of a JSON string field.
2.  Answering — a **citations** call over the retrieved abstracts as document
    blocks, with thinking enabled for reasoning across sources that disagree.

Both calls are shaped to the configured model's capabilities: the thinking and
effort parameters are not interchangeable across model families, and sending
the wrong pair is a 400 rather than a degraded answer.

When no API key is configured the service still answers, extractively, and says
so — the degraded mode is visible rather than silent.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Article
from app.services.pubmed.client import PubMedArticleDTO, PubMedClient

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 120.0
MAX_ABSTRACT_CHARS = 6000
#: Turns of prior conversation given to the resolver. Enough to resolve a
#: pronoun or an elliptical follow-up; short enough to stay cheap and to keep an
#: old topic from dragging a new question back toward it.
HISTORY_TURNS = 4
#: Shape of the assembled PubMed query. Two or three concepts is the useful
#: range: one is too broad to narrow anything, four or more rarely matches.
MAX_CONCEPT_GROUPS = 4
MAX_TERMS_PER_GROUP = 8

NOTICE = (
    "Answers are composed only from the PubMed abstracts listed as sources, and "
    "each citation is linked to the sentence it came from. This is a "
    "literature-retrieval aid, not a clinical or regulatory determination, and "
    "it is not part of the validated review workflow."
)

ANSWER_SYSTEM = """You answer medical and pharmacovigilance questions for a \
qualified safety reviewer, using only the documents supplied.

- Use only the supplied abstracts. Never add facts from your own knowledge.
- If the documents do not answer the question, say so plainly and describe what \
they do cover. Do not speculate to fill the gap.
- Report what the literature states. Do not give treatment, dosing or \
prescribing recommendations, and do not address the reader as a patient.
- Where sources disagree, say so and attribute each position.
- Distinguish the strength of evidence: a case report, a cohort study and a \
computational prediction do not carry the same weight, and saying which is which \
matters more to a reviewer than a confident summary.
- Prose, not bullet lists, unless the question asks for an enumeration. Aim for \
120-220 words. Plain text — no markdown headings or bold."""

RESOLVER_SYSTEM = """You prepare a reviewer's question for a PubMed search.

Given the conversation so far and their latest message, produce:

- standalone_question: the latest message rewritten to stand on its own, with \
pronouns and ellipsis resolved from the conversation. If it already stands \
alone, return it unchanged.
- concepts: the two or three ideas the search turns on, each as a group of \
interchangeable terms. Within a group the terms are alternatives — the \
ingredient and its salts, or a clinical term alongside its MeSH heading and the \
words a paper's title would actually use. Across groups they are requirements. \
So {fusidic acid, fusidate} and {hepatotoxicity, liver injury, jaundice, \
cholestasis} finds papers about either name of the drug together with any of \
those liver terms. Give each term as plain words: no quote marks, no AND, no OR, \
no parentheses, no date filters — the query is assembled from the groups.

Two or three groups is right. One group is too broad to be useful; four or more \
rarely matches anything. Prefer ingredient names over brand names.

Resolve against the conversation, but do not widen the question: if the reviewer \
narrows to a population or an outcome, that becomes a group of its own."""

#: Concept groups rather than a finished query string, because a model writing
#: PubMed syntax into a JSON string has to escape the quote marks that phrase
#: searches need — and a schema-constrained decoder reads that quote as the end
#: of the string. The failure is silent: the query is truncated mid-expression
#: but the JSON still parses, so a garbage search looks like a successful one.
#: Terms come back as plain words and `_compose_query` does the quoting.
RESOLVER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "standalone_question": {
            "type": "string",
            "description": "The latest message, rewritten to stand alone.",
        },
        "concepts": {
            "type": "array",
            "description": (
                "Two or three concept groups. Terms within a group are "
                "alternatives; the groups are all required."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "terms": {
                        "type": "array",
                        "description": (
                            "Interchangeable plain-text terms. No operators, "
                            "quote marks or parentheses."
                        ),
                        "items": {"type": "string"},
                    }
                },
                "required": ["terms"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["standalone_question", "concepts"],
    "additionalProperties": False,
}

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
    """One retrieved paper. `article_id` is set when we already monitor it, so a
    citation can link to its detection report instead of PubMed. `cited` is set
    when the answer actually drew on it — retrieved and cited are not the same
    thing, and showing them as one overstates the evidence behind an answer."""

    number: int
    pmid: str
    title: str
    journal: str | None
    pub_date: str | None
    url: str
    abstract: str | None
    article_id: int | None = None
    cited: bool = False


@dataclass
class AnswerSegment:
    """A run of answer text with the citations the API attached to it."""

    text: str
    #: Source numbers this span was drawn from.
    citations: list[int] = field(default_factory=list)
    #: The sentence each citation quotes, parallel to `citations`.
    quotes: list[str] = field(default_factory=list)


@dataclass
class AssistantAnswer:
    question: str
    #: The resolved, self-contained form. Differs from `question` when the
    #: reviewer asked a follow-up.
    interpreted_question: str
    answer: str
    segments: list[AnswerSegment] = field(default_factory=list)
    sources: list[AssistantSource] = field(default_factory=list)
    pubmed_query: str = ""
    total_matches: int = 0
    model_id: str = ""
    synthesised: bool = False
    notice: str = NOTICE
    warning: str | None = None


#: Model families that take adaptive thinking and the ``effort`` ladder (Claude
#: 4.6 and later). Anything else — Haiku 4.5 included — takes the older shape:
#: an explicit thinking budget, and no ``effort`` at all.
#:
#: This is a gate rather than a hardcoded parameter set because the mismatch is
#: a 400, not a weaker answer: Haiku 4.5 rejects both ``thinking.adaptive`` and
#: ``effort``, while the Opus 5 family rejects ``thinking.enabled``. Confirmed
#: per model against ``GET /v1/models/{id}`` capabilities.
ADAPTIVE_TUNING_PREFIXES = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
)

#: Thinking budget for the answer call on models without adaptive thinking.
#: Enough to weigh a handful of abstracts against each other, and well inside
#: the answer call's ``max_tokens`` — which caps thinking and prose together.
ANSWER_THINKING_BUDGET = 2000


def _tunes_adaptively(model: str) -> bool:
    return model.startswith(ADAPTIVE_TUNING_PREFIXES)


def _resolver_tuning(model: str) -> dict[str, Any]:
    """Request shaping for the question-resolution call.

    The JSON schema applies to every supported model; only the effort hint is
    family-specific. Resolving a reference is not hard reasoning, so where the
    ladder exists we spend as little as possible and leave the budget for the
    answer.
    """
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": RESOLVER_SCHEMA}
    }
    if _tunes_adaptively(model):
        output_config["effort"] = "low"
    return {"output_config": output_config}


def _answer_tuning(model: str, effort: str) -> dict[str, Any]:
    """Request shaping for the citations answer call."""
    if _tunes_adaptively(model):
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
    # Older families: budgeted thinking, and `effort` would be rejected.
    return {
        "thinking": {"type": "enabled", "budget_tokens": ANSWER_THINKING_BUDGET}
    }


def _client() -> anthropic.AsyncAnthropic | None:
    """The Anthropic client, or None when the assistant is unconfigured."""
    settings = get_settings()
    if settings.llm_mock or not settings.llm_api_key:
        return None
    return anthropic.AsyncAnthropic(
        api_key=settings.llm_api_key, timeout=REQUEST_TIMEOUT_SECONDS
    )


def _quote_term(term: str) -> str:
    """Quote a search term for PubMed, keeping any field tag outside the quotes.

    ``liver injury`` becomes a phrase search; ``Drug Resistance,
    Bacterial[MeSH]`` has to be quoted *inside* the tag
    (``"Drug Resistance, Bacterial"[MeSH]``) or PubMed reads the comma as a
    separate term. Single words are left bare — quoting them would suppress
    PubMed's automatic term mapping to MeSH and lose relevant papers.
    """
    if term.endswith("]") and "[" in term:
        head, _, tag = term.rpartition("[")
        head = head.strip()
        return f'"{head}"[{tag}' if " " in head else f"{head}[{tag}"
    return f'"{term}"' if " " in term else term


def _compose_query(concepts: list[dict[str, Any]]) -> str:
    """Assemble a PubMed query from the resolver's concept groups.

    Groups become parenthesised OR alternatives joined by AND. Quoting happens
    here rather than in the model's output: a multi-word term is a phrase search
    and needs quote marks, which is exactly the character the model cannot emit
    safely inside a JSON string. A term already carrying a field tag
    (``liver[MeSH]``) is passed through untouched.
    """
    groups: list[str] = []
    # Bounds are enforced here, not in the schema: structured-output schemas
    # reject minItems/maxItems on arrays, so the caps are ours to apply.
    for concept in concepts[:MAX_CONCEPT_GROUPS]:
        terms: list[str] = []
        seen: set[str] = set()
        for raw in (concept.get("terms") or [])[:MAX_TERMS_PER_GROUP]:
            # Strip any operator syntax the model added despite instructions —
            # it would otherwise nest inside our own parentheses.
            term = str(raw).replace('"', " ").replace("(", " ").replace(")", " ")
            term = " ".join(term.split())
            if not term or term.upper() in {"AND", "OR", "NOT"}:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(_quote_term(term))
        if terms:
            groups.append(terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")")
    return " AND ".join(groups)


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


def _first_sentences(text: str, count: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(p for p in parts[:count] if p).strip()


async def _resolve_question(
    client: anthropic.AsyncAnthropic,
    question: str,
    history: list[tuple[str, str]],
) -> tuple[str, str] | None:
    """Resolve a follow-up and translate it into a PubMed query.

    Structured output rather than free text: the schema guarantees both fields
    are present, so a malformed reply can't silently become the search query.
    """
    settings = get_settings()
    turns: list[dict[str, Any]] = []
    for prior_question, prior_answer in history[-HISTORY_TURNS:]:
        turns.append({"role": "user", "content": prior_question})
        # The prior answer is truncated: the resolver needs enough to resolve a
        # reference, not the whole prose.
        turns.append({"role": "assistant", "content": prior_answer[:600]})
    turns.append({"role": "user", "content": question})

    try:
        response = await client.messages.create(
            model=settings.assistant_model,
            max_tokens=2000,
            system=RESOLVER_SYSTEM,
            messages=turns,
            **_resolver_tuning(settings.assistant_model),
        )
    except Exception as exc:
        logger.warning("assistant resolver failed: %s: %s", type(exc).__name__, exc)
        return None

    # A truncated reply can still be parseable, so treat the cutoff itself as
    # the failure rather than trusting whatever survived it.
    if response.stop_reason == "max_tokens":
        logger.warning("assistant resolver hit max_tokens; falling back")
        return None

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except Exception:
        logger.warning("assistant resolver returned non-JSON")
        return None
    standalone = str(data.get("standalone_question") or "").strip()
    concepts = data.get("concepts")
    if not isinstance(concepts, list):
        return None
    query = _compose_query(concepts)
    return (standalone or question, query) if query else None


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
    return [
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
        for index, article in enumerate(articles, start=1)
    ]


def _document_blocks(sources: list[AssistantSource]) -> list[dict[str, Any]]:
    """Each abstract as a citable document.

    `citations` is enabled on every block — the API requires all or none — so
    every claim the model makes can be traced to the sentence behind it.
    """
    blocks: list[dict[str, Any]] = []
    for source in sources:
        text = (source.abstract or "No abstract available.")[:MAX_ABSTRACT_CHARS]
        blocks.append(
            {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": text},
                "title": f"[{source.number}] {source.title}",
                "context": (
                    f"PMID {source.pmid}"
                    f" · {source.journal or 'journal not stated'}"
                    f"{f' · {source.pub_date}' if source.pub_date else ''}"
                ),
                "citations": {"enabled": True},
            }
        )
    return blocks


def _read_segments(
    content: list[Any], sources: list[AssistantSource]
) -> list[AnswerSegment]:
    """Turn the API's cited text blocks into segments.

    With citations enabled the response arrives as several text blocks, the
    cited ones carrying a `citations` array. `document_index` is the position of
    the document we sent, which is the source number minus one.
    """
    segments: list[AnswerSegment] = []
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        numbers: list[int] = []
        quotes: list[str] = []
        for citation in getattr(block, "citations", None) or []:
            index = getattr(citation, "document_index", None)
            if index is None or not (0 <= index < len(sources)):
                continue
            source = sources[index]
            source.cited = True
            if source.number not in numbers:
                numbers.append(source.number)
                quotes.append((getattr(citation, "cited_text", "") or "").strip())
        segments.append(
            AnswerSegment(text=block.text, citations=numbers, quotes=quotes)
        )
    return segments


def _extractive_answer(sources: list[AssistantSource]) -> str:
    """Answer without a model: say so, then hand over the evidence."""
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


async def ask(
    db: Session,
    question: str,
    *,
    limit: int = 6,
    history: list[tuple[str, str]] | None = None,
) -> AssistantAnswer:
    """Answer `question` from PubMed, with citations.

    `history` is the prior (question, answer) turns of this conversation, oldest
    first. It is used only to resolve the question — each answer is grounded in
    a fresh retrieval, so a follow-up never inherits the previous turn's sources.
    """
    question = question.strip()
    if not question:
        raise ValueError("A question is required")
    history = history or []

    client = _client()
    heuristic = _keyword_query(question)
    interpreted = question
    pubmed_query = heuristic

    if client is not None:
        resolved = await _resolve_question(client, question, history)
        if resolved:
            interpreted, pubmed_query = resolved

    warning: str | None = None
    articles: list[PubMedArticleDTO] = []
    total = 0
    try:
        async with PubMedClient() as pubmed:
            # Relevance rather than recency: the best answer to a question is
            # rarely just the newest paper about it.
            result = await pubmed.esearch(pubmed_query, retmax=limit, sort="relevance")
            total = result.count
            if not result.pmids and pubmed_query != heuristic:
                # The model's query was too narrow — fall back to keywords from
                # the resolved question rather than reporting no evidence.
                fallback = _keyword_query(interpreted)
                result = await pubmed.esearch(fallback, retmax=limit, sort="relevance")
                if result.pmids:
                    pubmed_query = fallback
                    total = result.count
            if result.pmids:
                articles = await pubmed.efetch(result.pmids[:limit])
    except Exception as exc:
        logger.warning("assistant PubMed search failed: %s", exc)
        warning = getattr(exc, "user_message", None) or (
            "PubMed could not be reached, so this answer has no sources behind it."
        )

    sources = _to_sources(db, articles)

    segments: list[AnswerSegment] = []
    answer = ""
    model_id = ""
    synthesised = False

    if sources and client is not None:
        settings = get_settings()
        t0 = time.perf_counter()
        try:
            response = await client.messages.create(
                model=settings.assistant_model,
                # Room for thinking and the answer: max_tokens caps both
                # together.
                max_tokens=8000,
                system=ANSWER_SYSTEM,
                **_answer_tuning(
                    settings.assistant_model, settings.assistant_effort
                ),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            *_document_blocks(sources),
                            {
                                "type": "text",
                                "text": f"Question: {interpreted}",
                            },
                        ],
                    }
                ],
            )
        except Exception as exc:
            logger.warning(
                "assistant answer call failed: %s: %s", type(exc).__name__, exc
            )
        else:
            if response.stop_reason == "refusal":
                warning = (
                    "The model declined to answer this question. Rephrase it, or "
                    "read the retrieved sources directly."
                )
            else:
                segments = _read_segments(response.content, sources)
                answer = "".join(segment.text for segment in segments).strip()
                model_id = response.model
                synthesised = bool(answer)
                logger.info(
                    "assistant answered in %sms from %s sources (%s cited)",
                    round((time.perf_counter() - t0) * 1000),
                    len(sources),
                    sum(1 for s in sources if s.cited),
                )

    if not answer:
        answer = _extractive_answer(sources)
        segments = [AnswerSegment(text=answer)]
        if sources and not synthesised and not warning:
            warning = (
                "Language-model synthesis was unavailable, so the retrieved "
                "abstracts are shown instead of a written answer."
            )

    return AssistantAnswer(
        question=question,
        interpreted_question=interpreted,
        answer=answer,
        segments=segments,
        sources=sources,
        pubmed_query=pubmed_query,
        total_matches=total,
        model_id=model_id,
        synthesised=synthesised,
        warning=warning,
    )
