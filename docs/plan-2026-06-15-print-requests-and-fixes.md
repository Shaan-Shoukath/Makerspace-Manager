# Implementation Plan v2 — Public 3D Print Requests + Handout/QR/Transfer/Spool fixes (2026-06-15)

Revised after Codex Stage-1 review (NEEDS_REVISION → addressed below). Multi-tenant Django 5 + DRF
backend, React 18 + Vite + TS frontend. Files ≤200 LOC target / 300 hard ceiling, split via
`views_*`/`serializers_*` submodules + thin re-export barrels. All state-changing services emit
audit logs and route through the single-source workflow/availability modules. Makerspace scoping =
404-before-403. Every new route gets `@extend_schema`; OpenAPI snapshot + generated TS client
regenerated and kept in sync.

## Decisions (confirmed with user)
- 3D print requests: **PUBLIC** anonymous, mirroring the hardware-request public flow exactly.
- Direct handout: keep hard rule — Space Mgr + Inventory Mgr + Superadmin only; Guest Admin excluded.
- QR scanning: real in-browser camera scanner (native `BarcodeDetector`, zxing-wasm dynamic-import fallback).
- Transfer "errors": backend correct; fix is frontend UX + error surfacing.
- File storage: **printing-specific** presigned S3/MinIO helpers (NOT the staff-only evidence presign).

## Patterns Phase 6+ MUST mirror (from hardware_requests, verified by Codex)
- Public routes shaped `/public/<slug:makerspace_slug>/...` — `apps/hardware_requests/urls.py`.
- Makerspace resolution via `apps/makerspaces/lookup.py`.
- `permission_classes=[AllowAny]` + `ClientTierRateThrottle` + dedicated throttle scopes
  (`checkin_verify`, a new `print_request_submit`, `request_status`) — `hardware_requests/public_views.py`.
- HMAC/publishable-key handling via `apps/inventory/middleware.py` — **no HMAC secret in the browser**;
  browser uses publishable key/origin; server clients may HMAC-sign.
- Check-In identity via `apps/checkin/client.py`; requester via the shadow-user
  `get_or_create_requester(...)` pattern in `hardware_requests/request_workflow.py`
  (scoped by `external_checkin_user_id`). **`PrintRequest.requester` stays non-nullable.**
- Honeypot: `_honeypot_filled`-style check BEFORE serializer validation, returns decoy success
  with no row created — `hardware_requests/public_views.py`.
- Status lookup: verify Check-In, then filter by `requester__external_checkin_user_id` AND the
  request's `public_token`; serializer omits PII + object keys; strict public-status allowlist.

---

## PHASE 1 — Fix broken QR-label image (bug)
**Root cause (confirmed):** `backend/apps/boxes/api_views.py:212` returns `segno.make(payload).svg_inline(scale=5)`
(no SVG namespace) → `frontend/src/features/staff/panels/QrImage.tsx:14` uses it as
`data:image/svg+xml;utf8,<encoded>` `<img src>` → invalid standalone SVG → broken.
- Backend: return a namespaced standalone SVG — reuse the captioned-SVG renderer in
  `apps/operations/qr_zip.py` so print view + ZIP share one renderer (or pass segno args that emit `xmlns`).
- Frontend `QrImage.tsx`: build data-URI as `data:image/svg+xml;base64,<utf8-safe base64>`.
- Verify: label renders in console; ZIP download unaffected. No migration.

## PHASE 2 — Stock transfer UX + error surfacing (bug)
Backend verified correct (intra relocate 201, cross 201, asset-cross 400-by-design). Failure =
user picks a Source container but products have `box_id=None` → 400 "Product is not in the source
container"; DRF field errors not surfaced cleanly. **Note:** cross-makerspace path ignores
`source_container` entirely — document this in the UI.
- `StockTransferPanel.tsx` + `StockTransferTable.tsx`: parse + render DRF 400 field errors
  (`{field:[msg]}`/`{field:msg}`) inline; clarify source-container semantics; when cross-makerspace,
  hide/grey the source-container control and show the "source ignored" note.
- Verify live with user (intra + cross succeed; asset-cross + unassigned-box show clear messages).
  No backend change unless the user's live repro reveals a real server bug.

