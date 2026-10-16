# Production configuration audit - 14 October 2026

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
- Conversion scripts must stay active on production until the backend migration replaces them. Backend adoption skips those temporary scripts and retires their production versions after native code is installed.
- Native DocType identity fields replace their temporary Custom Field definitions without deleting physical data columns. The pre-model-sync migration preserves and removes only duplicate metadata definitions.

## Deployment boundary

The current production implementation is site scripts. The prepared backend implementation is native Python. They implement the same project-ID contract but must not both own conversion after deployment. Deploy the backend and run migrations first, verify staging/production, then deploy the website. The website now supplies server-derived project IDs with location rows.

## Ownership

Website installers retain the production runtime definitions and quote design. Backend migrations adopt non-overlapping managed configuration from the same manifest, while native project_alignment/project_locations own conversion and scout metadata. Manual production changes after this capture need a fresh audit/export before a later deployment.

## Limits

This audit covers the Diaspora Desk and scout integration configuration named above. It does not claim an inventory of every unrelated Frappe app, scheduled job, workspace or operational/customer record. It does not infer how previously deleted records were created.
