"""NLM RxNorm (RxNav) client — the drug reference catalogue.

Free public API from the U.S. National Library of Medicine, the same body
behind PubMed. No API key required.
Docs: https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.rxnorm.errors import RxNormError

# RxNorm term types worth offering as a monitored product:
#   IN  - ingredient            e.g. "atorvastatin"
#   MIN - multi-ingredient      e.g. "amoxicillin / clavulanate"
#   BN  - brand name            e.g. "Lipitor"
# Dose-level types (SCD/SBD) are deliberately excluded: "atorvastatin 80 MG
# Oral Tablet" is a packaging detail, not something you monitor literature for.
CATALOG_TTYS = ("IN", "MIN", "BN")

# The "Prescribe" subset is RxNorm restricted to currently-marketed drugs.
# Using it over the full vocabulary drops ~12k research chemicals and withdrawn
# substances that nobody runs literature monitoring against, leaving a
# catalogue where every entry is a real, prescribable medicine.
PRESCRIBABLE_PATH = "Prescribe"

TTY_LABEL = {
    "IN": "ingredient",
    "MIN": "combination",
    "BN": "brand",
}


@dataclass
class RxNormConceptDTO:
    rxcui: str
    name: str
    tty: str


class RxNormClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> RxNormClient:
        self._client = httpx.AsyncClient(timeout=self.settings.rxnorm_timeout_seconds)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self._client is not None, "RxNormClient must be used as a context manager"
        url = f"{self.settings.rxnorm_base_url.rstrip('/')}/{path}"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._client.get(url, params=params or {})
            except httpx.TimeoutException as exc:
                last_exc = exc
                await asyncio.sleep(2**attempt)
                continue
            except httpx.RequestError as exc:
                last_exc = exc
                await asyncio.sleep(2**attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(2**attempt)
                continue
            if resp.status_code >= 400:
                raise RxNormError(
                    f"RxNorm {path} HTTP {resp.status_code}",
                    user_message=(
                        f"The drug catalogue service returned HTTP {resp.status_code}. "
                        "Try again shortly."
                    ),
                    status_code=resp.status_code,
                    retryable=resp.status_code >= 500 or resp.status_code == 429,
                )
            return resp.json()
        raise RxNormError(
            f"RxNorm {path} failed after retries: {last_exc}",
            user_message=(
                "Could not reach the NLM drug catalogue (rxnav.nlm.nih.gov). "
                "Check network access, then retry the sync."
            ),
            retryable=True,
        )

    async def fetch_catalog(
        self, ttys: tuple[str, ...] = CATALOG_TTYS
    ) -> list[RxNormConceptDTO]:
        """Download the marketed ingredient / combination / brand concepts.

        One call per term type (~11k concepts, a few seconds). Mirroring this
        locally keeps the drug picker instant and usable with no network,
        instead of paying a round trip per keystroke.
        """
        out: list[RxNormConceptDTO] = []
        seen: set[str] = set()
        for tty in ttys:
            data = await self._get(
                f"{PRESCRIBABLE_PATH}/allconcepts.json", {"tty": tty}
            )
            concepts = (data.get("minConceptGroup") or {}).get("minConcept") or []
            for c in concepts:
                rxcui = str(c.get("rxcui") or "").strip()
                name = (c.get("name") or "").strip()
                if not rxcui or not name or rxcui in seen:
                    continue
                seen.add(rxcui)
                out.append(
                    RxNormConceptDTO(rxcui=rxcui, name=name, tty=c.get("tty") or tty)
                )
        if not out:
            raise RxNormError(
                "RxNorm returned an empty catalogue",
                user_message=(
                    "The NLM drug catalogue came back empty. This is usually "
                    "transient — retry the sync."
                ),
                retryable=True,
            )
        return out

    async def related_names(self, rxcui: str) -> dict[str, list[str]]:
        """Ingredient and brand names related to a concept.

        Used to prefill a new product's INN and brand list so the generated
        PubMed query covers trade names, not just the substance.
        """
        # RxNorm expects the term types space-separated. Passing "IN+MIN+BN"
        # here would be percent-encoded to %2B and rejected — in a query string
        # "+" already *means* space.
        data = await self._get(
            f"rxcui/{rxcui}/related.json", {"tty": " ".join(CATALOG_TTYS)}
        )
        groups = (data.get("relatedGroup") or {}).get("conceptGroup") or []
        result: dict[str, list[str]] = {"IN": [], "MIN": [], "BN": []}
        for g in groups:
            tty = g.get("tty")
            if tty not in result:
                continue
            for prop in g.get("conceptProperties") or []:
                name = (prop.get("name") or "").strip()
                if name and name not in result[tty]:
                    result[tty].append(name)
        return result
