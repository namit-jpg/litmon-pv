# Parallel-run protocol (partner-feedback MVP)

## Objective

For **one product line**, one reporting cycle, measure whether LitMon-PV surfaces at least the same reportable cases as the existing manual process (sensitivity ≥ 95% target).

## Setup

1. PV Lead and LitMon admin align **search strings** with the current manual PubMed strategy.
2. Record search string version in the system (`SearchString`).
3. Configure weekly cadence (Task Scheduler / cron → `workers/scheduled_search.py`) matching manual cycle.
4. Keep **manual process independent** — do not use system queues as the manual team’s source.

## Execution

1. At cycle start, note date window (e.g. previous 7 days).
2. System: run a bounded search from **Product search**, or let the configured schedule run.
3. Manual: continue usual screening and ICSR decisions.
4. At cycle end:
   - Export **parallel-run package** from **Pilot tools** → Generate parallel-run package
     (`POST /api/exports/parallel-run`)
   - Fill columns `manual_disposition`, `manual_is_icsr`, `manual_notes`.
   - Compute agreement and list **manual-only ICSRs** (system false negatives).

## Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| Sensitivity | ICSRs found by manual that system also surfaced (not pure auto-clear) | ≥ 95% |
| Workload reduction | Share auto-cleared without QC | Track; aim ≥ 40% of volume |
| False positives | System priority/expedited that manual marks not-a-case | Track (secondary) |

## Rules

- If any **false negative** is found: lower Auto-Clear threshold or add hard rules before expanding products.
- Do not enable unattended Auto-Clear as final disposition without QC until sensitivity is proven.
- All overrides and recalls remain in the audit trail.

## Gate to validated operational use

Document results. Proceed to CSV/SOP/validation only after PV Lead and Quality agree thresholds may be locked.
