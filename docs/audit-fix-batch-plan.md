# Audit Fix Batch — Implementation Plan (rev 2)

Fixes the H/M/L findings from the Claude(×7)+Codex audit. Branch: `fix/audit-findings-batch`
(merge to `main` when clean). Execution: **parallel Codex subagents on file-disjoint findings
(source AND test files) within each phase; sequential where files or domain logic overlap.**
Claude verifies every diff. Commit per green phase. Full backend `pytest` + frontend `tsc`/build
must stay green at each phase boundary.

User decisions baked in:
- M4 → validate AVAILABLE asset count at accept (fail fast); no partial-accept feature.
- M5 → relabel/clarify reports as estimate-based; no actual-grams input; no response-key renames.
- M8 → poll real status while `status==="printing"` (refetchInterval), stop at terminal.
- L4 → mirror `rbac.hide_from_superadmin` on evidence detail.
- L2 → claim-row-first idempotency + exclude archived/hidden makerspaces.
- Skip documented accepted risks: L8 (PUT oversized/overwrite) and status-by-email enumeration.

Revisions from Codex Stage-1 review (rev 1 → rev 2) are marked **[R#]** below.

---

## Phase 0 — Branch
`git checkout -b fix/audit-findings-batch` off current `main`.

---

## Phase 1 — Security (backend). 3 file-disjoint Codex agents in parallel.

**1A — H3 + M12 · `direct_loan_views.py`, `permissions.py` · tests `test_admin_direct_loans.py`**
- **H3 (list / create / verify):** these take `makerspace_id` in the URL, so add a permission
  class that checks `_active_authenticated` + `staff_origin_scope_allows(request, view)` +
  `rbac.makerspaces_for_action(ISSUE_DIRECT_LOAN)` (model it on the existing classes in
  `permissions.py`). Apply via `permission_classes`. Keep the existing `_require(...)` per-makerspace
  `rbac.can` check (defense in depth).
- **M12 (return, global pk) — [R1] do the scoping IN THE VIEW, not via an object-origin permission.**
  `origin_scope._MODEL_LOOKUPS` already maps `direct-loan-return` to a global `PublicToolLoan` pk
  lookup, so a `staff_origin_scope_allows`-based permission would 403 before the view body and
  defeat 404-before-403; and origin-less callers would still hit the leaky global fetch. Instead, in
  `DirectLoanReturnView.post`:
  1. `allowed = rbac.makerspaces_for_action(user, RETURN_REQUEST)` (handle the `rbac.ALL` sentinel —
     no `__in` filter when ALL).
  2. If an origin scope is present (`origin_scoped_makerspace_id(request) is not None`), intersect
     `allowed` with `{origin_scope}` (an origin-less server/test request keeps the membership scope).
  3. `loan = get_object_or_404(PublicToolLoan.objects.filter(source=ADMIN_DIRECT, makerspace_id∈allowed), pk=pk)`
     → both nonexistent AND out-of-scope ids return a uniform 404 (no enumeration oracle).
  4. Keep `_require(user, RETURN_REQUEST, loan.makerspace_id)` after the fetch (defense in depth).
  Permission class for the return view: active-staff + has-RETURN_REQUEST-somewhere (NO object-origin
  resolution — the in-view intersection owns the origin boundary).
- Tests: origin-less request still works (membership fallback); wrong staff-origin browser request
  rejected; cross-tenant / nonexistent return pk → 404 (not 403/200).

**1B — L3 + L5 · `accounts/rbac.py`, `admin_api/views_users.py`, `admin_api/serializers_users.py` ·
tests `test_rbac.py`/`test_hard_hide.py`**
- L3: route the hidden-makerspace membership tests at `rbac.py:147`, `:250` and `views_users.py:141`
  through the existing `_id_in(...)` helper (drop bare `in`/`int()`), so a str/int `makerspace_id`
  can't silently bypass the hard-hide.
- L5: run Django `validate_password` on the operator-supplied password in `StaffCreateSerializer`
  (or in the view before `make_password`) → 400 on failure.
- Tests: str-id hidden-block case; user-create with a weak password → 400.

**1C — L4 + L6 · `evidence/views.py`, `makerspaces/guards.py` · tests `test_evidence.py`**
([R4] merged 1C+1D — both land tests in `test_evidence.py`, so one agent owns that file.)
- L4: apply `rbac.hide_from_superadmin(self.request.user, qs, "makerspace_id")` in
  `EvidenceDetailView.get_queryset` (mirror `views_lending_history.py`).
- L6: `require_module` resolves via `get_object_or_404(Makerspace, ...)` (or callers catch
  `DoesNotExist`) so a bad `makerspace_id` is a clean 404, not a 500. Verify no caller depends on the
  raised `DoesNotExist`.
- Tests: superadmin cannot fetch evidence for a `superadmin_access_enabled=False` makerspace;
  evidence upload with a non-existent makerspace id → 404.

---

## Phase 2 — Concurrency & stock integrity (backend). 2 disjoint Codex agents in parallel.

**2A — H1 + L1 · `self_checkout_helpers.py`, `self_checkout_workflow.py`, `direct_loan_workflow.py` ·
tests `test_public_self_checkout.py`, `test_admin_direct_loans.py`** (one agent — shared locking
discipline, sequential within).
- H1: in `_return_request_items`, stop locking products via the `select_related` join. Collect
  `product_id`s, then lock distinct products once with
  `InventoryProduct.objects.select_for_update().filter(pk__in=ids).order_by("pk")` (match the
  `_checkout_box` pk-order discipline).
- **L1 — [R3] pragmatic locking fix, NO new table/migration.** The secondary QR ids live in JSON
  (`self_checkout_models.py:47`); a true DB uniqueness guarantee would need schema normalization +
  backfill + purge implications — out of scope. Instead: lock ALL scanned `QrCode` rows up front in
  pk order (the concrete race is the payload-order lock loop at `direct_loan_workflow.py:59`), and
  check `qr_ids__contains` membership under those locks so a bundled secondary QR can't be
  double-handed-out concurrently.
- Tests: deterministic return lock-order; bundled-QR double-handout rejected.

**2B — M3 + M4 · `inventory/availability.py`, `hardware_requests/request_workflow.py` ·
tests `test_handover_broken_reject.py`, `test_request_workflow.py`/`test_serialized_handout.py`**
([R2] M4's asset-count rule belongs in `availability.py` — the reservation-math owner — not in
`request_workflow.py`; one agent owns both files, sequential.)
- M3: in `availability.issue_items`, only set `item.needs_fix_quantity = broken` when
  `disposition != REJECT_REMOVE` (scrapped units must not be recorded on the to-be-fixed shelf).
- M4: add an availability helper (e.g. `assert_individual_assets_available(product, qty)`) and call
  it from `request_workflow.accept_request` for INDIVIDUAL-tracked products: require
  `count(AVAILABLE InventoryAsset) >= requested_quantity` before reserving; raise the workflow error
  → 409 on shortfall.
- Tests: REJECT_REMOVE leaves item `needs_fix_quantity` at 0; accept fails fast when too few
  AVAILABLE assets exist.

---

## Phase 3 — Reports / operations / printing-backend. 6 disjoint Codex agents in parallel.

**3A — M1 · `operations/reports.py` · tests `test_reports_ledger.py`** — **[R5] broaden, don't patch
only `_summary`.** Decision: archived (soft-deleted) products are excluded from ALL active
product-based report surfaces — both the stock surfaces AND the request-history/lending surfaces.
- Centralize `is_archived=False` in `_products()` (feeds `_summary` aggregates,
  `_product_quantity_rows`, `_recently_added`).
- **[R7 / Codex round 2] Also exclude archived from the `_items()`-backed surfaces**
  (`_taken_items`, `_most_lent`, `_top_borrowers`): add `product__is_archived=False` to `_items()`.
  An archived product is soft-deleted and should not appear in active analytics. (NOTE: the live
  "currently out / who holds it" recovery surface is the **Ledger** — `operations/ledger.py`, NOT
  touched here — so excluding archived from reports does not hide an outstanding loan that still
  needs recovery.)
- Tests assert summary quantity totals, product rows, AND most-lent/top-borrowers/taken-items all
  exclude archived products.

**3B — M2 · `operations/services_transfers.py` · tests `test_operations_api.py`** — add
`is_archived=False` to the cross-makerspace destination-product lookup (mirror
`services_transfer_splits.py`); create a fresh product when only an archived match exists.

**3C — M5 · `printing/reports.py`, `printing/reports_serializers.py` · tests
`test_printing_reports.py`** — clarify that completed-print filament figures are estimate-based via
`help_text`/comments + docs; document the two aggregation axes (`_printer_outcomes` vs spool delta).
Prefer NO response-key renames; if a clearly-named derived field is added, it triggers OpenAPI/TS
regen (Phase 5).

**3D — M11 · `printing/serializers_manual_logs.py` · tests `test_printing_manual_logs.py`** — declare
`grams_used` with explicit `max_digits=8, decimal_places=2` (+ sane `max_value`) so overlong input is
a clean 400, not a DB `DataError` 500. **Triggers OpenAPI/TS regen (Phase 5).**

**3E — L2 · `hardware_requests/services_return_reminders.py` · tests `test_return_reminders.py`,
`test_cron_return_reminders.py`** — claim each row first (atomic guarded
`update(... return_reminder_sent_at=now)` where `isnull=True`); only send the email on a successful
claim (rows-affected == 1); reset the flag if the send raises. Exclude
`rbac.archived_makerspace_ids()` + `superadmin_hidden_makerspace_ids()` from the queryset. Tests: no
duplicate send on retry; archived makerspace gets no reminder.

**3F — L7 · `admin_api/bulk_import.py`, `admin_api/serializers_bulk.py` · tests `test_admin_api.py`**
— cap `rows` length and reject oversized uploads at the serializer boundary (clean 400). **Triggers
OpenAPI/TS regen if the serializer shape changes (Phase 5).**

---

## Phase 4 — Frontend. 3 disjoint Codex agents in parallel. ([R4] regrouped to remove StaffApp.tsx /
login-state overlaps.)

