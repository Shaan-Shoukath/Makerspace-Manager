# Plan — Superadmin Django-admin monitoring surfaces (2026-06-15)

## Goal
Let the superadmin **monitor** QR + evidence + print artifacts directly in the Django admin
(`/control/`), mirroring what the React staff console shows. **Read-only / view+download only —
no new mutations, no new RBAC, no migrations.** All four surfaces reuse existing services.

User-confirmed scope (all four), inline thumbnails + click-through links.

## Reused services (no new business logic)
- `apps.operations.qr_zip.build_batch_zip(batch) -> bytes` — QR batch ZIP.
- `apps.boxes.qr_render.render_qr_label_svg(payload, label) -> str` — captioned standalone SVG
  (embeds a PNG **data-URI**, already allowed by global CSP `img-src 'data:'`).
- `apps.evidence.storage.presigned_get_url(object_key) -> str` — short-lived signed GET for photos.
- `apps.printing.storage.print_get_url(object_key) -> str` — short-lived signed GET for print files.

## Changes (file by file)

### 1. `backend/apps/operations/admin.py` — `QrPrintBatchAdmin`
- Add admin action `download_zip_selected` alongside `mark_printed_selected` (both in `actions`):
  if `queryset.count() == 1`, **return** `HttpResponse(build_batch_zip(batch),
  content_type="application/zip")` with `Content-Disposition: attachment; filename="qr-batch-<id>.zip"`
  (same response shape as `views_qr_batches.py:99`). If `!= 1`, `message_user` ERROR ("select exactly
  one batch") and return None. Superuser-only unchanged.

### 2. `backend/apps/boxes/admin.py` — `QrCodeAdmin`
- Add readonly `qr_preview(obj)` → `mark_safe(render_qr_label_svg(obj.payload))`; add to `readonly_fields`.
  (Box already has this pattern.)

### 3. `backend/apps/inventory/admin.py` — `InventoryAssetAdmin`
- Add readonly `qr_preview(obj)` → reverse-lookup the asset's **active, same-makerspace** `QrCode`:
  `QrCode.objects.filter(target_type=QrCode.TargetType.ASSET, target_id=obj.pk,
  makerspace=obj.makerspace, status=QrCode.Status.ACTIVE).first()` (TargetType.ASSET == `"asset"`,
  confirmed `boxes/models.py:114`). If found render `render_qr_label_svg(qr.payload, obj.asset_tag)`,
  else "(no active QR)". A revoked QR must NOT be previewed. Add to `readonly_fields`.

### 4. `backend/apps/evidence/admin.py` — `EvidencePhotoAdmin`
- Add readonly `photo_preview(obj)`: `url = presigned_get_url(obj.object_key)`; render via
  **`format_html`** (never broad `mark_safe` around the interpolated URL) an inline
  `<img src=url style="max-height:320px">` + an "Open full image" anchor. Add to `readonly_fields`.
  Add a small thumbnail method to `list_display`. Stays fully read-only (add/change/delete already False).
  Guard: if `object_key` empty or storage misconfigured/raises, show plain text (never 500 the changelist).

### 5. `backend/apps/printing/admin_requests.py` — `PrintRequestAdmin`
- Add readonly `files_preview(obj)`: iterate attached `PrintRequestFile` rows; for each build
  `print_get_url(f.object_key)`. **PrintRequestFile has no original-filename field** — synthesize a
  label from `kind` + `id` (+ short `object_key` tail) and show `size_bytes`. Inline `<img>` thumbnail
  **only when `content_type.startswith("image/")`**; otherwise (STL/model, and PDF "screenshots") an
  "Open / Download" link. Build markup with **`format_html` / `format_html_join`** (no broad
  `mark_safe`). `PrintRequestAdmin` has an explicit `fields` tuple (`admin_requests.py:27`), so add
  `files_preview` to **both `fields` and `readonly_fields`**. Read-only.

### 6. `backend/config/admin_access.py` — `AdminCspEvalMiddleware`
- Extend the existing per-`/control/` `_csp_update` (which already appends `'unsafe-eval'` to
  `script-src`) to **also** append the `AWS_S3_PUBLIC_ENDPOINT_URL` **origin** to `img-src`, so inline
  MinIO/S3 thumbnails load. In django-csp 4, `_csp_update` **appends** to the configured directive, so
  this adds to the global `["'self'", "data:", swagger_cdn]` rather than replacing it (verified by
  Codex). **Only** for `/control/` responses — never touch the global `CONTENT_SECURITY_POLICY`, so
  public/API/docs CSP is unchanged.
- Derive the origin with `urlsplit(settings.AWS_S3_PUBLIC_ENDPOINT_URL)` and add **only**
  `f"{scheme}://{netloc}"` — no path/query/object key. If `AWS_S3_PUBLIC_ENDPOINT_URL` unset/blank,
  no-op (links still work; inline images just won't — acceptable). QR data-URI SVGs already covered by
  global `img-src 'data:'` (no change needed).

## Risks / notes
- **CSP is the load-bearing change** — without the `img-src` origin add, evidence/print thumbnails are
  silently blocked. Scope strictly to `/control/`; do not widen the global policy.
- Signed URLs are short-lived (rendered at page-load). If the superadmin leaves a detail page open past
  expiry, images 404 on a later reload — acceptable for a monitoring view.
- ZIP action returns a file response from a multi-select changelist action — must handle the
  single-batch case and message clearly otherwise.
- All views stay `SuperuserOnlyModelAdmin` + read-only. No migrations. No OpenAPI change (admin is not
  part of the REST surface).
- Object keys are identifiers, not secrets (existing Phase-3 convention) — privacy via private bucket +
  short-lived signed URLs, unchanged.

## Tests (`backend/tests/`)
- QrPrintBatch `download_zip_selected` returns `application/zip` for one batch; errors for multi-select.
- `/control/` response CSP header includes the S3 public origin in `img-src`; a non-`/control/` response
  does not (global policy intact).
- Smoke: EvidencePhoto + InventoryAsset + QrCode + PrintRequest change pages render 200 for a superuser
  (no 500 from preview methods), incl. the empty-object_key / no-QR fallbacks.

## Out of scope
Issue/return handover, camera scanning, direct loans, reports/ledger dashboards — remain React-only.
This adds **monitoring/visibility** only.
