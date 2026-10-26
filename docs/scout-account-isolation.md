# Scout account isolation — 19 October 2026

The Scout Profile `legacy_fp_agent` field is hidden in the native schema. Its
unique link remains intact for registration, migration and contact synchronization.
Deploy schema changes through normal native migration and verify the resulting
metadata on the target site. The original 19 October source work did not establish
feature deployment. Native handover is complete; do not repeat its migrations
or edit retired scripts to change this field.

Mobile source in `DiasporaDesk/mobile` used one `diaspora-desk.db` SQLite file for
every login. Logout removed credentials but retained all cached tasks, and pulls
only upserted records. A subsequent account could therefore see the previous
account's downloaded tasks even when its own server pull returned no tasks.
The backend assignment pull already filters by the session's Scout Profile.

The mobile fix uses a separate database for each service/account, remounts the
database provider when credentials change, and rejects sync when the database
does not match the authenticated account. Sync deduplication is per database.
Pulled tasks also store `scout_profile` as their local assignment owner.
The previous shared database is preserved but never opened by the new app.
Existing sessions without an account identifier get an isolated session cache
until explicit sign-in. Unsynced work in the old database needs owner-verified
recovery; it must not be automatically assigned to whichever user logs in next.

Verification: mobile TypeScript check and account-isolation regression checks
pass locally. Device-level A → logout → B → logout → A testing and release are
still required. No production script was changed or retired.
