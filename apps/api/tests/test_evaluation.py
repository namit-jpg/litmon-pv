import asyncio

import pytest

from app.services.evaluation import evaluate_gold_set, load_gold_set

# A small, explicit validation set. Supplied by the test rather than shipped
# with the application: a sensitivity KPI computed on invented articles that
# ship as a fixture is a fabricated number.
GOLD = [
    {
        "id": "t1",
        "title": "Fatal hepatotoxicity after warfarin in a 67-year-old: case report",
        "abstract": (
            "We report a 67-year-old woman who developed acute liver failure "
            "and died after exposure to warfarin. The adverse reaction and "
            "hospital course are described."
        ),
        "is_icsr": True,
        "should_surface": True,
    },
    {
        "id": "t2",
        "title": "Efficacy of warfarin in a phase III hypertension trial",
        "abstract": (
            "A randomized controlled trial of warfarin versus placebo showed "
            "blood pressure reduction. No serious adverse events were observed."
        ),
        "is_icsr": False,
        "should_surface": False,
    },
    {
        "id": "t3",
        "title": "Anaphylaxis following warfarin administration: a case report",
        "abstract": (
            "A 41-year-old man developed anaphylaxis within minutes of "
            "receiving warfarin and required hospitalisation."
        ),
        "is_icsr": True,
        "should_surface": True,
    },
]

NAMES = ["warfarin"]


def test_missing_gold_set_reports_not_configured():
    """No validation set ships with the app, so this must degrade cleanly
    rather than raising or inventing a KPI."""
    result = asyncio.run(evaluate_gold_set(gold=[], product_names=NAMES))
    assert result["configured"] is False
    assert result["total"] == 0
    assert "sensitivity" not in result


def test_default_load_finds_no_bundled_fixture():
    """Guards against a demo gold set being reintroduced into the repo."""
    assert load_gold_set() == []


def test_evaluation_requires_product_names():
    """Scoring against the wrong product silently tanks recall, so refuse
    rather than fall back to a hardcoded product."""
    with pytest.raises(ValueError):
        asyncio.run(evaluate_gold_set(gold=GOLD, product_names=[]))


def test_evaluation_scores_a_supplied_gold_set():
    result = asyncio.run(evaluate_gold_set(gold=GOLD, product_names=NAMES))
    assert result["n"] == len(GOLD)
    assert result["tp"] + result["fp"] + result["tn"] + result["fn"] == result["n"]
    assert "sensitivity" in result
    # Sensitivity is the primary KPI: reportable cases must not be dropped.
    assert result["fn"] == 0 or result["sensitivity"] is None or result["sensitivity"] >= 0.5
