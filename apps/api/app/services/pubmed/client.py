"""NCBI PubMed E-utilities client (free public API).

Integrates via HTTPS only — no scraping.
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.pubmed.errors import PubMedError


@dataclass
class PubMedArticleDTO:
    pmid: str
    title: str
    abstract: str | None
    journal: str | None
    authors: list[str]
    pub_date: date | None
    doi: str | None
    mesh_terms: list[str]
    publication_types: list[str]
    pubmed_url: str
    content_hash: str


@dataclass
class ESearchResult:
    count: int
    pmids: list[str]
    raw_hash: str
    query: str


class RateLimiter:
    """Simple token-bucket style limiter for NCBI (3 rps no key / 10 rps with key)."""

    def __init__(self, rate_per_sec: float) -> None:
        self.min_interval = 1.0 / max(rate_per_sec, 0.1)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self.min_interval - (now - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class PubMedClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        rps = 10.0 if self.settings.ncbi_api_key else 3.0
        self._limiter = RateLimiter(rps)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PubMedClient:
        self._client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _common_params(self) -> dict[str, str]:
        params: dict[str, str] = {
            "tool": self.settings.ncbi_tool,
            "email": self.settings.ncbi_email,
        }
        if self.settings.ncbi_api_key:
            params["api_key"] = self.settings.ncbi_api_key
        return params

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        assert self._client is not None
        if not (self.settings.ncbi_email or "").strip() or self.settings.ncbi_email in (
            "dev@example.com",
            "your.email@company.com",
        ):
            # Still allow placeholder for offline demos, but surface a clear warning path
            # when live calls fail — NCBI requires a real contact email.
            pass
        await self._limiter.wait()
        url = f"{self.settings.ncbi_base_url.rstrip('/')}/{path}"
        merged = {**self._common_params(), **params}
        last_resp: httpx.Response | None = None
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                resp = await self._client.get(url, params=merged)
            except httpx.TimeoutException as exc:
                last_exc = exc
                await asyncio.sleep(2**attempt)
                continue
            except httpx.RequestError as exc:
                last_exc = exc
                await asyncio.sleep(2**attempt)
                continue
            last_resp = resp
            if resp.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(2**attempt)
                continue
            if resp.status_code >= 400:
                raise PubMedError(
                    f"NCBI {path} HTTP {resp.status_code}: {resp.text[:300]}",
                    user_message=_friendly_http_error(resp.status_code, path),
                    status_code=resp.status_code,
                    retryable=resp.status_code in (408, 429) or resp.status_code >= 500,
                )
            return resp
        if last_resp is not None:
            raise PubMedError(
                f"NCBI {path} failed after retries: HTTP {last_resp.status_code}",
                user_message=_friendly_http_error(last_resp.status_code, path)
                + " Retries exhausted — try again later or add NCBI_API_KEY.",
                status_code=last_resp.status_code,
                retryable=True,
            )
        raise PubMedError(
            f"NCBI {path} network error: {last_exc}",
            user_message=(
                "Could not reach NCBI E-utilities (network/timeout). "
                "Check connectivity and NCBI_EMAIL, then retry."
            ),
            retryable=True,
        )

    async def esearch(
        self,
        term: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        retmax: int = 10000,
        sort: str = "pub_date",
    ) -> ESearchResult:
        query = term.strip()
        if date_from and date_to:
            query = (
                f'({query}) AND ("{date_from.strftime("%Y/%m/%d")}"[PDAT] : '
                f'"{date_to.strftime("%Y/%m/%d")}"[PDAT])'
            )
        elif date_from:
            query = f'({query}) AND ("{date_from.strftime("%Y/%m/%d")}"[PDAT] : "3000"[PDAT])'

        resp = await self._get(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "retmax": str(retmax),
                "retmode": "json",
                # Monitoring wants newest first; question answering wants the
                # most on-topic papers, so the caller chooses.
                "sort": sort,
            },
        )
        try:
            data = resp.json()
        except Exception as exc:
            raise PubMedError(
                f"ESearch invalid JSON: {exc}",
                user_message="PubMed ESearch returned non-JSON. Retry or check NCBI status.",
                retryable=True,
            ) from exc
        if "esearchresult" not in data and "error" in data:
            raise PubMedError(
                f"ESearch error: {data.get('error')}",
                user_message=f"PubMed rejected the query: {data.get('error')}",
                retryable=False,
            )
        result = data.get("esearchresult", {})
        if result.get("ERROR"):
            raise PubMedError(
                f"ESearch ERROR: {result.get('ERROR')}",
                user_message=f"PubMed ESearch error: {result.get('ERROR')}",
                retryable=False,
            )
        pmids = result.get("idlist") or []
        count = int(result.get("count") or len(pmids))
        raw_hash = hashlib.sha256(resp.content).hexdigest()
        return ESearchResult(count=count, pmids=pmids, raw_hash=raw_hash, query=query)

    async def efetch(self, pmids: list[str]) -> list[PubMedArticleDTO]:
        if not pmids:
            return []
        articles: list[PubMedArticleDTO] = []
        # Chunk to avoid URL length limits
        chunk_size = 150
        for i in range(0, len(pmids), chunk_size):
            chunk = pmids[i : i + chunk_size]
            resp = await self._get(
                "efetch.fcgi",
                {
                    "db": "pubmed",
                    "id": ",".join(chunk),
                    "retmode": "xml",
                },
            )
            articles.extend(parse_efetch_xml(resp.text))
        return articles


def parse_efetch_xml(xml_text: str) -> list[PubMedArticleDTO]:
    root = ET.fromstring(xml_text)
    out: list[PubMedArticleDTO] = []
    for article_el in root.findall(".//PubmedArticle"):
        medline = article_el.find("MedlineCitation")
        if medline is None:
            continue
        pmid_el = medline.find("PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        pmid = pmid_el.text.strip()

        art = medline.find("Article")
        title = ""
        abstract = None
        journal = None
        authors: list[str] = []
        pub_date_val: date | None = None
        doi = None
        pub_types: list[str] = []

        if art is not None:
            title_el = art.find("ArticleTitle")
            title = "".join(title_el.itertext()).strip() if title_el is not None else ""

            abs_el = art.find("Abstract")
            if abs_el is not None:
                parts = [
                    "".join(t.itertext()).strip()
                    for t in abs_el.findall("AbstractText")
                ]
                abstract = " ".join(p for p in parts if p) or None

            journal_el = art.find("Journal/Title")
            if journal_el is not None and journal_el.text:
                journal = journal_el.text.strip()

            for author in art.findall("AuthorList/Author"):
                last = author.findtext("LastName") or ""
                fore = author.findtext("ForeName") or author.findtext("Initials") or ""
                collective = author.findtext("CollectiveName")
                if collective:
                    authors.append(collective.strip())
                elif last:
                    authors.append(f"{last} {fore}".strip())

            for pt in art.findall("PublicationTypeList/PublicationType"):
                if pt.text:
                    pub_types.append(pt.text.strip())

            # DOI
            for id_el in art.findall("ELocationID"):
                if id_el.get("EIdType") == "doi" and id_el.text:
                    doi = id_el.text.strip()

            # Pub date
            pd = art.find("Journal/JournalIssue/PubDate")
            if pd is not None:
                year = pd.findtext("Year")
                month = pd.findtext("Month") or "1"
                day = pd.findtext("Day") or "1"
                if year:
                    pub_date_val = _safe_date(year, month, day)
                else:
                    medline_date = pd.findtext("MedlineDate")
                    if medline_date:
                        m = re.search(r"(19|20)\d{2}", medline_date)
                        if m:
                            pub_date_val = date(int(m.group(0)), 1, 1)

        # ArticleIdList for DOI fallback
        if not doi:
            for aid in article_el.findall(".//ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text.strip()

        mesh_terms: list[str] = []
        for mh in medline.findall("MeshHeadingList/MeshHeading/DescriptorName"):
            if mh.text:
                mesh_terms.append(mh.text.strip())

        content = f"{pmid}|{title}|{abstract or ''}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        out.append(
            PubMedArticleDTO(
                pmid=pmid,
                title=title or f"(No title) PMID {pmid}",
                abstract=abstract,
                journal=journal,
                authors=authors,
                pub_date=pub_date_val,
                doi=doi,
                mesh_terms=mesh_terms,
                publication_types=pub_types,
                pubmed_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                content_hash=content_hash,
            )
        )
    return out


def _friendly_http_error(status: int, path: str) -> str:
    op = "ESearch" if "esearch" in path else "EFetch" if "efetch" in path else "NCBI"
    if status == 429:
        return (
            f"{op} rate-limited (HTTP 429). Add NCBI_API_KEY for higher limits "
            "or wait and retry."
        )
    if status in (401, 403):
        return f"{op} unauthorized (HTTP {status}). Check NCBI_API_KEY if set."
    if status == 400:
        return f"{op} bad request (HTTP 400). Check the search string syntax."
    if status >= 500:
        return f"{op} NCBI server error (HTTP {status}). Retry later."
    return f"{op} failed (HTTP {status}). See run error details and retry if needed."


_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _safe_date(year: str, month: str, day: str) -> date | None:
    try:
        y = int(year)
        if month.isdigit():
            m = int(month)
        else:
            m = _MONTHS.get(month[:3].lower(), 1)
        d = int(day) if str(day).isdigit() else 1
        return date(y, max(1, min(m, 12)), max(1, min(d, 28)))
    except (ValueError, TypeError):
        return None
