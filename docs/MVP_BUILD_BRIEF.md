# MVP Build Brief — partner feedback implementation

**Status:** approved wireframe, not yet built
**Date:** 07 Aug 2026
**Scope:** Section 6 ("Recommended MVP Scope") of [partner_feedback.md](partner_feedback.md). Single client. Sections 7 (later phase) and the multi-client operating model are explicitly **out of scope**.

## Read these first, in this order

1. [partner_feedback.md](partner_feedback.md) — the partner requirements. Step numbers used throughout this brief refer to its Section 2.
2. [wireframes/mvp-wireframe.html](wireframes/mvp-wireframe.html) — **open this in a browser.** Nine clickable screens. The right-hand margin carries per-element build notes tagged `Exists` / `Changed` / `New` / `Open`, each naming the file or model it lands on. The "Annotations" button hides them.
3. [AGENTS.md](AGENTS.md) — repo conventions and non-negotiables. Still apply.

The wireframe is the design authority. Where this brief and the wireframe disagree, the wireframe wins.

## The core reframing

The app today is an **ICSR triage tool**. The partner is asking for a **PV literature-monitoring platform**. The engine (PubMed search, dedup, AI scoring, SLA routing, audit) is sound and stays. What changes is the domain model above it and the surfaces on top.

## Ordering — do it in these phases

Phase 1 unblocks everything else. Do not start Phase 3 before Phase 1 is merged.

### Phase 1 — Domain model

This is the load-bearing change. `ArticleStatus` currently conflates workflow state with classification outcome (`routed` and `under_review` sit in the same enum as `disposition_not_case` and `disposition_valid_icsr`). Split them.

- **New `Classification` enum**, 9 values — `potentially_relevant`, `potential_safety_signal`, `adverse_event_related`, `product_quality_related`, `duplicate`, `irrelevant`, `invalid`, `insufficient_information`, `requires_human_review`. Store both the AI-proposed value and the human-confirmed value; never overwrite the former. (Step 4)
- **`ArticleStatus` reduces to workflow state only** — the nine workspace folders in the wireframe are the target states.
- **New `SignalTag`** — 14 values, many-to-many with article, multi-select. Distinct from classification and from decision. `confirmed_signal` is settable only by `pv_lead`, and only once a `ReviewDecision` exists. (Step 6)
- **Extend `DecisionAction`** from 6 to 9 — add `mark_invalid`, `mark_duplicate`, `mark_not_relevant`, `prepare_for_submission`, `retain_internally`, `close_report`. (Step 10)
- **Extend `Product`** — `mah` (marketing authorisation holder), `markets` (JSON list of country codes), `monitoring_frequency`, `responsible_user_id` FK, and split `generic_name` / `active_ingredient` / `api` into real distinct columns. `inn` and `brands` stay. (Step 1)
- **New `ExtractedField` columns on `ScreeningResult`** — indication, dosage, outcome, country_of_occurrence, reporter_type, concomitant_medication, article_excerpts, relevance_reason, confidence, processed_at. These currently live in the loose `entities` JSON blob, which cannot be filtered or validated against. (Step 5)
- **New `Alert` entity** — type, priority, recipient, channels, read state, related entity, created_at. Alerts are currently fire-and-forget log lines with no persistence. (Step 7)
- **New `LiteratureSource` entity** — source vs provider vs access model. PubMed and PMC are sources; NLM/NCBI are the provider. Getting this modelled correctly is called out in Step 2 as a design requirement. (Step 2)
- **Priority field** on articles — currently urgency is inferred from `sla_due_at` alone.

Alembic migration required. There are existing migrations in `apps/api/alembic/versions/` — follow that pattern.

### Phase 2 — API

- `/api/articles` filters: currently queue, status, open_only. Add product, ingredient/API, date range, source, classification, signal status, submission status, assignee, priority, review status. Ten filters, all in the wireframe's workspace filter bar. (Step 9)
- New alert endpoints — list, mark read, settings.
- New dashboard metrics endpoint — the 15 measures in Step 12. Every one must be drillable, i.e. return a filter payload the workspace can consume.
- Extend `/api/queues/stats` for the new classification counts.
- Regulatory endpoints — validate, generate, record submission.

