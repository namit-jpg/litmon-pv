"""LLM + structured extraction scorer for literature articles."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.ai.schemas import (
    CriterionCheck,
    IcsrPrecheck,
    ReasonTag,
    ScreeningOutput,
)

logger = logging.getLogger("litmon.scorer")

PROMPT_SYSTEM = """You are a pharmacovigilance literature screening assistant.
Score biomedical abstracts for product relevance, adverse-event relevance, and ICSR
minimum criteria (identifiable patient, suspect drug, adverse event, identifiable reporter).
Return ONLY valid JSON matching the schema. Prefer over-flagging possible cases.
Include short evidence quotes in reason tags and icsr_precheck.evidence fields.
Never invent PMIDs or citations not present in the input."""

PROMPT_USER_TEMPLATE_KEYS = (
    "title",
    "abstract",
    "journal",
    "mesh_terms",
    "monitored_products",
    "schema",
)

# Default HTTP timeout for LLM calls (seconds)
LLM_TIMEOUT_SECONDS = 90.0
LLM_MAX_RETRIES = 2


def build_user_payload(
    *,
    title: str,
    abstract: str | None,
    product_names: list[str],
    mesh_terms: list[str] | None = None,
    journal: str | None = None,
) -> dict[str, Any]:
    """Structured user message body sent to the LLM (unit-testable)."""
    return {
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "mesh_terms": mesh_terms or [],
        "monitored_products": product_names,
        "schema": ScreeningOutput.model_json_schema(),
    }


def parse_llm_screening_json(content: str) -> ScreeningOutput:
    """Parse and validate model JSON into ScreeningOutput (unit-testable)."""
    text = (content or "").strip()
    # Models sometimes wrap JSON in ```json ... ``` fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    # Fallback: extract first {...} block if prose sneaks in
    if text and not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
    parsed = json.loads(text)
    return ScreeningOutput.model_validate(parsed)


def _product_dictionary_boost(
    text: str, product_names: list[str]
) -> tuple[float, list[ReasonTag]]:
    text_l = text.lower()
    tags: list[ReasonTag] = []
    best = 0.0
    for name in product_names:
        if not name:
            continue
        if name.lower() in text_l:
            conf = 0.95 if len(name) > 4 else 0.8
            best = max(best, conf)
            tags.append(
                ReasonTag(
                    code="brand_match",
                    label=f"suspect drug: {name} (dictionary match)",
                    confidence=conf,
                )
            )
    return best, tags


def _heuristic_screen(
    title: str,
    abstract: str | None,
    product_names: list[str],
    mesh_terms: list[str] | None = None,
) -> ScreeningOutput:
    """Deterministic mock / fallback scorer for demos and offline mode."""
    text = f"{title}\n{abstract or ''}"
    text_l = text.lower()
    mesh = " ".join(mesh_terms or []).lower()

    prod_boost, prod_tags = _product_dictionary_boost(text + " " + mesh, product_names)
    product_match = prod_boost if prod_boost else 0.08

    event_terms = [
        "adverse",
        "toxicity",
        "hepatotoxicity",
        "side effect",
        "safety",
        "reaction",
        "anaphylaxis",
        "rash",
        "death",
        "fatal",
        "hospitali",
        "overdose",
        "case report",
    ]
    event_hits = [t for t in event_terms if t in text_l]
    event_relevance = min(0.15 + 0.12 * len(event_hits), 0.95) if event_hits else 0.1
    if "efficacy" in text_l and not event_hits:
        event_relevance = 0.12

    patient_cues = any(
        x in text_l
        for x in ["patient", "year-old", "yo ", "woman", "man", "infant", "child"]
    )
    reporter_cues = bool(re.search(r"we report|case of|authors?", text_l))
    drug_cues = product_match >= 0.5
    event_cues = event_relevance >= 0.4

    criteria_score = (
        (0.25 if patient_cues else 0.05)
        + (0.25 if drug_cues else 0.05)
        + (0.25 if event_cues else 0.05)
        + (0.25 if reporter_cues else 0.1)
    )

    hard: list[Any] = []
    if any(x in text_l for x in ["death", "died", "fatal"]) and product_match >= 0.4:
        hard.append("death_with_product")
    if any(x in text_l for x in ["pregnan", "fetal", "foetal", "trimester"]):
        hard.append("pregnancy")
    if any(x in text_l for x in ["pediatric", "paediatric", "infant", "neonate", "child"]):
        hard.append("pediatric")
    if 0.2 <= criteria_score <= 0.55 and product_match >= 0.4:
        hard.append("ambiguous_icsr")

    tags = list(prod_tags)
    for t in event_hits[:5]:
        tags.append(
            ReasonTag(
                code="event_term",
                label=f"event term: {t}",
                confidence=0.7,
            )
        )
    if "case report" in text_l:
        tags.append(
            ReasonTag(
                code="case_structure",
                label="case structure: case report language detected",
                confidence=0.8,
            )
        )

    precheck = IcsrPrecheck(
        identifiable_patient=CriterionCheck(
            present=patient_cues,
            evidence="patient descriptor found" if patient_cues else "",
            confidence=0.7 if patient_cues else 0.2,
        ),
        suspect_drug=CriterionCheck(
            present=drug_cues,
            evidence=prod_tags[0].label if prod_tags else "",
            confidence=product_match,
        ),
        adverse_event=CriterionCheck(
            present=event_cues,
            evidence=", ".join(event_hits[:3]),
            confidence=event_relevance,
        ),
        identifiable_reporter=CriterionCheck(
            present=reporter_cues,
            evidence="author/report language" if reporter_cues else "",
            confidence=0.6 if reporter_cues else 0.2,
        ),
    )

    summary = (
        f"Product match {product_match:.2f}; event relevance {event_relevance:.2f}; "
        f"ICSR criteria {criteria_score:.2f}. "
        + ("Hard rules: " + ", ".join(hard) if hard else "No hard-rule triggers.")
    )

    return ScreeningOutput(
        product_match=round(product_match, 4),
        event_relevance=round(event_relevance, 4),
        icsr_criteria_match=round(min(criteria_score, 1.0), 4),
        entities={
            "drugs": [t.label.split(":")[-1].strip() for t in prod_tags],
            "events": event_hits[:5],
            "study_type": "case_report" if "case report" in text_l else "other",
        },
        icsr_precheck=precheck,
        reason_tags=tags,
        hard_rule_candidates=hard,
        summary_for_reviewer=summary,
    )


def _apply_dictionary_boost(
    out: ScreeningOutput,
    title: str,
    abstract: str | None,
    product_names: list[str],
) -> ScreeningOutput:
    boost, boost_tags = _product_dictionary_boost(
        f"{title}\n{abstract or ''}", product_names
    )
    if boost > out.product_match:
        out.product_match = boost
        out.reason_tags = list(out.reason_tags) + boost_tags
    return out


async def score_article(
    *,
    title: str,
    abstract: str | None,
    product_names: list[str],
    mesh_terms: list[str] | None = None,
    journal: str | None = None,
) -> tuple[ScreeningOutput, str, bool, dict[str, Any]]:
    """Return (output, model_id, is_mock, meta).

    Fail-open policy: any LLM transport/parse error falls back to the heuristic
    scorer with ``model_id=heuristic-fallback-v1`` and ``meta.llm_fallback=True``
    so articles are never dropped for model outages.
    """
    settings = get_settings()
    meta: dict[str, Any] = {
        "llm_fallback": False,
        "llm_timeout": False,
        "llm_retries": 0,
        "error": None,
    }

    if settings.llm_mock or not settings.llm_api_key:
        out = _heuristic_screen(title, abstract, product_names, mesh_terms)
        return out, "heuristic-mock-v1", True, meta

    payload_user = build_user_payload(
        title=title,
        abstract=abstract,
        product_names=product_names,
        mesh_terms=mesh_terms,
        journal=journal,
    )

    last_error: str | None = None
    timed_out = False
    retries_used = 0

    # Anthropic OpenAI-compat rejects response_format.type=json_object
    # (expects json_schema). OpenAI-style providers accept json_object.
    is_anthropic = "anthropic.com" in (settings.llm_base_url or "").lower()

    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            t0 = time.perf_counter()
            body: dict[str, Any] = {
                "model": settings.llm_model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": PROMPT_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(payload_user),
                    },
                ],
            }
            if not is_anthropic:
                body["response_format"] = {"type": "json_object"}
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                out = parse_llm_screening_json(content)
                out = _apply_dictionary_boost(out, title, abstract, product_names)
                meta["llm_retries"] = retries_used
                meta["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                # Prefer provider-returned model id when present
                returned_model = data.get("model") or settings.llm_model
                return out, str(returned_model), False, meta
        except httpx.TimeoutException as exc:
            timed_out = True
            last_error = f"timeout: {exc}"
            retries_used = attempt
            logger.warning("LLM timeout attempt=%s: %s", attempt, exc)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            retries_used = attempt
            logger.warning("LLM error attempt=%s: %s", attempt, last_error)
            # Non-timeout HTTP 4xx usually won't help on retry
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                    break
        if attempt < LLM_MAX_RETRIES:
            # brief backoff before retry
            import asyncio

            await asyncio.sleep(0.5 * (2**attempt))

    # Fail-open: heuristic over-flags rather than dropping articles
    out = _heuristic_screen(title, abstract, product_names, mesh_terms)
    meta.update(
        {
            "llm_fallback": True,
            "llm_timeout": timed_out,
            "llm_retries": retries_used,
            "error": last_error,
        }
    )
    logger.warning(
        "LLM fail-open to heuristic: timeout=%s retries=%s error=%s",
        timed_out,
        retries_used,
        last_error,
    )
    return out, "heuristic-fallback-v1", True, meta
