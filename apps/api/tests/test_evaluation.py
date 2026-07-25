import asyncio

from app.services.evaluation import evaluate_gold_set


def test_gold_evaluation_runs():
    result = asyncio.run(evaluate_gold_set())
    assert result["n"] >= 5
    assert "sensitivity" in result
    assert result["tp"] + result["fp"] + result["tn"] + result["fn"] == result["n"]
    # With mock scorer, we should surface true ICSR cases (no FN preferred)
    assert result["fn"] == 0 or result["sensitivity"] is None or result["sensitivity"] >= 0.5
