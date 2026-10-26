# Production and backend alignment

Production is native-owned. Read-only verification of `thenetwork.frappe.cloud` on 26 October 2026 confirmed the completed native handover of 16 October 2026: Patch Log contains `fieldpulse.patches.v1_0.adopt_native_dd_schema` and `fieldpulse.patches.v1_0.complete_native_dd_handover`; all 29 DD Server Scripts have `disabled=1`; all eight DD Client Scripts have `enabled=0`; the checked DD schemas are standard FieldPulse DocTypes; and the former script-owned Pesapal reconciliation job is stopped.

Runtime changes belong in `Documents/thenetwork-backend`: native Python modules, standard DocTypes/controllers, hooks, scheduled jobs and Desk assets. Deploy and verify changes through the native application workflow. Do not mirror new behavior into retired site scripts, recreate the removed website installers, or re-enable those scripts. Retain the disabled records as recovery references until explicit cleanup approval. Do not rerun handover or retirement migrations for routine updates. A local checkout is not evidence that a new change has been deployed.

The earlier instruction that production remained script-owned was a pre-handover note and is superseded by this live verification. See [handover verification](production-handover-verification-2026-10-26.md).

Confirmed policy: one quotation with 50% deposit and 50% balance; assign scouts only after verified deposit. Customers may review the complete approved report before paying the balance. Responsibility and Location columns stay removed from the assignment dialog. Existing recorded destinations and task metadata remain available to operational code.
