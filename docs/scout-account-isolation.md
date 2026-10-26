# Scout account isolation — 19 October 2026

The Scout Profile `legacy_fp_agent` field is hidden in the native schema. Its
unique link remains intact for registration, migration and contact synchronization.
This source change has not been applied to production. Apply the matching hidden
property on the live site's Scout Profile with a metadata backup; do not run the
native handover or retirement migrations solely to hide this field.

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
