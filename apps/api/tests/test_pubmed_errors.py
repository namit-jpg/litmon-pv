from app.services.pubmed.client import _friendly_http_error
from app.services.pubmed.errors import PubMedError


def test_friendly_http_429():
    msg = _friendly_http_error(429, "esearch.fcgi")
    assert "rate-limited" in msg.lower() or "429" in msg
    assert "NCBI_API_KEY" in msg


def test_friendly_http_500():
    msg = _friendly_http_error(503, "efetch.fcgi")
    assert "server error" in msg.lower() or "503" in msg


def test_pubmed_error_user_message():
    err = PubMedError(
        "raw detail",
        user_message="Could not reach NCBI",
        retryable=True,
        status_code=None,
    )
    assert str(err) == "Could not reach NCBI"
    assert err.retryable is True