**FE-1 — Auth & staff shell · `lib/api.ts`, `features/staff/StaffApp.tsx`,
`features/staff/StaffTabContent.tsx`, `features/staff/LoginPanel.tsx`,
`features/staff/panels/PrintingPanelParts.tsx`** (H2 + M6 + L9-login). One agent because
`login.isPending`, the 401→login redirect, and tab gating all live in / route through `StaffApp.tsx`.
- H2: on a 401 in `staffRequest`/`printingRequest`, call `refreshAccessToken()` once and replay; on
  refresh failure clear the token and route to login (via StaffApp auth state). Guard against retry loops.
- M6: gate tabs to the backend RBAC matrix — `users` → space_manager+superadmin; `direct` →
  EDIT_INVENTORY (exclude guest_admin); `scanner`/`qr`/`transfers` → appropriate manager roles;
  `audit` → `canViewAudit` (add the missing gate).
- L9-login: disable the Sign-in button while `login.isPending`.

**FE-2 — Public printing · `App.tsx`, `features/printing/PublicPrintRequestPage.tsx`,
`features/printing/PublicPrintRequestParts.tsx`** (M7 + M8).
- M7: add a `modules.has("printing")` guard on the public print page ("not enabled" card like the
  self-checkout page); direct-URL `/m/<slug>/print` no longer renders the form when disabled.