## PHASE 3 — Filament spool delete (feature)
`views_spools.py:49` is `RetrieveUpdateAPIView` (no DELETE). **FK reality:**
`PrintRequest.filament_spool` is `on_delete=SET_NULL` (`printing/models.py:171`) — a naked delete
would silently null historical links.
- Backend: add `delete()` (or `RetrieveUpdateDestroyAPIView`) with an explicit guard:
  `if PrintRequest.objects.filter(filament_spool=spool).exists(): return 409` (message: deactivate
  instead, preserves history); else hard-delete + audit. Same active-status + `MANAGE_PRINTING` +
  module guard + 404-before-403 scoping as the existing detail view.
- Frontend `PrintingPanelParts.tsx` SpoolRow: add "Delete" (confirm dialog); on 409 show the hint.
- `@extend_schema` for DELETE (200/409). Regen snapshot + client. Tests: referenced→409, unreferenced→deleted.

## PHASE 4 — Direct handout: multi-item UI + camera QR scanner (feature)
Backend already accepts `items[]` + `qr_payloads[]` (no backend change). **Path correction:** file is
`frontend/src/features/staff/DirectLoans.tsx` (NOT under `panels/`).
- Multi-item rows (product + qty), like the transfer line rows.
- New reusable `frontend/src/components/ui/QrScanner.tsx`: `BarcodeDetector` when available, else
  dynamic-import zxing-wasm; on decode POST `/admin/qr/resolve`, append resolved product/asset to the
  loan list (asset-tracked → scanned asset payload; quantity → product line). Dedupe scans.
- RBAC unchanged. Verify: multi-item handout issues; scanning an asset QR adds + issues it as ISSUED.

## PHASE 5 — Print request data model + printing storage (backend, migration)
- `PrintRequest`: add `public_token` (UUID, unique, db_index, default uuid4), `project_brief` (Text),
  `contact_email`, `contact_phone`. Keep `requester` **non-nullable** (Check-In shadow user).
- New `PrintRequestFile` with an explicit **upload→attach lifecycle** (solves pre-submit uploads):
  fields `print_request` FK **nullable** (set only on attach), `makerspace` FK, `kind=[stl|screenshot]`,
  `object_key` (server-generated), `content_type`, `size_bytes`, `owner_checkin_user_id` (the verified
  Check-In identity that created the upload), `created_at`, `attached_at` nullable. A row is created at
  presign time with `print_request=null`/`attached_at=null`; submit performs a **one-time attach**
  (sets `print_request` + `attached_at`) only if the row's `owner_checkin_user_id` matches the verified
  requester AND `attached_at IS NULL` AND `makerspace` matches AND `object_exists`+size verify pass —
  otherwise the row is rejected (foreign/unattached/reused). After attach the row is immutable.
  Unattached rows are reclaimable by a later GC command (out of scope here; document only).
- New printing storage module `apps/printing/storage.py` + settings: `PRINT_UPLOAD_MAX_BYTES`,
  `PRINT_ALLOWED_MODEL_MIME`/ext (STL/3MF/STEP/STP/OBJ), `PRINT_ALLOWED_SCREENSHOT_MIME` (PNG/JPG/WEBP/PDF).
  **Server-generated** object keys under a `print/` prefix; reuse the S3/MinIO client + `object_exists`
  from evidence storage helpers but with printing-specific allowlists/limits (do NOT widen evidence).
- Migration(s) for the new fields/model + `public_token` backfill. Existing single
  `model_file`/`estimate_screenshot`/`preview_screenshot` retained (no destructive backfill); new uploads
  use `PrintRequestFile`. Tests: model + storage key generation + allowlist rejects bad MIME/size.

## PHASE 6 — Public print API + security (backend)
Mirror hardware_requests exactly (see "Patterns" above).
- `printing/public_views.py` + `public_serializers.py` + `public_urls.py` mounted under
  `/api/v1/printing/public/<slug:makerspace_slug>/...`.
