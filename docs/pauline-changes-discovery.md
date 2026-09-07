# Pauline changes — Phase 0 discovery

Date: 2026-09-07

## Scope inspected

- Backend: `thenetwork-backend` (standalone Git repository, `origin` is `NDANUKL/thenetwork-backend`).
- Mobile: `DiasporaDesk/mobile`, inside the `DiasporaDesk` monorepo.

`DiasporaDesk` also contains `FieldPulse/`.  Its checked-in `fieldpulse/api.py`
is byte-identical to the deploy repository's current `fieldpulse/api.py`, which
confirms the historical subtree-style relationship described in the plan.
Backend work should still be made directly in `thenetwork-backend` as instructed,
then reconciled to `DiasporaDesk/FieldPulse` separately after verification.

## Backend findings

The actual DocType names are all `FP`-prefixed, not the unprefixed names used
in the plan:

| Plan term | Existing DocType | Relevant current state |
| --- | --- | --- |
| Task | `FP Task` | Links to `FP Agent`, `FP Location`, and `FP Questionnaire`; statuses are Draft, Assigned, In Progress, Submitted, Approved, Rejected, Cancelled. |
| Task Response | `FP Task Response` | Links to `FP Task` and `FP Agent`; includes geofence fields. |
| Question Response | `FP Question Response` | Links to `FP Task Response` and `FP Question`. |
| Agent | `FP Agent` | Links to User; has name/phone plus GPS/radius, status, trust/KYC/bond fields, and `last_sync_at`. |
| Location | `FP Location` | GPS geofence location; no county field. |
| Questionnaire | `FP Questionnaire` | Present with questions/options in separate `FP Question` and `FP Question Option` DocTypes. |
| Diaspora Request | `Diaspora Request` | Present, with its own request status/category and child tables. |
| Attachment/Evidence | `FP Attachment` | References a Frappe `Attach` `file_url` plus task/question responses and capture metadata. |

There are no `Field Request`, `Field Task`, `Scout Profile`, `Field Evidence`,
or Field Task reassignment-log DocTypes yet.

`fieldpulse/api.py` exposes:

- `sync_pull_assignments` (one combined pull, rather than separate pull endpoints)
- `sync_push_responses`
- `sync_upload_attachment` (not `sync_push_attachment`)
- `sync_log`

`sync_upload_attachment` only creates an `FP Attachment` record from a
previously supplied `file_url`. The documented preceding call is Frappe's
built-in `upload_file`; no R2/S3/Cloudflare integration is present in the app
source. The repository is source-only: it contains no `site_config.json` or
environment file, so deployed storage configuration cannot be inspected here.

Existing roles are Field Agent, Supervisor, Admin, and Diaspora Website
Integration. No Field Operations Coordinator role is defined. Whether a
Clarissa User exists is runtime database state and cannot be established from
this source repository; no site/database connection is included.

## Mobile findings

The app has an existing Profile tab (`app/(tabs)/profile.tsx`) with device,
storage, cellular-sync, and sign-out controls. It has no availability control.

The SQLite model still uses generic local names (`tasks`, `task_responses`,
`attachments`), populated from the current `FP Task` / `FP Agent` sync payload.
Captured photos/files are permanently copied to device storage and queued in
the `attachments` table with `sync_status = pending`.

Crucially, the current sync engine (`services/sync.ts`) never uploads those
attachment records. It only pulls assignments and pushes task/question
responses. There is no mobile call to either Frappe `upload_file` or
`fieldpulse.api.sync_upload_attachment`. Thus the planned Phase 7 starting
assumption of an existing mobile attachment-upload call site is not true;
the attachment queue is currently stranded on-device.

## Material contradictions / required decision before Phase 1

1. The plan refers to unprefixed `Task`, `Agent`, `Task Response`, `Question
   Response`, `Location`, and `Questionnaire`, but this app uses the distinct
   `FP *` DocTypes throughout its schema, API, and mobile payloads. The
   migration/repointing plan needs confirmation that `Field Task` and `Scout
   Profile` are successors specifically to `FP Task` and `FP Agent`, and that
   the associated response/doc links should likewise target the `FP *` tables.
2. The attachment API is named `sync_upload_attachment`, not
   `sync_push_attachment`, and mobile has no implemented upload path at all.
   Phase 7's analysis must begin from an incomplete/offline-only attachment
   queue rather than a working Frappe-server upload flow.
3. `FP Task` has an existing task/consent/QA workflow and `FP Agent` has
   marketplace/trust and GPS-radius fields. The intended treatment of these
   existing fields during the proposed replacement migration is not specified.

## Confirmed follow-up decisions

- `Field Task` and `Scout Profile` are successors specifically to `FP Task`
  and `FP Agent`. Associated response/location/questionnaire references use
  the existing `FP *` DocTypes until they are migrated as part of this work.
- The legacy endpoint name is `sync_upload_attachment`. The selected future
  attachment path is Option A: the R2 presigned-URL flow will be the only
  upload path. It will replace the stranded local attachment queue; no Frappe
  upload fallback will be retained.
- The existing FP Agent trust/KYC/bond fields and FP Task consent/QA workflow
  fields are out of scope. They remain only on the deprecated legacy records
  and are not migrated into Scout Profile or Field Task.
- `Scout Profile.base_county` cannot be derived from FP Agent's GPS/radius
  data. The migration will leave it blank and document a required manual
  backfill.

No code changes beyond this Phase 0 discovery note have been made.
