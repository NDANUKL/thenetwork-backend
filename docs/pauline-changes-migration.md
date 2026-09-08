# Pauline changes migration notes

## Scout Profile migration

The `migrate_fp_agents_to_scout_profiles` post-model-sync patch creates one
Scout Profile per FP Agent, mapping `full_name` to `scout_name`, `user` to
`user`, and `phone` to `phone_number`.

FP Agent has GPS/radius coverage but no county field. Every migrated
`base_county` is intentionally left blank and needs manual backfill before
county-based allocation is used.

The legacy FP Agent record is retained unchanged. Its trust/KYC/bond fields
are not migrated and remain out of scope for this change.

## Field Task migration

The `migrate_fp_tasks_to_field_tasks` post-model-sync patch creates Field
Tasks using the legacy FP Task document names, maps the assigned FP Agent to
its Scout Profile, and carries over the existing location, questionnaire,
assignment, due, and submission data needed by the current questionnaire and
geofence workflow. Legacy `Draft` tasks become `Assigned`, because Field Task
does not retain a Draft status; other shared statuses are preserved.

The patch repoints FP Task Response and FP Sync Log links from FP Agent to
Scout Profile. FP Task remains intact and is not deprecated until a production
sync cycle has been verified.

## Mandatory staging procedure

Do not run the post-model-sync patches against production first.

1. Take a restorable database and private-files backup of the staging site.
2. Deploy this backend revision to staging and run `bench --site <staging-site>
   migrate`.
3. Record and compare the FP Agent / Scout Profile and FP Task / Field Task row
   counts. Spot-check linked task responses and sync logs to confirm that their
   Scout Profile and Field Task links resolve.
4. Exercise the mobile Phase 8 build against staging: login, pull, accept,
   start, submit, evidence upload, and activity reporting.
5. Keep production migration and Play Store submission blocked until that
   end-to-end run passes. The legacy FP Task and FP Agent records remain
   available for rollback analysis until then.
