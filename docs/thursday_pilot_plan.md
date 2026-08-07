# Thursday pilot completion plan — historical snapshot

> **Superseded for the current partner-feedback MVP.** This document records
> the 6 August assignment-routing demo plan. For the current implemented scope,
> read [MVP_BUILD_BRIEF.md](MVP_BUILD_BRIEF.md), [AGENTS.md](AGENTS.md), and the
> user-owned [phase3_4_manual_test.md](phase3_4_manual_test.md). Do not treat
> the dated actions or seeded product examples below as current pilot data.

Target demo: Thursday, 6 August 2026.

## Pilot outcome

Demonstrate a human-in-the-loop literature-monitoring workflow in which:

1. A product has a responsible PV reviewer.
2. PubMed or demo literature is screened and routed.
3. Reviewable articles are automatically assigned to that reviewer.
4. The reviewer sees the item in **My Work** and receives an in-app alert.
5. The reviewer can mark an article as a potential signal.
6. A senior reviewer or PV lead can confirm the signal.
7. The dashboard reflects assignment, signal, ICSR, overdue, and product counts.
8. New work routes like a small Service Cloud Omni queue: the product's
   primary reviewer is preferred when Available and below capacity; otherwise
   the least-loaded available reviewer receives it; if everyone is Busy,
   Offline, or at capacity, it remains unassigned in the triage queue.
9. Existing ICSR review, audit, archive, and export behavior remains available.

## Scope locked for Thursday

### Included

- One primary reviewer per product.
- Automatic assignment of non-auto-cleared articles.
- Reassignment of open work when the product reviewer changes.
- My Work and All Work views.
- Product and signal filters.
- Potential, confirmed, and rejected signal states.
- Human-only signal confirmation.
- Persistent per-user in-app alerts.
- Reviewer presence and capacity controls for the Omni-style routing demo.
- Alerts for assignments, signal changes, failed searches, and SLA breaches.
- Dashboard summary with drill-through links.
- Four-product configuration using the existing product APIs.
- Product-scoped PMID deduplication so one article can create work for multiple products.
- Existing PubMed, mock scoring, ICSR review, archive, audit, and exports.

### Seeded product configuration

All four products route to the single demo reviewer, `Reviewer One`
(`reviewer@litmon.local`). The values below are representative pilot search
strategies and should be validated by the PV subject-matter owner before any
real monitoring use.

| Product / API | Brands | Synonyms | Starter PubMed query |
|---|---|---|---|
| Ibuprofen | Advil, Motrin, Nurofen, Brufen | ibuprofen; 2-(4-isobutylphenyl)propionic acid; isobutylphenylpropionic acid | `(ibuprofen OR Advil OR Motrin OR Nurofen OR Brufen) AND (adverse OR toxicity OR safety OR "case report" OR interaction OR pregnancy OR overdose)` |
| Metformin | Glucophage, Fortamet, Riomet | metformin; metformin hydrochloride; dimethylbiguanide | `(metformin OR Glucophage OR Fortamet OR Riomet) AND (adverse OR toxicity OR safety OR "case report" OR lactic acidosis OR interaction OR pregnancy)` |
| Amoxicillin | Amoxil, Moxatag, Trimox | amoxicillin; amoxycillin; amoxicillin trihydrate | `(amoxicillin OR Amoxil OR Moxatag OR Trimox) AND (adverse OR allergy OR anaphylaxis OR toxicity OR safety OR "case report" OR interaction OR pregnancy)` |
| Atorvastatin | Lipitor, Sortis, Torvast | atorvastatin; atorvastatin calcium; statin | `(atorvastatin OR Lipitor OR Sortis OR Torvast) AND (adverse OR myopathy OR rhabdomyolysis OR toxicity OR safety OR "case report" OR interaction OR pregnancy)` |

### Explicitly deferred

- SMS, WhatsApp, Teams, Slack, and push delivery.
- Direct regulatory gateway integration.
- Production security hardening.
- Formal GxP validation.
- Full multi-tenant architecture.
- Cross-article statistical signal analytics.
- A full detection-report redesign.
- MedDRA and WHO-DD coding, and E2B(R3) HL7 v3 output. The CDSCO export is
  E2B(R2)-shaped pilot output and is not a validated regulatory submission.

## Day 1: functional vertical slice

- [x] Add primary reviewer to products.
- [x] Backfill the demo reviewer and existing open work through Alembic.
- [x] Automatically assign newly screened work.
- [x] Add signal states and human review actions.
- [x] Add persistent per-user alerts and read/unread behavior.
- [x] Add dashboard, My Work, signal filters, and Alerts bar.
- [x] Add presence/capacity-aware assignment with an unassigned fallback queue.
- [x] Add focused tests and pass the frontend production build.
- [x] Scope PMID deduplication per product for the four-product pilot.

## Day 2: demo preparation

1. Configure the four real or representative pilot products.
2. Set each product's primary reviewer in **Admin -> Product assignment**.
3. Add or verify one active PubMed query per product.
4. Run one small live PubMed search per product and retain demo seed data as backup.
5. Review labels, product names, and dashboard counts with the presentation owner.
6. Keep the demo reviewer Available; switch to Busy briefly to show routing
   fallback and the unassigned triage state.
7. Rehearse the demo flow below twice on the actual presentation machine.
8. Freeze feature work after the successful rehearsal; fix only demo-blocking defects.

## Thursday demo script

1. Log in as Admin.
2. Open **Admin -> Product assignment** and show the responsible reviewer.
3. Run **Seed demo articles** or a prepared PubMed search.
4. Log in as the assigned reviewer.
5. Open the Alerts bar and select a new assignment.
6. Show the AI assessment, evidence tags, queue, and SLA.
7. Enter a rationale and select **Mark potential signal**.
8. Return to **PV Dashboard** and show the potential-signal count.
9. Log in as PV Lead or Senior Reviewer and select **Confirm signal**.
10. Show the decision history and audit trail.
11. Briefly show the existing ICSR decision and export path.

## Demo acceptance checklist

- [ ] Frontend build succeeds.
- [ ] Backend tests pass.
- [ ] Fresh database migrates and bootstraps successfully.
- [ ] Each configured product has a primary reviewer.
- [ ] Seed/search produces assigned My Work items.
- [ ] Assignment alerts open the correct article.
- [ ] Potential-signal action updates the dashboard.
- [ ] Reviewer cannot confirm a signal; senior/PV lead can.
- [ ] Alert read and mark-all-read behavior works.
- [ ] Existing ICSR review and export still work.
- [ ] Presentation machine has a known-good offline demo path.

## Rollback and demo safety

- Back up the pilot SQLite database before rehearsal.
- Keep `LLM_MOCK=true` as the guaranteed offline path.
- Do not depend on live PubMed or a live LLM during the core demo.
- Use live PubMed only as an optional proof point after the deterministic flow.
- Keep the demo credentials and seeded article path available.
