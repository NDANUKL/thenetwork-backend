# Important customer request emails

## Events and customer preference

The Account checkbox, `DD Customer Account.email_notifications`, now controls all five optional request emails:

| Trigger | Customer destination |
| --- | --- |
| Details request published as Details needed | Request questions |
| Quotation issued | Billing: download and accept quotation |
| Deposit or balance verified Paid by Pesapal | Billing Receipts section |
| Client report approved and available | Request report section |
| Coordinator publishes a new or changed dispute reply | Dispute details |

Verification, password reset and early-access approval remain independent of this preference. No emails are sent for ordinary internal status changes. Payment confirmation includes the received amount and currency. Test payments are explicitly labelled as sandbox payments. Receipt and report downloads remain authenticated; no private files are attached to emails.

## Why the old details email failed

The old website helper sent email only after a signed Frappe webhook called `/api/frappe/details-published`. During the read-only live check on 23 October 2026, both DD Request Details webhooks (after_insert and on_update) were disabled. This explains the missing trigger. They remain untouched. Source inspection also found no native retry worker for that old delivery path.

The new native event hooks capture notifications directly and the old webhook compatibility helper queues into the same backend flow instead of sending independently. There is no need to re-enable those webhooks.

## Durable delivery

`DD Customer Notification` is a System Manager-only outbox. Its event key combines event type, source and revision. Repeated document saves and payment callbacks do not create duplicate messages. Dispute revisions are based on the actual response content.

Capture creates the outbox record in the source transaction and enqueues delivery after commit. Missing Redis does not lose the Pending record. A five-minute scheduler retries Pending deliveries and also captures currently unanswered, unemailed details rounds left by the old flow. Other old milestones are not bulk emailed at deployment.

The sender rechecks ownership, account verification, account access, the customer's preference and current event state. Stale events, resolved details questions, withdrawn/accepted quotations and reversed payments are skipped. A changed account email cannot reuse an old-recipient payload. The exact Resend payload and a stable idempotency key are persisted before HTTP delivery. Retries back off from five minutes to one hour, with at most eight attempts. Uncertain deliveries beyond 23 hours require review rather than reusing an expired provider idempotency key. Resend retains these keys for 24 hours.

Sent means accepted by Resend, not proven inbox delivery. The outbox records the provider email ID for checking delivery/bounce status in Resend. Logs and failure summaries do not include API keys, recipient addresses or provider response bodies.

## Deployment and verification

1. Deploy backend code and run normal Frappe migration to create DD Customer Notification and sync the scheduler. Deploy the website helper and Account wording alongside it.
2. In DD Access Settings, verify the HTTPS customer origin, verified sender address and Resend API key. These settings are shared with access approval emails; website `.env` Resend credentials alone do not configure the backend sender. The live check confirmed a sender address and origin, but a normal settings read cannot establish whether a usable password is stored.
3. A System Manager can call `fieldpulse.customer_notifications.delivery_status` to inspect redacted configuration readiness and Pending/Needs review counts. It never returns credentials or recipients. After fixing configuration, a System Manager may call the POST-only `fieldpulse.customer_notifications.retry_notification` with the outbox record name. It preserves the original payload/key, never resends Sent records, and refuses expired retry windows.
4. Ensure scheduler and default background workers are running. Review DD Customer Notification and the Resend provider status. Check currently unanswered details requests after the next scheduler cycle.
5. Validate one event of each type against a controlled customer account, plus an opted-out account. No live emails were sent during local verification.

Local tests cover event hooks, event deduplication, preferences, stale events, verified payment capture, stable retry payload/key, queue/provider failures, expired retry windows, sender configuration and authenticated destination links.
