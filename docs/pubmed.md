# PubMed integration (NCBI E-utilities)

## Summary

LitMon-PV talks to PubMed **only through the free NCBI Entrez Programming Utilities (E-utilities) HTTPS API**.

| Method | Used? |
|--------|-------|
| NCBI E-utilities API | **Yes** |
| Website scraping | No |
| Embase API | No (later phase) |

Base URL: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`

## Flow

1. **ESearch** — run product search string + optional publication date window → PMID list + count  
2. **EFetch** — fetch PubMed XML for new PMIDs → title, abstract, authors, journal, DOI, MeSH, publication types  
3. Persist `SearchRun` audit + `Article` rows; enqueue AI scoring  

## Credentials

| Env var | Required | Notes |
|---------|----------|-------|
| `NCBI_EMAIL` | Yes (NCBI policy) | Contact email sent on every request |
| `NCBI_API_KEY` | Recommended | Free from NCBI account; 3 → 10 requests/sec |
| `NCBI_TOOL` | Default `litmon-pv` | Application identifier |

No OAuth. API key is a query parameter, not a bearer token.

## Rate limits

- Without key: **3 requests/second**
- With key: **10 requests/second**

Client implements spacing + exponential backoff on 429/5xx.

## Date windows

`POST /api/search-runs` accepts either explicit `date_from` / `date_to` or convenience
`days` (7 / 14 / 30 presets in Admin). Window is applied as PubMed `[PDAT]`.

## Errors & retry

Transport/HTTP failures raise `PubMedError` with a short `user_message` and `retryable`
flag. Failed runs remain in the DB (`status=failed`, `error_message` set). Operators can
`POST /api/search-runs/{id}/retry` (same search string + date window → new SearchRun row)
from Admin or the search-run detail page. Common fixes: real `NCBI_EMAIL`, optional
`NCBI_API_KEY` for 429s.

## Audit

Every search run stores:

- Exact query snapshot (including date filter)
- Hit count, new vs re-hit counts
- Raw response hash
- Triggered-by actor
- Per-article link via `ArticleAppearance`

## References

- [E-utilities introduction](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- [API keys](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)
