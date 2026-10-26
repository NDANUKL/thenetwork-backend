# Native backend integration — 16 October 2026

The production integration now has native source in `thenetwork-backend`; it is no longer represented only by copied installer files.

## Where the implementation lives

| Concern | Backend source |
| --- | --- |
| Customer registration and recovery bridge | `fieldpulse/customer_accounts.py` |
| Customer request listing, details submission, ownership and source locations | `fieldpulse/customer_requests.py` |
| Details publication, validation, next actions and notifications | `fieldpulse/request_details.py` |
| Scout registration/profile synchronization and task team API | `fieldpulse/scout_registration.py` |
| Assignment API compatibility | `fieldpulse/scout_assignment.py` |
| Project conversion, coverage, navigation and task status | Existing `fieldpulse/project_alignment.py`, `project_contract.py`, `project_locations.py` and Field Task controller |
| Quotation/payment rules, IPN verification, reconciliation, deposit gate and withdrawal | `fieldpulse/payments.py`, `payment_rules.py` |
| Website payment action routing | `fieldpulse/customer_payments.py` |
| Disputes, approved reports, customer settings and deletion requests | `fieldpulse/commerce.py` |
| 13 DD schemas and relevant controllers | `fieldpulse/fieldpulse/doctype/dd_*/` |
| Customer request and Field Request native fields | Their existing DocType JSON files |
| Desk forms, assignment dialog, list view and quotation actions | Corresponding DocType `.js` and `_list.js` files |
| Quotation print format | `fieldpulse/fieldpulse/print_format/diaspora_desk_quotation/` |
| External User custom fields, roles, permissions and Property Setters | `fieldpulse/production_configuration.py` and its managed configuration manifest |
| API aliases, document events and scheduling | `fieldpulse/hooks.py` |
| Ownership and deployment checks | `fieldpulse/native_ownership.py`, `native_events.py`, `native_handover.py`, `configuration/native-ownership.json` |

All 29 audited Server Scripts have a disposition: 28 have native handlers; the quotation-specific currency amendment is a historical repair and must never be replayed automatically. The eight audited Client Scripts are mapped to their DocTypes; the disabled request-assignment script remains excluded. Native assets preserve the simplified assignment dialog without Responsibility and Location inputs.

## Production remains script-owned

No deployment, migration, production edit or script retirement was performed during this work. Local tests do not establish deployed parity.

API overrides delegate to Frappe's original Server Script executor while their live script is active, preserving the original permission and rate-limit checks. Native event handlers and Desk assets remain dormant until approved handover. Native payment mutating actions retain the production mutation-token check. Approved complete reports remain visible before balance payment; scout assignment requires a verified 50% deposit.

The historical website-to-backend generator tools now refuse to overwrite this native implementation. The duplicate `integrations/frappe` and `fieldpulse/production_commerce` trees have been removed from thenetwork-backend. Temporary script source and operational tools remain only in diaspora-desk. Native backend code and migration audit/test fixtures remain in thenetwork-backend.

## Approved deployment sequence

Do not set `dd_native_handover_approved` merely to bypass a failed migration. The owner must explicitly approve production handover after staging verification and rollback review.

1. Deploy this backend revision to a staging copy with matching production configuration and private settings. Take a complete database/files backup before migration.
2. With staging handover authorized, run normal Frappe migration. The pre-model patch checks script hashes/targets and native handler imports, rejects unknown active DD scripts, backs up schema and Custom Field metadata, and adopts the existing DD tables as standard app DocTypes. It deletes duplicate Custom Field metadata only; it does not delete documents or physical data columns.
3. Model sync loads native schemas, controllers, Desk assets and the standard print format. The post-model handover patch checks definitions again, preserves script and scheduler rollback definitions, stops the old reconciliation job, and disables the managed Server/Client Scripts. Configuration adoption skips the app-owned script/schema/print documents so it cannot re-enable them. Existing guarded project patches remain in their established order.
4. Verify account registration/login/recovery, request pagination/details/ownership, multi-project conversion and retry rollback, location revisions/navigation, simplified assignment, deposit enforcement and scout count, quotation acceptance/withdrawal, checkout/IPN/reconciliation, report access/download, disputes/settings/deletion and scout team/mobile task updates.
5. Verify exactly one reconciliation owner, all expected API aliases, original record counts/links and private settings. Retain a full backup and pre-handover app revision for rollback; restoring a production database backup must be coordinated with any payments received since that backup.
6. Only after staging passes and explicit production approval, repeat the controlled deployment on production and perform the same acceptance checks. Website compatibility copies can be removed after successful handover; that removal is not part of source integration.

The one-off `dd_amend_00028_currency` endpoint is preserved in the dated snapshot for audit, excluded from native API aliases, and disabled with the managed scripts at approved handover.

## Verification

Final local checks: 60 backend tests and 3 production-script rule tests pass; native Desk JavaScript syntax and Git whitespace checks pass. Existing payment settings values and credentials are preserved. The new-site currency default matches the recorded enabled currencies: KES, USD, GBP and EUR.

Offline backend tests cover existing project/payment behavior plus native schema/Desk coverage, trusted registration permissions, customer request pagination parity with the live definition, API transition ownership, mutation-token enforcement, approved-report access, changed/unknown production script rejection, rollback capture and scheduler retirement. Full Frappe model-sync and end-to-end staging acceptance remain required; no Frappe bench is available in this local Python environment.

The dated production snapshot and script ownership registry preserve the audited deployment boundary. They do not export customer documents, password values, API keys or payment settings values.

Framework behavior checked against Frappe v15 primary source: [API dispatch order](https://github.com/frappe/frappe/blob/version-15/frappe/handler.py), [Server Script execution and scheduler handling](https://github.com/frappe/frappe/blob/version-15/frappe/core/doctype/server_script/server_script.py), and [session CSRF storage](https://github.com/frappe/frappe/blob/version-15/frappe/sessions.py).
