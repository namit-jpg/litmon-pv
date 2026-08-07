# End-to-end browser test plan for Computer Use agents

## Purpose and outcome

Use this plan to verify the complete **partner-feedback MVP** through the
running browser UI. The test is successful only when an agent can trace one
literature record from product setup through search, review, regulatory-output
prototype and audit evidence without a direct regulatory submission.

This is a pilot/prototype test, **not a GxP validation protocol**. It must not
be represented as a validated CDSCO submission test.

## Scope

The plan covers the implemented MVP workflow:

```text
Admin configures product
  -> bounded PubMed search / scheduled-search visibility
  -> reviewer receives and acknowledges in-app work
  -> reviewer classifies, tags and decides
  -> PV Lead confirms a signal
  -> reviewer prepares a prototype regulatory version
  -> reviewer records an internal test gateway reference or retains internally
  -> audit trail and dashboard expose the complete outcome
```

It also covers the high-value guardrails: unsupported source rejection,
missing-abstract exception handling, and mandatory-field/submission blocking.

Out of scope: outbound email/SMS/chat notifications, a real regulatory-gateway
upload, payment, production data, real patient data, and confirmation that the
prototype XML conforms to an official CDSCO schema.

## Safety rules

1. Use only the local application endpoints and the supplied local test
   accounts. Do not enter a real patient, customer, company, or regulatory
   credential.
2. Keep PubMed searches bounded to `max_fetch` 5–10. Do not run a broad search
   or change a production-like schedule.
3. Do not choose a real external gateway or submit/upload a regulatory file.
   If the UI requires a gateway reference, select an explicitly test/internal
   gateway and use `LOCAL-TEST-001` (or another clearly test-only value).
4. Do not delete or overwrite existing products, literature records, reports,
   alerts, audit records, or schedules. Prefer an existing seeded product. If a
   temporary product is required, name it `E2E Test <YYYYMMDD-HHMM>` and leave
   it inactive at the end; do not delete it.
5. The application must continue to show the `Pilot — not GxP validated`
   banner. Record a failure if it is absent from the tested user screens.

## Required environment

Start from the repository root. This plan assumes a local seeded database and
deterministic scoring where available.

```zsh
# Terminal 1
cd apps/api
source .venv/bin/activate
export PYTHONPATH=.
export LLM_MOCK=true
python -m app.bootstrap
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```zsh
# Terminal 2
cd apps/web
npm run dev
```

Before browser testing, confirm the following read-only endpoints respond
successfully:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/health/ready
http://localhost:5173
```

Use these seeded local accounts:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@litmon.local` | `admin123` |
| Reviewer | `reviewer@litmon.local` | `reviewer123` |
| PV Lead | `pvlead@litmon.local` | `pvlead123` |

If bootstrap would overwrite an existing working database, stop and ask the
test owner whether a fresh local database is intended. Do not reset data as an
implicit test-setup step.

## Computer Use operating procedure

Use the local browser with accessibility-tree locators wherever possible.

1. Inspect the latest page state before every interaction.
2. Prefer a visible label, role, text, or accessibility-tree element over
   screen coordinates. Re-read the page state after every navigation, save,
   login/logout, modal action, or asynchronous search.
3. Use screenshots when the tree does not reveal charts, selected filter state,
   printed-report layout, toast messages, or other visual-only state.
4. Never reuse an element index after the page changes. Re-resolve it from the
   newest browser state.
5. Wait only for observable completion: a success toast, a changed status, a
   new table row, an enabled button, or the absence of a loading indicator.
   Do not use arbitrary long sleeps.
6. If a step cannot be completed because a label or path differs, capture the
   page state and screenshot, record the exact visible text, then proceed to an
   independent test case where safe. Do not guess at hidden controls.
7. At the end of each test case, write one result line containing the case ID,
   pass/fail/blocked status, target record/product, and evidence filenames or
   URLs. A failure must include expected behaviour, observed behaviour, and the
   exact step that failed.

## Evidence to capture

Create a dated evidence folder outside version-controlled source directories,
for example `../litmon-pv-e2e-evidence-YYYYMMDD-HHMM/`. Capture only
non-sensitive local test evidence:

- Screenshot of the login/dashboard banner and each material state transition.
- Screenshot or downloaded file for the printable detection report and one
  prototype XML version.
- Browser-visible success/error toast and validation text for every guardrail.
- Exported filtered audit CSV, if the UI provides it.
- A `results.md` summary with the test-case table below completed.

Do not add screenshots, downloaded XML/CSV, or local databases to git.

## Test data strategy

Use a seeded active product (normally Ibuprofen, Metformin, Amoxicillin, or
Atorvastatin) if it has an active search string and a reviewer can be assigned.
Choose one product and one ingested article and record their visible names/IDs
in the results summary. Preserve that same article for all role handoffs so the
audit trail is coherent.

Where a test requires a new article, use the smallest supported import/search
path and an obvious test marker in the title or notes. Do not use a live
regulatory report or patient information.

## Core end-to-end cases

### E2E-01 — Application readiness and pilot posture

**Role:** unauthenticated, then Admin  
**Goal:** establish a healthy, clearly labelled pilot test environment.

1. Open `http://localhost:5173`.
2. Confirm the login screen loads without a blank/error state.
3. Sign in as Admin.
4. Confirm the application shell loads and the pilot/not-GxP banner is visible.
5. Navigate to Dashboard and confirm it renders an operational metric or an
   explicit empty-state message, not an unhandled error.

