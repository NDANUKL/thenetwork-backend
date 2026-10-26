# Historical production configuration audit ? 14 October 2026

This is a dated pre-handover audit, not current deployment guidance. Native handover completed on 16 October 2026 and was verified on 26 October 2026. Follow [production ownership](production-script-ownership.md) and [native integration](native-integration.md). The counts below describe the 14 October capture only.

Production was read directly using the authenticated Frappe API. Customer records and credentials are excluded from the checked-in configuration manifest.

| Configuration | Managed definitions |
| --- | ---: |
| Client Script | 7 |
| Custom DocPerm | 4 |
| Custom Field | 20 |
| DocType | 6 |
| Print Format | 1 |
| Property Setter | 31 |
| Role | 2 |
| Server Script | 22 |

## Findings

- Production has the project-ID conversion gate, exact coverage checks and retry serialization active. Live tests verified three separate projects, shared locations, duplicate rejection, unchanged references on retry, and rollback of invalid submissions.
- Before this audit, customer registration, details requests, ownership, scout profile/team APIs, readonly form rules, custom permissions and quotations were primarily maintained by website installers. The native backend alone did not contain every production definition.
- The configuration manifest now preserves every managed production script, custom field, property setter, custom permission and quotation print format, plus the DD custom DocTypes and required roles. It is also copied into the backend for migration-time adoption.
- Customer request listing comparison: no script difference.
- The live operations dashboard HTML, CSS and JavaScript match the native backend assets; no dashboard asset gap was found.
- Quotation HTML matches the website source. The backend manifest includes the live quotation DocTypes, validation and print format.
- At the audit date, conversion still used site scripts. The subsequent native handover replaced that ownership; the retired DD scripts are now disabled recovery references.
- Native DocType identity fields replace their temporary Custom Field definitions without deleting physical data columns. The pre-model-sync migration preserves and removes only duplicate metadata definitions.

## Deployment boundary

At the audit date, site scripts owned production and native Python was prepared for adoption. That transition completed on 16 October 2026. Current changes use the normal native deployment workflow; do not repeat the historical handover or reinstall script definitions. The website supplies server-derived project IDs with location rows.

## Ownership

The native backend now owns runtime definitions, quote design, conversion and scout metadata. The website installers mentioned by this audit were removed. Preserve the historical manifest/snapshot for recovery; audit the current affected definitions when preparing a later deployment.

## Limits

This audit covers the Diaspora Desk and scout integration configuration named above. It does not claim an inventory of every unrelated Frappe app, scheduled job, workspace or operational/customer record. It does not infer how previously deleted records were created.
