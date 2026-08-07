# Phase 3/4 manual functional test

This is the human-run rehearsal for the partner-feedback MVP. The application
must keep the **Pilot — not GxP validated** banner visible. It never transmits a
regulatory file and implements in-app alerts only.

## Preconditions

- API: `http://127.0.0.1:8000`
- Web: `http://localhost:5173`
- Admin: `admin@litmon.local` / `admin123`
- Reviewer: `reviewer@litmon.local` / `reviewer123`
- PV lead: `pvlead@litmon.local` / `pvlead123`
- Use a bounded search (`max_fetch` 5–10) for the rehearsal.

## Main story

1. Log in as Admin and open **Products**. Select an existing monitored product
   or add one through **Product search**. Enter MAH and markets, confirm its INN
   and API tags, and assign the Reviewer as responsible user. Save and confirm
   the success message.
2. Open **Product search** and run a bounded PubMed search. Optionally create a
   daily or weekly schedule. In **Search & schedule**, confirm the run/schedule
   status and that the exception summary is visible.
3. Log in as the assigned Reviewer. Open **Alerts**, acknowledge the assignment
   alert, and confirm the read action removes it from the default unread view.
4. Open **My workspace**. Confirm folder counts, priority sorting, and the ten
   filters. Open an ingested article from Awaiting review or New alerts.
5. In the **Detection report**, confirm source, search date, search terms,
   article details, APIs, extraction fields, AI proposal, model/prompt versions,
   and audit history. Use **Print / save report** and confirm the navigation and
   form controls are absent from the printable document.
6. Enter a rationale, suspect product, adverse-event terms, the four ICSR
   criteria, and any controlled supporting-document reference. Record a human
   classification and save signal tags. Mark the report as a potential signal
   or record another review decision.
7. Log in as PV Lead. Open the same report and confirm the signal if appropriate.
   Confirmation must fail if there is no prior human decision; it must succeed
   after one exists.
8. Choose **Prepare for submission** or open **Submission & storage** and record
   an approved/retained decision with a required reason. Validation must name
   missing fields and block generation until PMID, suspect product, and adverse
   event are present.
9. Generate two versions and confirm both remain listed. Download either XML;
   verify the filename includes the article and version. The surrounding UI and
   stored package metadata must continue to label it as a prototype, not a
   validated CDSCO submission.
10. For a local workflow test only, choose an explicitly test/internal gateway
    and record a reference such as `LOCAL-TEST-001`. This records manual evidence
    but sends nothing. Alternatively choose **Retain internally** and verify the
    report moves to Not for submission.
11. Open **Audit trail**. Filter by article/action/actor, verify the complete
    sequence, then export the filtered CSV.
12. Open **Dashboard** and drill into totals, screened/relevant/irrelevant,
    signal, exception, submission, overdue, product, API, source, alert-priority,
    and search-completion measures.

## Negative-path checks

- Try enabling a literature source without a configured retrieval path. It must
  be rejected rather than implying unsupported coverage.
- Import a record with no abstract. It must remain in **Invalid / failed** with
  an itemised `full_text_unavailable` cause and an in-app alert.
- Pause or remove a product's active search string, then run its due schedule.
  The schedule must record failure and create an in-app `search_failed` alert.
- Leave an assigned review inside the 24-hour warning window or past its SLA,
  then run the SLA check. Due-soon and overdue alerts must deduplicate.
- Try recording a manual submission before generating a validated version. The
  API/UI must block it.