**Pass:** Login succeeds, the banner is visible, and Dashboard is usable.

### E2E-02 — Product configuration and ownership

**Role:** Admin  
**Goal:** establish the monitored product and assigned reviewer used downstream.

1. Open **Products**.
2. Select an existing active seeded product. If none is suitable, create a
   temporary `E2E Test <timestamp>` product through **Product search**.
3. Confirm the product displays an INN/generic value and active ingredient/API
   information.
4. Set or confirm MAH and at least one market value.
5. Assign `reviewer@litmon.local` as the responsible user and save.
6. Confirm the UI displays a success message and the persisted values remain
   after a browser refresh.

**Pass:** A valid active product is configured and visibly assigned to the
Reviewer. Record its name and ID in `results.md`.

### E2E-03 — Source configuration guardrail

**Role:** Admin  
**Goal:** prove that unsupported literature coverage cannot be advertised.

1. Open **Literature sources**.
2. Identify an existing enabled PubMed source and record its visible retrieval
   path/provider state.
3. Attempt to enable a source without a configured retrieval path, using a
   test-only source or a non-destructive validation path offered by the UI.
4. Confirm the save/enable action is rejected and names the missing
   configuration; do not leave an unsupported source enabled.

**Pass:** The unsupported source cannot be enabled.  
**If the UI offers no safe validation path:** mark **blocked** and record the
page state; do not manufacture an invalid production-like source.

### E2E-04 — Bounded search and schedule visibility

**Role:** Admin  
**Goal:** get or confirm a traceable literature record without an unbounded run.

1. Open **Product search** for the E2E product.
2. Confirm the active search string is visible and identify the source as
   PubMed.
3. Run a search with `max_fetch` between 5 and 10.
4. Wait for a terminal run status, then record the run status, retrieved count,
   deduplicated count if displayed, and any exception summary.
5. Open **Search & schedule** and confirm the run appears. If a schedule is
   already configured, confirm its cadence/status. Do not create a recurring
   schedule unless the test owner specifically requested one.
6. Identify one ingested article in New alerts or Awaiting review and record it
   as the E2E article.

**Pass:** A bounded search/run is visible with terminal status and an article
is available to review.  
**Allowed alternative:** If PubMed is unavailable, use the application’s
supported local/CSV/PMID pilot import path with a small fixture and record the
fallback used.

### E2E-05 — Reviewer alert, workspace, and report inspection

**Role:** Reviewer  
**Goal:** validate the assigned-user operational flow.

