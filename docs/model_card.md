# Model card — LitMon-PV screening (pilot)

| Field | Value |
|-------|-------|
| System | Literature Monitoring Automation for Pharmacovigilance |
| Component | AI relevance / ICSR pre-screen |
| Version tags | `prompt_version`, `ruleset_version`, `threshold_version` (env / settings) |
| Status | Pilot — not GxP validated |

## Intended use

Rank and explain biomedical abstracts for a monitored product. Route to Auto-Clear, Standard, Priority, or Expedited queues. **Humans decide** reportability.

## Out of scope

- Final ICSR validity without human review  
- Silent discard of potential cases  
- Direct regulatory submission  

## Inputs

- Title, abstract, journal, MeSH terms  
- Monitored product names / brands / synonyms  

## Outputs

- `product_match`, `event_relevance`, `icsr_criteria_match`, `composite`  
- Reason tags with evidence labels  
- ICSR four-criteria pre-check  
- Hard-rule candidates (death, pregnancy, pediatric, IME, ambiguous)  

## Modes

| Mode | When | Model id |
|------|------|----------|
| Mock / heuristic | `LLM_MOCK=true` or no API key | `heuristic-mock-v1` |
| LLM structured JSON | `LLM_MOCK=false` + key | configured `LLM_MODEL` |
| Fallback (fail-open) | LLM timeout / HTTP / parse error after retries | `heuristic-fallback-v1` |

### Fail-open policy

Articles are **never dropped** because the LLM is down. On transport timeout,
5xx/429 (after limited retries), 4xx, or invalid JSON:

1. Score with the deterministic heuristic (same as mock, tends to over-flag).  
2. Set `is_mock=true`, `model_id=heuristic-fallback-v1`.  
3. Emit audit event `llm_fallback_heuristic` on the article.  
4. Increment Ops metrics: `scoring.llm_fallbacks`, `scoring.llm_timeouts`, `scoring.llm_retries`.

Admin → **Runtime config** shows `LLM_MOCK` / live mode (env-driven; restart API to change).

## Thresholds (starting — calibrate in pilot)

| Band | Composite | Queue | SLA |
|------|-----------|-------|-----|
| Auto-clear | &lt; 0.15 | Auto-Clear (+10% QC) | 5 business days QC |
| Uncertain | 0.15–0.65 | Standard | 5 business days |
| Likely relevant | 0.65–0.85 | Priority | 2 business days |
| High ICSR | ≥ 0.85 or hard rule | Expedited | 24 hours |

## Primary KPI

**Sensitivity** (1 − missed-case rate). False negatives are costlier than false positives.

Run: `POST /api/evaluation/run` against `data/seed/gold_labels.json`.

## Risks

| Risk | Mitigation |
|------|------------|
| Silent false negatives | Over-flag; no silent delete; QC sample; recall |
| Hallucinated entities | Reason tags + human checklist authoritative |
| Drift | Version logging; quarterly gold re-run |

## Change control

Bump `prompt_version` / `ruleset_version` / `threshold_version` on any change that affects scores or routing. All three are stored on every `ScreeningResult`.
