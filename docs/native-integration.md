# Native backend integration

Production uses the native FieldPulse backend. Handover completed on **16 October 2026** and was verified through read-only live API checks on **26 October 2026**. See [production ownership](production-script-ownership.md) for the controlling policy and [verification evidence](production-handover-verification-2026-10-26.md).

All 29 DD Server Scripts and all eight DD Client Scripts are disabled recovery references. The checked DD schemas are standard FieldPulse DocTypes and the old script-owned Pesapal reconciliation job is stopped. Native source belongs in `thenetwork-backend`; the website's obsolete `integrations/frappe` tree and installer/mirror tools have been removed.

## Where the implementation lives

| Concern | Backend source |
| --- | --- |
| Customer registration and recovery bridge | `fieldpulse/customer_accounts.py` |
| Customer request listing, details submission, ownership and source locations | `fieldpulse/customer_requests.py` |
| Details publication, validation, next actions and notifications | `fieldpulse/request_details.py` |
| Scout registration, admission and access | `fieldpulse/auth.py`, `scout_access.py`, `scout_registration.py` and Scout Application/Profile DocTypes |
| Assignment API compatibility | `fieldpulse/scout_assignment.py` |
| Project conversion, coverage, navigation and task status | Existing `fieldpulse/project_alignment.py`, `project_contract.py`, `project_locations.py` and Field Task controller |
| Quotation/payment rules, IPN verification, reconciliation, deposit gate and withdrawal | `fieldpulse/payments.py`, `payment_rules.py` |
| Website payment action routing | `fieldpulse/customer_payments.py` |
| Disputes, approved reports, customer settings and deletion requests | `fieldpulse/commerce.py` |
| Standard DD schemas and relevant controllers | `fieldpulse/fieldpulse/doctype/dd_*/` |
| Customer request and Field Request native fields | Their existing DocType JSON files |
| Desk forms, assignment dialog, list view and quotation actions | Corresponding DocType `.js` and `_list.js` files |
| Quotation print format | `fieldpulse/fieldpulse/print_format/diaspora_desk_quotation/` |
| External User custom fields, roles, permissions and Property Setters | `fieldpulse/production_configuration.py` and its managed configuration manifest |
| API aliases, document events and scheduling | `fieldpulse/hooks.py` |
| Ownership and deployment checks | `fieldpulse/native_ownership.py`, `native_events.py`, `native_handover.py`, `configuration/native-ownership.json` |

All 29 audited Server Scripts have a disposition: 28 have native handlers; the quotation-specific currency amendment is a historical repair and must never be replayed automatically. The eight audited Client Scripts are mapped to their DocTypes; the disabled request-assignment script remains excluded. Native assets preserve the simplified assignment dialog without Responsibility and Location inputs.

## Routine changes and deployment

1. Make backend changes in the native modules, standard DocTypes/controllers, hooks, scheduling and Desk assets. Website and mobile changes belong in their own repositories.
2. Run checks appropriate to the change. Use a backed-up staging site for real Frappe model sync, permissions, workflow and rollback checks; verify affected mobile flows on a physical phone.
3. Deploy the reviewed native revision, run normal Frappe migration when required, build affected assets and verify the deployed behavior. Coordinate API/schema changes with compatible website/mobile releases.
4. Preserve customer records, historical payment currencies, source/evidence links, task pins and private configuration. A local test or source change does not establish that a feature has been deployed or activated.

Do not update or re-enable retired site scripts, recreate website installers, run old mirror generators over native source, change the handover approval flag, or manually rerun handover/retirement patches for a routine update. Do not delete disabled recovery records without explicit cleanup approval.

## Compatibility and audit

`fieldpulse/configuration/native-ownership.json` maps the historical script definitions to their native owners. `docs/production-snapshots/2026-10-16.json` retains the dated audit. They are recovery/audit inputs, not instructions to restore script ownership. Historical handover patches retain their approval and parity guards for migration history; completed production patches are not a deployment checklist for new features.

The one-off `dd_amend_00028_currency` repair remains excluded from native API aliases and must never be replayed automatically. Compatibility aliases and guarded legacy delegation remain in code for transition/recovery; their presence does not mean the disabled scripts currently own production.

The simplified assignment dialog omits Responsibility and Location inputs. Assignment requires the verified 50% deposit. Customers may review the complete approved report before paying the balance. Preserve those rules when changing integrations.

Feature guides, including [scout admission](scout-admission.md), describe source behavior and their own rollout checks. Completed native handover does not establish deployment of every later feature.