1. Sign out of Admin and sign in as Reviewer.
2. Open **Alerts**. Locate the assignment, signal, exception, or pending-review
   alert related to the E2E article.
3. Mark it read and confirm it leaves the default unread view; verify the read
   action has a visible success state or persisted read state after refresh.
4. Open **My workspace**. Confirm the folder counts and the controls for
   product, ingredient/API, date, source, classification, signal status,
   submission status, assignee, priority, and review-status filtering.
5. Apply at least product and assignee filtering and confirm the E2E article is
   reachable, then clear the filters.
6. Open the article’s **Detection report** and confirm visible source, search
   date, search terms, article identity, product/API data, extracted fields,
   AI proposal, model/prompt/ruleset versions, and audit history.
7. Use **Print / save report**. Verify the print view hides application
   navigation and form controls. Cancel the browser print dialog unless saving
   a local PDF is explicitly supported and safe.

**Pass:** The reviewer can acknowledge work, locate the article, inspect the
required report details, and view a print-safe report.

### E2E-06 — Human review, classification, and signal tags

**Role:** Reviewer  
**Goal:** prove the human-in-the-loop state changes are persisted and auditable.

1. On the E2E Detection report, enter a test-only rationale.
2. Add/confirm a suspect product and adverse-event term appropriate to the
   article; use existing extracted values where possible.
3. Complete the four ICSR criteria deliberately. Record whether the UI gives a
   clear result when the criteria do not support a valid ICSR.
4. Save a human classification, preserving the displayed AI proposal.
5. Add a `Potential signal` tag and save.
6. Record a decision such as **Mark as a potential signal** or another valid
   test outcome. Do not choose a final regulatory submission action here.
7. Refresh and confirm the decision, classification, tags, rationale, and audit
   entry persisted.

**Pass:** Human decision data persists, the AI proposal remains distinguishable
from the human classification, and the audit trail reflects the action.

### E2E-07 — PV Lead confirmation permission and precondition

**Role:** PV Lead  
**Goal:** verify that confirmed signal status is controlled and cannot bypass a
human decision.

1. Sign in as PV Lead and open the E2E article.
2. If there is a separate article with no human decision, try its **Confirm
   signal** action and confirm it is blocked with an explanatory message.
3. On the reviewed E2E article, confirm the potential signal.
4. Refresh and verify confirmed state, actor, and time/audit history.

**Pass:** Confirmation without a prior human decision is blocked; confirmation
by PV Lead after a human decision succeeds.  
**If no safe unreviewed article is available:** run only the positive check and
mark the negative precondition check blocked, rather than undoing a decision.

### E2E-08 — Regulatory prototype validation, versioning, and safe gateway record

**Role:** Reviewer or PV Lead, according to UI permissions  
**Goal:** validate the manual, non-transmitting submission/storage workflow.

1. Open **Submission & storage** for the E2E article or choose **Prepare for
   submission** from the report.
2. Trigger validation before filling required fields if the UI safely permits.
   Confirm it names missing required data and blocks generation.
3. Ensure PMID/source identifier, suspect product, and adverse-event data are
   present. Choose an approved or retained decision and provide its required
   test-only reason.
4. Generate a prototype regulatory output. Confirm its visible labels say
   prototype/not validated CDSCO submission.
5. Generate a second version and confirm both versions remain listed with
   distinct version identifiers.
6. Download one XML file locally. Confirm its filename identifies the article
   and version. Do not upload it anywhere.
7. If testing the manual gateway record, select only an explicitly test/internal
   gateway and record `LOCAL-TEST-001`; confirm it merely records evidence and
   causes no external navigation or transmission. Otherwise select **Retain
   internally** and confirm the report moves to the non-submission state.

**Pass:** Missing required data prevents generation; two prototype versions can
be listed; download is local only; and the report is either retained or has a
test-only manual reference without an external submission.

### E2E-09 — Audit-trail integrity and dashboard drill-through

**Role:** PV Lead or Admin  
**Goal:** verify cross-screen traceability of the complete story.