- M8: add a TanStack `refetchInterval` (~30s) that re-fetches real print status while
  `status==="printing"`, stopping at a terminal status; keep the client-side countdown as the
  between-poll estimate; handle `estimated_minutes===0` (don't hide the countdown on falsy 0).

**FE-3 — Staff panels · `features/staff/DirectLoans.tsx`, `features/staff/panels/StocktakePanel.tsx`,
`features/staff/panels/Queues.tsx`, `features/staff/panels/Inventory.tsx`,
`features/staff/panels/AuditLog.tsx`** (M9 + M10 + L9-stocktake/audit + L10 + L11). Independent files;
sequential within the agent.
- M9: after direct-loan issue, invalidate `["inventory-all", id]` + `["inventory", id]` (+ ledger);
  after stocktake apply, invalidate `["inventory", id]` (+ `["needs-fix-shelf", id]`).
- M10: replace the bare `queryClient.invalidateQueries()` in Queues with the specific affected keys.
- L11: surface clearly when assign-box succeeded but issue failed (visible/retryable half-step).
- L9: disable Start/Complete/Approve/Apply while pending + render `create.error` (StocktakePanel);
  render `logs.error` (AuditLog).
- L10: switch the bulk-QR toggle to `Promise.allSettled` with per-item outcome reporting (Inventory).

---

## Phase 5 — Verification & review gate
- Full backend `pytest` + frontend `tsc`/build green.
- **[R6] OpenAPI/TS regen is MANDATORY this batch** (not conditional): Phase 3D adds field
  constraints, 3F may change the bulk serializer, 3C may add a derived field, and 1A changes
  permission wiring. Run the OpenAPI snapshot + `frontend/src/generated/api.ts` regen and commit the
  diff; assert no unexpected drift.
- Stage 4: Codex `review` (background) on the branch diff; resolve findings, re-review until clean.
- Stage 5: user QA gate before merge to `main`.

## Risk notes
- Phase 1A is the only behavioral auth change; origin-less (server/test) requests must keep working
  via the membership fallback — `test_admin_direct_loans.py` is the guardrail.
- Parallel Codex agents are assigned strictly file-disjoint sets per phase **including test files**;
  intentional couplings (2A locking subsystem, 2B availability+accept, FE-1 auth shell) are kept
  within a single agent.
- M1 changes report semantics (archived excluded everywhere) — a deliberate, documented decision.
