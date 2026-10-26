# Recurring checks

Customer entry: My Requests -> request -> Set up recurring checks. The native website API uses the customer's Frappe session and CSRF token. No script-runtime fallback or production installer is provided.

## First release

- Whole-request recurrence, including every supported project. Source quotation must be accepted; each project must have a confirmed questionnaire and dispatch-confirmed locations.
- Monthly, every three months, or explicit dates; 1-24 occurrences ending within 24 months. Month-end schedules keep their original anchor. Visit windows cannot overlap.
- Plans start Pending review. Coordinator approval rechecks the frozen source scope and records the schedule/commercial review. It does not accept prices for future visits or authorize a scout assignment.
- The private scope snapshot contains the exact template references, project-specific checks/configuration and agreed source inputs. Later source edits cannot change an active plan.
- Within 14 days, ask the customer to confirm access. The normal preference-aware, durable customer email queue and portal inbox show reminders. A paused/cancelled/expired reminder cannot send. Resuming a plan gives its reminder a new revision.
- Every five minutes, the scheduler prepares access-confirmed visits in active plans. A coordinator can also Prepare from DD Recurring Occurrence. A new Diaspora Request is created with new Field Requests and the pinned questionnaires. No tasks, quotations, invoices, payments, answers, evidence or reports are copied.
- Source site inputs are reused but dispatch verification is cleared. The existing per-request quotation acceptance, verified 50% deposit, location verification, scout offer/compensation and report/balance gates still apply.
- Plans have no automatic renewal or charging. Prepared visits continue if the parent is paused/cancelled. Cancel/Decline only cancel unprepared visits. Skip requires a reason and cannot affect prepared work. Pausing does not shift dates; expired unprepared windows become Missed, never catch-up assignments.
- Each occurrence links its own request/report; an approved report marks it Completed. A rejected occurrence request marks that occurrence Cancelled without changing financial records. Original rework remains part of its occurrence, not a later scheduled visit.
- Access instructions can be updated before preparation. New questions, evidence, sites or scope use a new assessed request and, where needed, a new plan. This release does not silently amend a live plan or run AI on access notes.

## Operations and demand

Desk: DD Recurring Plan -> Plan actions, Visit schedule. DD Recurring Occurrence -> Prepare/Skip. All actions check roles, ownership, current modified version and retry keys; raw edits of schedule, scope, provenance and history are blocked.

Recurring Check Schedule is a standard Desk report with date-range filters, scheduled month, service, plan status, occurrence outcome and prepared request. Use these records to separate planned demand from completed/missed/skipped/cancelled visits. The report does not describe planned visits as collected revenue. Independent repeat requests remain separate records.

## Deployment verification

No live deployment is performed by these source changes. Deploy the native backend and run normal Frappe migration/build before enabling the website release. Verify the two new standard DocTypes, added provenance fields/unique links, new report and scheduler owner on a staging copy. Preserve existing handover flags, disabled script records, credentials and financial history. No mobile update is needed; prepared visits use the normal Field Task contract.

On real Frappe verify: create/retry and duplicate-plan protection; cross-customer denial; coordinator review and changed-source rejection; month-end and custom dates; pause/skip/cancel racing with preparation; pending access and expired windows; reminder preferences, retries and resume; exact questionnaire inheritance with fresh site verification; separate quote/deposit and scout compensation gates; approved report linkage; report permissions. Local Python mocks and browser fixtures do not replace model-sync or live payment/device checks.
