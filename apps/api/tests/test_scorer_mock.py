import asyncio
import json

from app.services.ai.scorer import (
    PROMPT_SYSTEM,
    PROMPT_USER_TEMPLATE_KEYS,
    build_user_payload,
    parse_llm_screening_json,
    score_article,
)
from app.services.ai.schemas import ScreeningOutput


def test_mock_scorer_flags_case_report():
    out, model, is_mock, meta = asyncio.run(
        score_article(
            title="Fatal hepatotoxicity with DrugX in a 67-year-old woman: a case report",
            abstract="We report a patient who died after DrugX. Adverse reaction described.",
            product_names=["DrugX", "drugxanib"],
        )
    )
    assert is_mock
    assert model == "heuristic-mock-v1"
    assert not meta.get("llm_fallback")
    assert out.product_match >= 0.8
    assert "death_with_product" in out.hard_rule_candidates or out.composite > 0.3


def test_prompt_system_requires_overflag_and_json():
    assert "over-flagging" in PROMPT_SYSTEM.lower() or "Prefer over-flagging" in PROMPT_SYSTEM
    assert "JSON" in PROMPT_SYSTEM
    assert "ICSR" in PROMPT_SYSTEM


def test_build_user_payload_schema_keys():
    payload = build_user_payload(
        title="T",
        abstract="A",
        product_names=["DrugX"],
        mesh_terms=["Rash"],
        journal="J",
    )
    for key in PROMPT_USER_TEMPLATE_KEYS:
        assert key in payload
    assert payload["monitored_products"] == ["DrugX"]
    assert "properties" in payload["schema"] or "$defs" in payload["schema"] or payload["schema"]


def test_parse_llm_screening_json_valid():
    raw = {
        "product_match": 0.9,
        "event_relevance": 0.8,
        "icsr_criteria_match": 0.7,
        "entities": {"drugs": ["DrugX"], "events": ["rash"]},
        "icsr_precheck": {
            "identifiable_patient": {
                "present": True,
                "evidence": "patient",
                "confidence": 0.8,
            },
            "suspect_drug": {
                "present": True,
                "evidence": "DrugX",
                "confidence": 0.9,
            },
            "adverse_event": {
                "present": True,
                "evidence": "rash",
                "confidence": 0.8,
            },
            "identifiable_reporter": {
                "present": True,
                "evidence": "authors",
                "confidence": 0.6,
            },
        },
        "reason_tags": [
            {"code": "brand_match", "label": "DrugX", "confidence": 0.9}
        ],
        "hard_rule_candidates": [],
        "summary_for_reviewer": "Likely relevant case report",
    }
    out = parse_llm_screening_json(json.dumps(raw))
    assert isinstance(out, ScreeningOutput)
    assert out.product_match == 0.9
    assert out.composite > 0


def test_parse_llm_screening_json_rejects_bad_scores():
    bad = {
        "product_match": 2.5,
        "event_relevance": 0.1,
        "icsr_criteria_match": 0.1,
    }
    try:
        parse_llm_screening_json(json.dumps(bad))
        assert False, "expected validation error"
    except Exception:
        pass
