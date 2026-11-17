# Beta feedback (source only)

Deploy the native DD Beta Feedback DocType and beta_feedback module with an ordinary schema migration, then deploy the compatible website. The existing dashboard sync must run to update the Field Operations Custom HTML Block; use the normal migration path, never retired scripts. Verify the shortcut appears after migration.

The website displays the invitation only on dashboard Home, for a verified, approved customer with at least one Diaspora Request and no prior response. Request detail pages have no feedback invitation. Direct access and POST requests are subject to the same server eligibility check. Identity comes from the authenticated website session through the existing System Manager bridge; backend fields never trust browser-provided names, email, timestamps or account IDs.

DD Beta Feedback stores form version 1, all 12 questions, conditional confusion details, use case, fair amount and currency, customer account/name/email and server submission time explicitly in UTC. Form data is immutable. Field Operations Coordinators and System Managers have read/report/export access; customers cannot list responses through Desk or submit directly through Frappe. Concurrent and repeated POSTs serialize on the account and return existing submitted status without overwriting or duplicating a response. Customer account has a unique database constraint in the feedback table. Records cannot be manually deleted to reopen eligibility.

Staging acceptance: customer with no request cannot submit; request owner sees Home invitation; all answer types and conditional fields validate; retry after a lost response creates no duplicate; two concurrent submissions store one response; refreshing Home after submission hides the invitation; a second customer cannot read another response; a coordinator can open the shortcut and see all questions, answers, identity and UTC timestamp. Validate desktop/mobile keyboard layout and real website-to-backend session integration. No source-only check establishes deployment.

Country of residence is a required, length-limited field for new feedback submissions for broad client demographics. No city or address is requested. Existing responses remain valid with no country. Deploy the backend and run ordinary schema migration before the website update. Source only; not deployed.

Form version 2 asks three separate fair prices (land/property, construction progress, business/assets), only when pricing clarity is Yes. Each uses KES or USD. No excludes hidden prices on the server. Version 1 submissions remain supported during frontend rollout; historical prices and currencies are retained. Run ordinary schema migration before deploying the website. Source only.

Country is mandatory for all new submissions, enforced by the API after trimming whitespace. The stored field remains nullable to preserve historical responses.
