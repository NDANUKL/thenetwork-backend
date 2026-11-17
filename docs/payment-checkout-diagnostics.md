# Checkout rejection diagnostics

10 November 2026, source only. Checkout Error Log entries retain bounded HTTP/provider status codes and a fixed reason category derived from provider text in memory. Categories are diagnostic hints, not proof of cause. Unknown responses remain UNCLASSIFIED. Raw response bodies, provider messages, URLs, arbitrary error codes and credentials are never logged. Existing reconciliation codes, retry rules and payment verification remain unchanged.

Deploy the native backend revision through the normal release workflow and restart application workers. No schema change or retired script installation is required. Verify on staging with an approved sandbox checkout. This change cannot reconstruct the discarded response for attempt 16msdaj4eu. Confirm that attempt against provider records before any operational resolution; do not clear Review or create a replacement order merely to collect diagnostics. No live records are changed by this source update.


## 11 November 2026 sandbox checkout compatibility

Source change, not deployed. The owner requested that customer billing collection remain entirely on Pesapal; no website billing form is added. Direct sandbox controls reproduced rejected missing name/address fields despite the documented optional fields. A complete sandbox test address produced an order at KES 0.50. Authentication and a historical order status query succeeded. Re-registering the existing IPN returned the same ID and did not resolve the rejection; an empty IPN list alone was not proof of a stale registration.

`payment_rules.checkout_billing_address` supplies explicitly labelled synthetic name/address values only when the validated environment is `sandbox`. It preserves the authenticated email and does not infer billing details from a customer's fieldwork destination. Live payloads remain email-only, with billing details collected on Pesapal. The sandbox fixture is a test compatibility workaround, not a claim that live requires the same fields or that the provider regression has been corrected. Sandbox test values may appear prefilled on the provider page. Unknown environments fail closed.

The exact new helper was exercised from the backend host against Pesapal sandbox: provider status 200, tracking ID present and valid sandbox checkout URL present at KES 0.50. No payment was completed, and no customer payment records were changed. Billing-name/address rejections now receive the fixed BILLING_ADDRESS diagnostic category without retaining provider text.

Deploy the native backend through the normal release workflow and restart workers; no frontend, schema, retired-script or handover migration change is required. Do not reset Review/Pending attempts, clear their references or create replacement customer orders merely to test the fix. Existing attempts without checkout URLs remain blocked pending provider reconciliation; the source change does not resolve attempt 190hm4tcnf. Verify a fresh authorized sandbox obligation after deployment, including the hosted billing page and verified return/IPN flow. Live behavior and hosted-page editing have not been verified by the isolated order-creation test.


## 17 November 2026 status verification diagnostics

Source only. Scheduled reconciliation now retains the same bounded HTTP/provider statuses and reason category as checkout, including TRACKING_ID and PROVIDER_ERROR hints. Each rejected scheduled status check writes a diagnostic, including retries of existing generic PROVIDER_REJECTED attempts; ordinary timeout deduplication and bounded backoff remain. No raw provider text, card details, tokens or response bodies are stored. Categories are hints, not proof of a configuration mismatch or bank decline.

The retry log explicitly says it retries a status check and does not charge again. Verification rejection preserves payment uncertainty and tracking evidence. A successful status query reporting status_code 2 is a failed payment, including Pesapal's documented card authorization failure; it is distinct from rejection of the status query itself. The website keeps another checkout blocked while verification is unresolved.

Deploy through the normal backend release workflow and restart workers. No schema change is required. Recheck attempt 97ig8udbd0 through normal reconciliation in its original environment; historical discarded diagnostics cannot be recovered by this code. Review the new safe category and provider records before changing configuration or resolving that attempt. This source fix cannot make an issuer authorize a declined card, and is not production verification.
