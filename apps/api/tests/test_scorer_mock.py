import asyncio

from app.services.ai.scorer import score_article


def test_mock_scorer_flags_case_report():
    out, model, is_mock = asyncio.run(
        score_article(
            title="Fatal hepatotoxicity with DrugX in a 67-year-old woman: a case report",
            abstract="We report a patient who died after DrugX. Adverse reaction described.",
            product_names=["DrugX", "drugxanib"],
        )
    )
    assert is_mock
    assert out.product_match >= 0.8
    assert "death_with_product" in out.hard_rule_candidates or out.composite > 0.3