- Endpoints: (a) Check-In verify; (b) **presigned upload** for STL/screenshot — `AllowAny` but
  **Check-In-verified + makerspace + `printing` module scoped**: server generates the object key, creates
  a `PrintRequestFile` staging row (`print_request=null`, `owner_checkin_user_id`=verified id), returns
  the presigned POST + the row id. MIME/size bound; (c) submit (honeypot-before-serializer, decoy
  success, Check-In shadow requester via `get_or_create_requester`, creates the request, then **attaches**
  each referenced `PrintRequestFile` id via the one-time attach rule from Phase 5 — owner match +
  unattached + makerspace match + `object_exists`/size verify; foreign/reused/unattached ids → reject);
  (d) status lookup by `public_token` + `requester__external_checkin_user_id`, public-status allowlist,
  **no PII, no object keys, no enumeration**.
- **Submit is atomic:** the whole submit runs in one `transaction.atomic()` block; staged
  `PrintRequestFile` ids are `select_for_update`-locked and validated/attached in the SAME transaction
  as `PrintRequest` creation, so any rejected foreign/reused/missing-object file rolls back the entire
  request (no partial request, no half-attached files).
- Throttles: new `print_request_submit` scope + reuse `checkin_verify`/`request_status`. Module guard `printing`.
- Tests: happy submit, honeypot decoy, module-off 404, Check-In-down 503, presign scoping/forgery,
  status no-enumeration, cross-tenant isolation.

## PHASE 7 — Emails + status transitions (backend)
- `printing/emails.py` + templates: add submission-received + printing-started; keep accepted /
  completed("ready to collect") / rejected. Fail-safe per-makerspace SMTP (existing pattern).
  `workflow.py` remains the transition source of truth (row-locked + audited). Tests: each transition
  sends the right fail-safe email; SMTP failure never breaks the transition.

## PHASE 8 — Public frontend: request form + status tracker (frontend)
- "Request a 3D print" entry on the public makerspace page: Check-In verify → form (multi-STL upload,
  multi screenshot upload with progress via presigned endpoints, project brief, personal preferences,
  email, phone). Uses publishable/bootstrap config only (no HMAC secret).
- Public status page with stepper Requested → Accepted → Printing → Ready to collect (+ Rejected/Failed),
  via the `public_token` status endpoint.
- Regenerate generated client. No secret in browser; validate inputs client-side + rely on server.

## PHASE 9 — Staff/admin surface for new fields/files (backend serializer + frontend)
- Staff print serializers expose `project_brief`, contact fields, and `PrintRequestFile` rows as
  short-lived signed **view** URLs (staff-only, `MANAGE_PRINTING`, active status). Never raw object keys.
- `PrintingPanel`/parts: show brief, contact, downloadable STL(s) + screenshot(s) for managers.
  Tests: signed-view URL scoping; non-manager 403/404.

## PHASE 10 — OpenAPI + full validation + review + docs
- `@extend_schema` complete; regenerate `frontend/openapi-schema.json` + `src/generated/api.ts`; sync-diff check.
- Full `pytest`; frontend `tsc -b && vite build`.
- Codex Stage-4 background review; fix findings; re-run until clean.
- Update `CLAUDE.md` (public printing surface, `PrintRequestFile` + printing storage, `public_token`,
  spool delete, QR-label fix, camera scanner) + source map + hard-rules sections.

## Execution model
Phase-sequenced. Each phase: Claude writes per-file Codex prompts (Stage 2, `workspace-write`); Codex
implements; Claude verifies the diff against this plan and fixes small issues directly. Bug phases
(1, 2, 3) may run as parallel Codex agents; security-sensitive backend phases (5, 6, 7, 9) run focused
and individually. Commit only after user QA per gate.

## Risks / open items
- Public printing endpoints loosen today's login requirement — must replicate hardware-request posture
  exactly (HMAC/publishable, Check-In, honeypot, throttle, no enumeration). Highest-risk phase = 6.
- Upload lifecycle: presigned PUT/POST can overwrite a key until expiry (accepted Phase-3-evidence risk);
  record ETag/size on attach. No client-supplied keys; tie uploads to the verified Check-In identity.
- zxing-wasm bundle size: dynamic-import only when `BarcodeDetector` is absent.
- Spool delete: explicit 409-when-referenced guard chosen over SET_NULL nulling, to preserve audit lineage.
