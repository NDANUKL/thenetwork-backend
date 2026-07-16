# FieldPulse Sync API Contract (Week 4)

## Authentication

No custom auth was built — Frappe already provides per-user API key/secret
natively, and every FP Agent is linked to a User via the `user` field.

1. In Desk, open the Agent's linked User record.
2. Under "API Access," click "Generate Keys." This produces an `api_key`
   and `api_secret`.
3. The mobile client sends both on every request:
   `Authorization: token <api_key>:<api_secret>`

No extra code needed. If a User doesn't have keys yet, generate them once
and store api_secret securely on the device (it's shown only once).

## Pull pattern (device downloads)

`GET /api/method/fieldpulse.api.sync_pull_assignments?since=<ISO timestamp or omitted>`

Returns everything the mobile client needs in one call, scoped to the
calling agent (resolved via the linked User -> FP Agent):

- `tasks` — FP Task records assigned to this agent, changed since `since`
- `locations` — FP Location records referenced by those tasks
- `questionnaires` — FP Questionnaire records referenced by those tasks
- `questions` / `question_options` — full form definitions for those questionnaires
- `server_time` — store this and pass it back as `since` on the next pull

**Deviation from the original plan:** the plan specifies three separate
pull endpoints (assignments / questionnaires / locations). We combined
them into one call since the client needs all three together anyway, and
it halves the round trips on a slow connection. Functionally equivalent.

## Push pattern (device uploads)

### `POST /api/method/fieldpulse.api.sync_push_responses`

Body:
```json
{
  "task_responses": [ { "client_uuid": "...", "task": "...", "status": "Submitted", "client_updated_at": "...", ... } ],
  "question_responses": [ { "client_uuid": "...", "task_response": "...", "question": "...", "answer_text": "...", "client_updated_at": "..." } ]
}
```

Up to ~50 items per batch. Each item validates and saves independently —
one bad item does not fail the rest of the batch.

### `POST /api/method/fieldpulse.api.sync_upload_attachment`

Attachments are a two-step flow, reusing Frappe's own file upload
machinery instead of a custom multipart handler:

1. Client uploads the raw file to Frappe's built-in
   `POST /api/method/upload_file` → gets back a `file_url`.
2. Client calls `sync_upload_attachment` with that `file_url` plus
   metadata (`client_uuid`, `task_response`, `attachment_type`, GPS,
   timestamp). This links the file to the response record and is
   idempotent — resending the same `client_uuid` returns success
   without creating a duplicate or overwriting the stored file
   (append-only, per the locked architecture decision).

### `POST /api/method/fieldpulse.api.sync_log`

Posts a sync session summary (counts pulled/pushed/accepted/rejected,
errors) for debugging and audit.

## Idempotency

Every push item carries a `client_uuid`, generated on-device before the
record ever reaches the network. If the server already has a record with
that UUID, it returns success with the existing `server_id` instead of
creating a duplicate. This is what makes retries after a dropped
connection safe.

## Error contract

`sync_push_responses` always returns:
```json
{
  "accepted": [ { "client_uuid": "...", "server_id": "...", "status": "accepted | already_exists" } ],
  "rejected": [ { "client_uuid": "...", "errors": ["..."] } ]
}
```

## Task assignment helpers (Week 3, used alongside sync)

- `POST /api/method/fieldpulse.fieldpulse.doctype.fp_task.fp_task.bulk_assign_tasks`
  — cross-product of agents x locations, one task each.
- `POST /api/method/fieldpulse.fieldpulse.doctype.fp_task.fp_task.auto_assign_by_proximity`
  — assigns every active location within an agent's `service_radius_km`.
  This is the GPS-based substitute for the plan's "auto-assign by region" —
  there's no named region field in this schema, only GPS + radius.
