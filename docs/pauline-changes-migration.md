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
