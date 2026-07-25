"""Fail-open path: LLM errors fall back to heuristic with audit meta."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.core.config import get_settings
from app.services.ai.scorer import score_article


def test_fail_open_on_timeout(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_mock", False)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.side_effect = httpx.TimeoutException("timed out")

    with patch("app.services.ai.scorer.httpx.AsyncClient", return_value=mock_client):
        out, model, is_mock, meta = asyncio.run(
            score_article(
                title="DrugX case report in a patient",
                abstract="We report rash after DrugX.",
                product_names=["DrugX"],
            )
        )

    assert is_mock
    assert model == "heuristic-fallback-v1"
    assert meta["llm_fallback"] is True
    assert meta["llm_timeout"] is True
    assert out.product_match > 0
