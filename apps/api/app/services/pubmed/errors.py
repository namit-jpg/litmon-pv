"""User-facing PubMed / NCBI E-utilities errors."""

from __future__ import annotations


class PubMedError(Exception):
    """Raised when NCBI E-utilities calls fail in a way operators can act on."""

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or message
        self.status_code = status_code
        self.retryable = retryable

    def __str__(self) -> str:
        return self.user_message
