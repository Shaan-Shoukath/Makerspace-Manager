# Phase 3 — Object storage + evidence infrastructure + append-only audit log

Stage-1 implementation plan (gated workflow). Builds on the uncommitted Phase 2 auth/RBAC foundation.
**Rev 2** — incorporates Codex plan-review fixes (EvidencePhoto lifecycle, DB-level immutability, presigned POST, boto3 Config, endpoint split, permission wiring).

## Goal

A **private, immutable** place to store issue/return evidence photos, and the **append-only audit log** that every state-changing workflow (phases 4–7) will write to. Plus two admin endpoints: one mints a short-lived signed **upload** authorization, one mints a short-lived signed **view** URL.

## Key decisions (resolved up front)

1. **`EvidencePhoto` carries NO `request` FK — ever.** (Codex fix #1.) It is a self-contained immutable blob record: `makerspace`, `evidence_type`, `object_key`, `uploaded_by`, `created_at`. In Phase 6 the **issue/return record links to it** (a FK on the issue side → `EvidencePhoto`), not the other way around. This removes the nullable-then-set mutation entirely and keeps the immutability invariant honest: an `EvidencePhoto` row is created once, with all fields set, and never updated.

2. **The upload endpoint creates the `EvidencePhoto` row at issuance**, inside a transaction, **only after** the presigned authorization is successfully generated. A row whose object is never uploaded is a harmless orphan; the view endpoint does a `HEAD` and returns 409 if the object is missing. (Codex notes: no durable row on presign failure.)

3. **Two new apps.** `apps/audit/` (AuditLog + `record()` service) and `apps/evidence/` (EvidencePhoto + storage helpers + 2 endpoints). `INSTALLED_APPS` entries `"apps.audit"`, `"apps.evidence"`. Matches the PRD deep-module boundaries and keeps `apiclients` focused on HMAC.

4. **MinIO for S3-compatible storage, dev = Django-on-host.** (Codex fix #5.) Phase 3 dev assumes the documented flow (only `db` in docker, Django via `runserver` on host), so a single `AWS_S3_ENDPOINT_URL=http://localhost:9000` is reachable by both backend and browser. We still add a **`AWS_S3_PUBLIC_ENDPOINT_URL`** seam (defaults to the endpoint) so a future dockerized backend can use `minio:9000` internally while signed URLs point the browser at `localhost:9000`. Running the backend container against MinIO is explicitly **out of scope** for this phase and noted in `.env.example` + `docker-compose`.

5. **Presigned POST, not PUT.** (Codex fix #3.) `generate_presigned_post` with **exact** Content-Type binding (Codex rev-3): `Fields={"Content-Type": content_type}` and `Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, EVIDENCE_MAX_BYTES]]`, where `content_type` is first validated server-side against `EVIDENCE_ALLOWED_MIME`. Exact binding (not `starts-with "image/"`) prevents smuggling `image/svg+xml`/`image/gif`. PUT cannot enforce max size; POST can.

6b. **Object-bytes mutability within the TTL — accepted risk.** A presigned POST for an `object_key` is reusable until expiry, so the authorized holder could re-POST/overwrite the bytes within the window. For Phase 3 this is an **accepted risk**: short TTL (300s) + a single authorized uploader per key. True byte-immutability (object lock/versioning) is deferred; **Phase 6's attach step will record the object ETag at attach time** so any later change is detectable. Documented in CLAUDE.md.

6. **Raw boto3 presign client is built explicitly** with `botocore.client.Config(signature_version="s3v4", s3={"addressing_style": "path"})` and the configured endpoint/keys/region. (Codex fix #4.) django-storages settings do **not** configure this client for us.

7. **URL-shaped, typed makerspace scoping.** (Codex note.) Routes are `/api/v1/admin/makerspaces/<int:makerspace_id>/uploads/evidence-url` (POST) and `/api/v1/admin/evidence/<int:pk>` (GET). The upload route gets the makerspace from a typed URL kwarg, so `HasMakerspaceAction`'s default `view.kwargs["makerspace_id"]` path works with no body-parsing fragility.

8. **New RBAC action `Action.UPLOAD_EVIDENCE`**, granted to both admin and guest-admin membership roles (guests perform issue/return, when evidence is captured).

## Files

### New — `apps/audit/`
- `__init__.py`, `apps.py` (`AuditConfig`, `name="apps.audit"`)
- `models.py` — `AuditLog`:
  - Fields: `actor` (FK `accounts.User`, `null=True`, `on_delete=PROTECT`; system actions = null), `action` (CharField), `target_type` (CharField, blank), `target_id` (CharField, blank — string fits int/UUID pks), `makerspace` (FK `makerspaces.Makerspace`, `null=True`, `on_delete=PROTECT`; null = global), `meta` (`JSONField`, default=dict), `created_at` (auto_now_add, indexed).
  - **App-level guard**: override `save()` → raise if `self.pk` already set; override `delete()` → raise. `Meta.ordering=["-created_at"]`, indexes on `(makerspace, created_at)` and `(action,)`.
- `migrations/0001_initial.py` (generated) **+ `0002_auditlog_append_only_triggers.py`** — (Codex fix #2) `RunSQL` creating a Postgres trigger function that `RAISE EXCEPTION` on `UPDATE`/`DELETE` of the `audit_auditlog` table, with a reverse that drops it. This closes the `QuerySet.update()` / bulk / raw-SQL bypass that model methods can't.
- `services.py` — `record(actor, action, *, makerspace=None, target=None, target_type="", meta=None) -> AuditLog`. If `target` is a model instance, derive `target_type` (`label_lower`) and `target_id` (`str(pk)`). Single `create`. **The** function phases 4–7 call.
- `admin.py` — read-only Unfold `ModelAdmin` (`has_add/change/delete_permission=False`); list display + filters.
- Tests: `backend/tests/test_audit.py`.

### New — `apps/evidence/`
- `__init__.py`, `apps.py` (`EvidenceConfig`, `name="apps.evidence"`)
- `models.py` — `EvidencePhoto`: `makerspace` (FK, `on_delete=PROTECT`), `evidence_type` (`TextChoices` issue|return), `object_key` (CharField, unique), `uploaded_by` (FK User, `on_delete=PROTECT`), `created_at` (auto_now_add). App-level `save()`/`delete()` immutability guards.
- `migrations/0001_initial.py` **+ `0002_evidencephoto_immutable_triggers.py`** — `RunSQL` Postgres trigger rejecting `UPDATE`/`DELETE` on `evidence_evidencephoto` (mirrors AuditLog).
- `storage.py` — boto3-backed helpers (one place; views never touch boto3):
  - `_client()` — builds the S3 client with the explicit `Config(s3v4, path-style)` + endpoint/keys/region. (Codex fix #4.)
  - `evidence_object_key(makerspace_id, evidence_type) -> str` — `evidence/<makerspace_id>/<type>/<uuid4().hex>` (uuid at call time).
  - `presigned_upload(object_key, content_type) -> dict` — `generate_presigned_post` with `Fields={"Content-Type": content_type}` and `Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, EVIDENCE_MAX_BYTES]]`; TTL = `EVIDENCE_URL_TTL_SECONDS`. Raises `StorageUnavailable` on boto/endpoint error.
  - `presigned_get_url(object_key) -> str` and `object_exists(object_key) -> bool` (HEAD). Same TTL.
- `serializers.py` — `EvidenceUrlRequestSerializer` (`evidence_type` choice, `content_type` validated against `EVIDENCE_ALLOWED_MIME`), `EvidenceUrlResponseSerializer` (`evidence_id`, `upload_url`, `fields`, `object_key`), `EvidenceGetResponseSerializer` (`url`, `expires_in`).
- `views.py`:
  - `EvidenceUploadUrlView(StaffAPIView)` — `required_action=Action.UPLOAD_EVIDENCE`; `permission_classes = StaffAPIView.permission_classes + [HasMakerspaceAction]` (Codex fix #6); makerspace from typed URL kwarg. POST: validate body → mint key → `presigned_upload()` (catch `StorageUnavailable` → **503**) → inside `transaction.atomic` create `EvidencePhoto` → `audit.record(actor, "evidence.upload_url_issued", makerspace, target=photo)` → 201 with `{evidence_id, upload_url, fields, object_key}`. Structured log on issue/failure; **never log signed URL/fields**.
  - `EvidenceDetailView(MakerspaceScopedQuerysetMixin, RetrieveAPIView-style)` — `permission_classes=[IsAuthenticated, IsStaff]`; `queryset=EvidencePhoto.objects.all()` auto-scoped → cross-tenant id 404. GET: `object_exists()` HEAD (missing → 409); `presigned_get_url()` (error → 503); `audit.record(actor, "evidence.viewed", makerspace, target=photo)`; return `{url, expires_in}`.
  - All endpoints documented with `@extend_schema` (request/response/error 400/403/404/409/503).
- `urls.py` — the two routes above; `app_name="evidence_admin"`.
- `admin.py` — read-only Unfold admin for `EvidencePhoto`.
- Tests: `backend/tests/test_evidence.py`.

### Modified
- `backend/config/settings.py`:
  - `INSTALLED_APPS += ["storages", "apps.audit", "apps.evidence"]`.
  - Storage block (django-environ): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME` (default `evidence`), `AWS_S3_ENDPOINT_URL`, `AWS_S3_PUBLIC_ENDPOINT_URL` (default = endpoint), `AWS_S3_REGION_NAME` (default `us-east-1`), `AWS_S3_ADDRESSING_STYLE="path"`, `AWS_S3_SIGNATURE_VERSION="s3v4"`, `AWS_DEFAULT_ACL=None`, `AWS_QUERYSTRING_AUTH=True`. **Django 5.1 `STORAGES`** dict (not legacy `DEFAULT_FILE_STORAGE`) → default backend `storages.backends.s3boto3.S3Boto3Storage`; keep `staticfiles` as whitenoise. Add `EVIDENCE_URL_TTL_SECONDS=env.int(default=300)`, `EVIDENCE_MAX_BYTES=env.int(default=10*1024*1024)`, `EVIDENCE_ALLOWED_MIME=["image/jpeg","image/png","image/webp"]`.
- `backend/config/urls.py`: mount `apps.evidence.urls` at `api/v1/admin/`.
- `backend/apps/accounts/rbac.py`: add `Action.UPLOAD_EVIDENCE="upload_evidence"`; add to `_ADMIN_ACTIONS` and `_GUEST_ADMIN_ACTIONS`.
- `backend/requirements.txt`: `django-storages[s3]>=1.14,<2`, `boto3>=1.34,<2` (bounded ranges, matching the repo's existing pin style). `cryptography` already present.
- `backend/.env.example`: `AWS_*` keys (MinIO dev defaults: endpoint `http://localhost:9000`, key/secret `minioadmin`), `AWS_S3_PUBLIC_ENDPOINT_URL`, `EVIDENCE_URL_TTL_SECONDS`, `EVIDENCE_MAX_BYTES`, with a comment that dockerized-backend signed URLs need the internal/public endpoint split (out of scope this phase).
- `docker-compose.yml`: add `minio` service (`minio/minio`, API 9000 + console 9001, volume, healthcheck) and a one-shot `createbuckets` init container (`minio/mc`) that waits for MinIO, creates the **private** `evidence` bucket, and **sets bucket CORS** allowing browser `PUT/POST/GET/HEAD` from the dev origins (Codex fix #4). Do **not** wire the existing `backend` service to MinIO (host-dev only this phase); leave a comment.
- `CLAUDE.md`: document the audit + evidence modules, the storage env, the signed-URL + private-bucket convention, and that object keys are non-secret identifiers (bucket privacy + signed URLs are the control — Codex note correcting the earlier "never expose object keys" wording).

## Tests (Stage 3 — external behavior)
- **AuditLog**: `record()` creates row + derives target_type/id; `instance.save()`-update raises; `delete()` raises; **`AuditLog.objects.filter(pk=...).update(...)` raises (trigger)**; queryset `.delete()` raises (trigger); makerspace nullable for global actions.
- **EvidencePhoto immutability**: create works; second `save()` raises; `delete()` raises; queryset `.update()`/`.delete()` raise (trigger).
- **Upload endpoint**: admin/guest with UPLOAD_EVIDENCE → 201 `{evidence_id, upload_url, fields, object_key}`, exactly one EvidencePhoto + one audit row; bad MIME → 400; oversize handled by POST conditions (documented, asserted in policy fields); requester/anon → 403; user with no membership in that makerspace → 403; storage error (mocked) → 503 **and no row created**.
- **Evidence GET**: in-scope staff → `{url, expires_in}` + one audit row; cross-tenant id → 404; object missing (mocked HEAD) → 409; storage error → 503.
- **Storage helpers**: boto3 client mocked — assert `generate_presigned_post` called with the content-length-range + content-type conditions and correct expiry; assert client built with s3v4 + path addressing. (No live MinIO in CI; an opt-in test can hit real MinIO when `AWS_S3_ENDPOINT_URL` is set.)

## Risks / invariants
- **Evidence private** → private bucket + `AWS_QUERYSTRING_AUTH=True`, signed URLs only, short TTL. Object keys are identifiers, not secrets; privacy is enforced by the bucket + signing, not key obscurity.
- **Immutability** → model `save()`/`delete()` guards **and** Postgres `UPDATE`/`DELETE` triggers **and** read-only admin, for both AuditLog and EvidencePhoto.
- **Scoping** → GET via scoped queryset (404 cross-tenant); upload via typed URL kwarg + `HasMakerspaceAction`.
- **Storage failure** → fail safe: 503, no durable row, structured log, never crash; never log credentials/signed URLs.
- **No quantity/workflow logic** here — pure infrastructure.

## Out of scope (later phases)
- Linking evidence to a `HardwareRequest`/issue record (Phase 6, FK lives on the issue side).
- "Cannot issue without issue photo" (Phase 6) / "cannot return without return photo + remark" (Phase 7).
- Dockerized-backend signed URLs (internal/public endpoint split — seam added, wiring deferred).
- The audit log is *built* here; the workflow *writes* to it from Phase 4 on.
