# Beta access and public launch

Deploy the native backend and run normal bench migrate before deploying the website.
The owner has confirmed native handover; this change does not modify live or disabled script records.
Normal migration does not backfill approval decisions or disable existing accounts. Their blank Beta access status means Approved; authorized deactivation actions are described below.
New accounts receive Pending in invite-only mode, including registrations created from Desk.
Email verification still sets the password and activates the Frappe user, while DD access is checked separately.

## Configure once

In Desk, search for DD Access Settings (System Manager only):

- Registration access: Invite only (the default).
- Website origin: the deployed website HTTPS origin.
- Email sender and Resend API key: use the same verified sender and provider credentials as the website.

The password field stores the provider key using Frappe encryption. Do not put it in source control.
Keep the normal scheduler and background workers running for approval delivery and retries.
The website continues to use its existing Resend environment variables for verification, recovery and request-details messages.

## Manage accounts

Search for DD Customer Account. Filter Beta access by Pending; Email Verified identifies completed signups.
Open a user and choose Grant access, Remove access, or Reject, or edit the Beta access field and save.
Approval queues one branded email once the email address is verified. Approval before verification waits until verification.
The approval email sent at field confirms provider acceptance, not inbox delivery.
Failed deliveries are retried every five minutes with an idempotency key for that approval.
Inspect failed background jobs if the sent timestamp remains empty; correct delivery configuration before retrying.
Rejection/removal clears unsent approval work and sends no email. Status is shown after a successful password login.
In invite-only mode, removal denies existing DD sessions on their next server check. Open registration admits Pending accounts under the existing launch policy; use **Deactivate** to block an account regardless of registration mode. Raw request/payment APIs also enforce the policy.

## Client deactivation and reactivation

On **DD Customer Account**, a System Manager can use **Deactivate** or **Reactivate**, with a reason. **Account Activation** is independent from **Beta access**: both the approval workflow and email verification retain their existing rules. Deactivation blocks the account even when Registration access is Open to everyone. It disables the linked customer Website User, removes API/reset credentials and revokes Frappe sessions after commit. Repeat signup, verification links, recovery and ordinary User edits cannot reactivate it. Historical requests, payments and account data remain intact.

Reactivation restores the same account and records who performed it, when and why. A verified customer User is enabled; an unverified User stays disabled until normal email verification. The original Pending/Rejected/Approved decision is not changed, so reactivation cannot grant beta approval. Revoked credentials/sessions are not restored: the client must sign in again. These actions are restricted to customer Website Users and cannot be used to enable or disable staff accounts. The existing approval notification flow skips deactivated accounts; no separate reactivation email is introduced. Version history preserves repeated access changes.

These are native backend/schema/Desk changes and require normal backend deployment/migration. No retired site script changes or extra handover are needed. Verify the actual deployed revision separately from source.

## Launch policy

Change Registration access to Open to everyone and save. No website rebuild is needed.
New registrations and existing Pending accounts gain access; email verification is still required.
Rejected accounts remain blocked until an admin grants access. Existing disabled users remain disabled.
The registration form reads this same policy and changes Join the waitlist to Register on page load.
Switching back to Invite only blocks still-Pending accounts again; explicitly Approved and legacy accounts keep access.

## Validation before rollout

Run Python offline tests, website auth tests and browser signup checks. On a staging Frappe site,
verify schema sync and permissions, existing-account login, pending/rejected login, approval email receipt,
revoked-session API denial, and public-mode registration using email addresses owned by the tester.
Local mocks do not verify live email delivery or Frappe schema migration. No production records were changed by this implementation.

Also verify Deactivate with an existing portal session/API key, public-registration mode, verification and recovery retries. Reactivate Approved, Pending, Rejected and unverified accounts and confirm each retains its original approval/verification gate, requires fresh sign-in, and keeps its historical records. Confirm ordinary customers/coordinators cannot call these System Manager actions.