### Phase 3 — UI

Nine screens, mapped to existing files:

| Wireframe screen | Today | Action |
|---|---|---|
| Dashboard | `OpsPage.tsx` (infra metrics) | **New page.** Ops stays as a separate admin screen — do not merge them. |
| My workspace | `QueuePage.tsx` (severity tabs) | **Rework.** Folders replace tabs; severity becomes a priority column and a sort key. |
| Detection report | `ArticlePage.tsx` | **Extend.** ICSR checklist, rationale capture and audit already work — fold them in, don't rebuild. Add extraction fields, classification, signal tags, expanded decision set. Must render/export as a document (Step 11), not just a form. |
| Alerts | one button on `OpsPage.tsx` | **New page.** Inbox over the new `Alert` entity. |
| Submission & storage | `AdminPage.tsx` → Export packages | **New page.** Wraps the existing ICSR export with validation, versioning, submit/store decision, gateway record. |
| Audit trail | `AuditPage.tsx` | **Extend.** New event types + export. |
| Products | `AdminPage.tsx` (787 lines) | **Extract to own page.** New fields. |
| Literature sources | none | **New page.** |
| Search & schedule | `AdminPage.tsx` + `SearchRunPage.tsx` | **Extract and extend.** Per-product schedule, exception queue. |

`AdminPage.tsx` is 787 lines and currently holds products, search strings, PubMed runs, imports, evaluation and exports. Phase 3 breaks it up — that decomposition is most of the frontend work.

### Phase 4 — Alerts and regulatory

- Wire the 8 triggers in Step 7 to the existing `notifications.py`. It already logs and can send SMTP; today it has exactly one trigger (SLA breach). Two of the triggers — "scheduled search failed" and "no search completed in the expected period" — depend on the per-product schedule from Phase 1.
- Exception queue: anything the pipeline cannot complete lands there and alerts, rather than being dropped.
- Regulatory: mandatory-field validation that **blocks generation** and names what is missing; version store; submit-or-store decision; gateway reference capture.

## Open questions — do not guess these

These are unresolved with the partner. Build the mechanism, leave the specifics configurable, and flag them rather than inventing answers.

| Question | Effect on build |
|---|---|
| **CDSCO XML schema** — no schema, mandatory-field list, validation rules, sample accepted file, or acknowledgement format has been supplied | Build the validation *mechanism* and the generation pipeline. The field list must be data-driven, not hardcoded. Ship it labelled "prototype — not a validated CDSCO submission". |
| **What "invalid" means** — 7 candidate readings in feedback Section 8 | Keep exception causes itemised separately (full text unavailable / insufficient information / parse error / search failed). They can be regrouped in one place once defined. Do not collapse them into one bucket. |
| **Which gateway** — CDSCO portal, PvPI, internal safety system, or third-party | Leave as an unset dropdown. The app never submits automatically regardless (Step 14). |
| **Alert channels for pilot** | Build in-app and email only. Draw the rest as later-phase. |
| **User assignment model** — one user for all, one per product, or primary + backup | `responsible_user_id` on Product supports per-product. Do not build escalation chains yet. |
| **The four pilot products** | Wireframe brand names (Glucomet, Lipicor, Amoxiclan, Levracet) are placeholders. |

## Non-negotiables (from AGENTS.md, still binding)

- No PubMed HTML scraping or Embase scraping — E-utilities API only.
- No auto-finalising an ICSR without human action. No auto-submission to any regulator (Step 14 is explicit).
- No hard deletes — status + archive + recall.
- Keep screening dimensions separate (product / event / ICSR), not one opaque score.
- Log model/prompt/ruleset/threshold versions on every score.
- Not a GxP-validated system. Keep the pilot banner.

## Definition of done

Walk the pilot story end to end: configure a product → scheduled search runs → articles ingested and classified → assigned user alerted → user opens the detection report → records a decision → tags a potential signal → prepares a regulatory output → decides submit or store → records the gateway reference → the whole path is visible in the audit trail.