1. Open **Audit trail**.
2. Filter by the E2E article, then by at least action and actor.
3. Verify the visible sequence includes, where exercised: search/ingest,
   assignment or alert acknowledgement, review/classification, signal tagging,
   PV Lead confirmation, prototype generation, and retain/manual reference.
4. Export the filtered audit CSV and store it only in the evidence directory.
5. Open **Dashboard** and confirm metrics/load states render normally.
6. Drill into at least three categories exercised by the E2E record (for
   example potential/confirmed signal, awaiting review, submission/retained,
   alerts, product, source, or search completion). Confirm each drill-through
   opens a filtered workspace/list whose visible filters match the selected
   metric.

**Pass:** Audit history is coherent and dashboard drill-through preserves the
expected operational context.

## Negative-path cases

Run these independently after the core story. Do not corrupt the E2E article
used above.

| ID | Scenario | Expected result |
|---|---|---|
| NEG-01 | Enable an unsupported literature source | UI rejects the action and names the missing retrieval configuration. |
| NEG-02 | Import/test a record with no abstract using the supported pilot import flow | It stays in **Invalid / failed** with an itemised `full_text_unavailable` cause and an in-app alert. |
| NEG-03 | Trigger a due schedule for a product with no active search string, only in an isolated test configuration | Search failure is recorded and an in-app `search_failed` alert is created. Restore the original configuration immediately. |
| NEG-04 | Run the SLA check against an eligible due-soon/overdue fixture | Due-soon/overdue alerts appear once and repeated checks do not create duplicates. |
| NEG-05 | Attempt manual submission before a validated/generated version exists | The UI blocks it and gives an actionable explanation. No external gateway is contacted. |

If an isolated fixture is not available for NEG-02 through NEG-04, mark the
case blocked. Do not alter retained pilot data merely to create a failure.

## Result template

Create `results.md` in the evidence directory using this table:

| Case | Status | Test product/article | Evidence | Notes / defect |
|---|---|---|---|---|
| E2E-01 | PASS / FAIL / BLOCKED | | | |
| E2E-02 | PASS / FAIL / BLOCKED | | | |
| E2E-03 | PASS / FAIL / BLOCKED | | | |
| E2E-04 | PASS / FAIL / BLOCKED | | | |
| E2E-05 | PASS / FAIL / BLOCKED | | | |
| E2E-06 | PASS / FAIL / BLOCKED | | | |
| E2E-07 | PASS / FAIL / BLOCKED | | | |
| E2E-08 | PASS / FAIL / BLOCKED | | | |
| E2E-09 | PASS / FAIL / BLOCKED | | | |
| NEG-01 | PASS / FAIL / BLOCKED | | | |
| NEG-02 | PASS / FAIL / BLOCKED | | | |
| NEG-03 | PASS / FAIL / BLOCKED | | | |
| NEG-04 | PASS / FAIL / BLOCKED | | | |
| NEG-05 | PASS / FAIL / BLOCKED | | | |

## Completion criteria

Report the run as passed only if:

- E2E-01 through E2E-09 all pass, or any blocked case has a documented safe
  environmental reason and does not conceal a product failure.
- No test action sent data to a real regulatory gateway or asserted CDSCO
  compliance.
- The pilot/not-GxP posture stayed visible and all regulatory outputs remained
  explicitly labelled as prototypes.
- The evidence folder contains the completed results table, material-state
  screenshots, one report/print-view evidence item, one prototype XML evidence
  item, and audit evidence where the export control is available.
- Any defect is recorded with reproducible UI steps, expected versus observed
  result, screenshot/page-state evidence, test account role, and the
  product/article identifier.

## Related project material

- [Phase 3/4 manual functional test](phase3_4_manual_test.md) — source human
  rehearsal steps.
- [Pilot runbook](pilot_runbook.md) — daily operation, failure handling, and
  pilot controls.
- [MVP build brief](MVP_BUILD_BRIEF.md) — current scope, open questions, and
  explicit prototype limitations.
- [Agent guide](AGENTS.md) — repository conventions and non-negotiables.
