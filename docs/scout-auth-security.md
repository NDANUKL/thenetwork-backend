# Scout account security and rollout

Current runtime ownership follows [production policy](production-script-ownership.md) and [native integration](native-integration.md). This feature does not re-enable scripts or rerun handover patches.

## State on 27 October 2026

- Live System Settings were updated and read back: 5 consecutive failed login attempts, 300-second retry wait. Password-reset logout remains enabled. These site-wide throttle settings affect other site users too.
- Live `session_expiry` remains `170:00` (inactivity). Live two-factor authentication remains disabled.
- Native source now imposes a 604,800-second absolute maximum on scout sessions, independently of activity renewal. It requires a real session and rejects scout API-token access as a bypass. Existing session creation time is used for older sessions. New sessions have a server-owned creation marker.
- Native mobile login now runs the complete Frappe login flow, including its configured second factor. Initial challenge responses contain no SID. Verification is bound to the cached user, serialized under a challenge lock, and cached challenge credentials/secrets are consumed after success. Sensitive authentication fields are removed from the request form on every exit.
- The app supports Email/SMS/authenticator code challenges and same-account session renewal. The planned scout activation uses Email. Challenge/password/code data are not saved in SecureStore. Only the successfully verified session is saved. Guest recovery/auth requests explicitly omit an old session cookie.
- No PIN or biometric lock has been added. Offline drafts remain accessible for the saved account and are preserved after online expiry.

## Deployment and activation

1. Deploy native source with the existing normal application deployment process and restart/reload native Python/hooks. Deploy the matching mobile build. No DocType schema or historical ownership migration is required for these changes.
2. Verify password login, email delivery, expired/wrong code, repeated challenge submission, password reset and same-account offline-cache preservation on staging. No real scout login/reset emails were sent during implementation.
3. Once matching clients are installed and mail delivery works, an authorized System Manager can explicitly run `fieldpulse.scout_sessions.configure_security` with `enable_scout_two_factor=true`. It enables Email two-factor globally and the Field Agent role. It does not silently replace an already-enabled different second-factor method. Review other roles already flagged for two-factor authentication before activation, because the setting is site-wide.
4. With MFA enabled, scout sign-ins must complete the verified mobile flow. Other login paths cannot create an unverified scout session. Existing unverified sessions must sign in again; old app builds cannot complete the code step and must be updated before activation. Key-based password reset remains available without a valid old session, subject to the framework's reset-key validation.
5. Confirm live seven-day rejection and second-factor verification before marking either feature deployed. Source tests/export alone do not establish production activation. The absolute cap requires deployed Python; it cannot be implemented by changing the inactivity value alone.

Native configuration is explicit and is not called automatically during installation, migration, handover or startup. Throttle changes are already live; no other production settings were modified here.

## Existing account flows

Sign-up creates a disabled User and Pending Scout Application. Staff approval enables scout access and creates the agent/profile. My profile edits required full name/county and optional phone; availability/leave controls remain. Sign-out removes saved device credentials and attempts server logout, retaining account-specific offline work. Server deactivation revokes sessions/access. Sensitive recipient changes and deletion requests require the password again.

Forgot password calls the native reset endpoint with a generic result for unknown/blocked accounts. The server sends a framework-generated reset link for an active scout. The link opens the backend password-reset page; the framework checks its token and password policy. Password-reset logout is enabled. The email now tells the scout to return to Ground Scouts to sign in afterward. The reset request is rate-limited per IP/account. SMTP delivery and installed-phone link handling remain staging acceptance checks.

## Account deletion request

In the app: Privacy > Account controls > Request account deletion. The scout optionally explains why, confirms the password and submits online. Pending-upload/handover information is shown before confirmation. The server reuses an existing Open/Under review request instead of making duplicates.

System Managers/Admins review Scout Data Request. Statuses are Open, Under review, Completed and Declined. Closing a request requires a public explanation, including retained records. Status/reply changes create a scout notification and the Privacy page displays the outcome. Private processing notes stay private.

This is a request/review workflow. Marking Completed does not automatically remove files, anonymise records, deactivate access or clear device drafts. Administrators must carry out approved deletion/anonymisation separately and accurately record retained financial/audit evidence. No live account/data deletion was performed.

## Validation

420 native tests and 34 mobile test files pass, including absolute age despite renewed activity, malformed/future sessions, token rejection, MFA-marker enforcement, challenge binding/consumption, wrong/expired/cross-account codes, field scrubbing, reset privacy, required profile fields, and preserved offline identity across verification. TypeScript and Android export are checked in the mobile repository. Full real Frappe/Redis/SMTP/installed-device acceptance is still required before second-factor activation.
