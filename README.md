# FieldPulse

Offline-first geo-coded task platform for field agents.

This repository contains the Frappe backend app for the FieldPulse Trust Market MVP:

- field-agent task assignment
- offline-first questionnaire definitions
- idempotent response sync by client UUID
- append-only attachment evidence
- server-side geofence validation
- sync logging for field debugging

## Frappe App

Internal app/package name: `fieldpulse`

Product label: FieldPulse

The user-facing domain terms are Agent, Location, Questionnaire, Task, Response, Attachment, and Sync Log. The Frappe DocTypes are prefixed with `FP` to avoid global DocType name collisions:

- `FP Agent`
- `FP Location`
- `FP Questionnaire`
- `FP Question`
- `FP Question Option`
- `FP Task`
- `FP Task Response`
- `FP Question Response`
- `FP Attachment`
- `FP Sync Log`

## MVP Scope

The first build focuses on Isaac's Trust Market verifier workflow:

```text
Supervisor assigns a consent-cleared verification task
-> field agent pulls it to mobile
-> agent completes an offline questionnaire with GPS/photo evidence
-> mobile pushes structured answers and attachment metadata
-> Frappe validates idempotency, task ownership, geofence, and append-only evidence
-> response is ready for QA/proof report review
```

Outcome Market services such as provider catalogues, escrow, payout split, and hard-record connectors are intentionally left as future extension points.

## Development Notes

DocTypes are committed as JSON fixtures under `fieldpulse/fieldpulse/doctype`.

Seed roles and question types are defined in `fieldpulse/install.py`.

Whitelisted sync API stubs are in `fieldpulse/api.py`.

