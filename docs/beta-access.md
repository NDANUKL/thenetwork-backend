# Beta access and public launch

Deploy the native backend and run normal bench migrate before deploying the website.
The owner has confirmed native handover; this change does not modify live or disabled script records.
No existing accounts are backfilled or disabled. Their blank Beta access status means Approved.
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
Removal denies existing DD sessions on their next server check. Raw request/payment APIs also enforce the policy.

## Launch

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
