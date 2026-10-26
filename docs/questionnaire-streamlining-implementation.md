# Streamlined scout questionnaires: implementation and rollout

## Default library update ? 26 October 2026

V2 is now the standard questionnaire library. Normal installation and migration
install its 15 templates without `dd_questionnaire_v2_enabled`; that former flag
is ignored even if false. New project selection requires V2 (school fee version 5)
and does not fall back to V1. Normal installation no longer creates V1 templates.
The default Questionnaire and Question lists omit superseded shared publications.
Existing documents are retained and explicit project pins remain readable.
The separate `dd_scout_visit_workflow_enabled` setting still controls the optional
V3 camera/verified-visit workflow. Deploy this backend revision, run normal site
migration and build Desk assets; use the compatible V2 mobile application.
The historical rollout record below describes the earlier opt-in implementation,
not the current V2 activation requirements. No live deployment was performed by
this source change.


For the subsequent verified-arrival and separate collection workspace changes (template version 3), see [scout-visit-release.md](scout-visit-release.md). The version 2 implementation below remains supported for existing assignments.

Implemented locally on 24 October 2026 in `thenetwork-backend` and `DiasporaDesk/mobile`. Production has not been changed. The native backend owns production; retired scripts remain disabled. The simplified assignment dialog is preserved.

## Delivered behaviour

The version 2 catalogue retains the supplied [Scout Questionnaire Library](scout-questionnaire-library.md), with 15 services and 43 service question definitions. Each template has two opening questions and one optional closing question. Service-specific options, item checklists, conditional follow-ups, assigned demonstrations and confirmation methods replace the generic findings form. The earlier catalogue and renderer remain available for pinned version 1 tasks.

Coordinator configuration is resolved into the task's immutable request snapshot. It includes assigned item IDs, descriptions/reference values, permitted confirmation methods and evidence instructions. Missing checklist items, unspecified custom evidence policies, missing authorisation and invalid capture instructions prevent confirmation/dispatch. Changing settings clears the coordinator's prior confirmation.

Use **Questionnaire → Choose services for this site** on the Field Request to select one or more services sharing its site and access arrangements. A combined immutable questionnaire includes all selected services with opening/closing questions once. This deliberately uses one Field Task per scout/site bundle, rather than introducing a visit record spanning independently approved tasks. Separate sites/access arrangements remain separate assignments. Existing separately assigned tasks are not merged, and files cannot cross their response boundaries.

Use **Configure selected checks** to enter assigned areas, milestones, goods, approved fields or custom questions; expected values; quantity/demonstration flags; permitted confirmation methods; and any extra capture subjects/conditions. Optional service checks must be added to Selected checks and enabled in their configuration. Conditional comparisons require supplied prior reference material. General-visit custom questions require an explicit per-item media policy; Not applicable is offered only where the coordinator permits it.

The scout can reuse location/access explanations, pause authorised checks if authorisation is disputed, and submit a site-not-found attempt. Merchant refusal stops the remaining survey questions. Missing institutional/issuer records suppress the detail-confirmation branch.

Files are captured once and linked to question/item requirements with a description of the supported subject. Files, links and exceptions are separate concepts. Local SQLite version 7 adds the link table and semantic evidence type without rewriting prior drafts. A written confirmation can be a Document even if the selected file's MIME type is an image. Removing a link does not remove a shared file. Unused files can be removed before queuing.

Required evidence exceptions use the supplied reason list. Other requires explanation. Exceptions remain unavailable evidence and produce coordinator review reasons; they never fulfil requirements. The generated summary shows answers, skipped checks, missing/unavailable media and reuse counts, with links back to questions. Scouts do not repeat the findings in a coverage declaration.

Sync saves draft answers, uploads/verifies each file, replaces verified requirement links, then finalises the response. Link retries are idempotent, including a lost final submission acknowledgement. The server checks assigned requirement/type, scout/task/response ownership and verified upload state. Evidence from another response, including old rework, cannot satisfy a requirement. Version 2 dispatch and client protocol checks prevent the old renderer from silently handling new assignments.

Coordinator review shows item outcomes, evidence coverage and original limitations. Client-report preparation includes typed findings and deduplicates supporting files. Approved documents can be explicitly released into `Documents/` in the report ZIP, alongside `Photos/` and `Videos/`. Customer ownership, approved-source and integrity checks remain in place.

## Source map

- `fieldpulse/configuration/scout-questionnaires-v2.json`: version 2 source catalogue.
- `fieldpulse/scout_library.py`: pure configuration, conditional requirements and answer/exception rules.
- `fieldpulse/scout_v2.py`: default V2 installation, optional V3 visit workflow, site bundles, pinned configuration and verified evidence-link sync.
- `scout_templates.py`, `scout_submissions.py`, `evidence.py`, `scout_reports.py`, `api.py` and the affected standard DocTypes/Desk assets: integration with assignment, validation and reporting.
- Mobile `components/StreamlinedQuestionnaire.tsx` and `utils/streamlinedProtocol.ts`: version 2 rendering and offline validation.
- Mobile `db/database.ts`, `db/repository.ts`, `services/sync.ts`: additive SQLite migration, pinned form metadata, single-file links and staged sync.
- `tests/fixtures/scout-v2-contract.json`: the same answer/evidence cases run by Python and TypeScript. The mobile copy is under its `tests/fixtures/` directory.

`tools/build_scout_library_v2.py` reproduces the catalogue from the retained owner source and explicit declarative rules. Do not edit an installed published version in place; future changes require a new version.

## Current activation and acceptance

Version 2 is the default library in the current source. The former `dd_questionnaire_v2_enabled` flag is ignored. Optional V3 verified-visit dispatch remains controlled by `dd_scout_visit_workflow_enabled`. Follow normal native deployment; handover is complete.

1. Deploy additive source/schema support to staging through the established approved deployment process. Verify existing version 1 tasks, drafts and uploads still work with the default V2 library; keep optional V3 dispatch disabled until separately accepted.
2. Build/distribute the compatible mobile binary. Check the new screen on a physical phone: arrival exception, actual camera/video/document permissions, evidence reuse, draft restart, unlink/removal, offline queue/retry and rework.
3. On staging, run normal installation/migration to install the default V2 templates. Confirm the 15 service templates and current service-specific revisions. The services selector also creates missing single/composite templates on demand.
4. Verify coordinator role permissions and actual Frappe model sync. Configure a plot check, a property checklist, an authorised institution/issuer confirmation, a merchant refusal and a same-site service bundle. Verify unexplained gaps block submission, explained limitations stay flagged, and reference media is never demanded twice.
5. Exercise coordinator approval/rework, private storage previews, report generation and authorised client downloads. Verify source limitations remain after approval and each released file appears once in the ZIP.
6. Enable new version 2 assignments in production only after the compatible build and staging checks pass, following the native production deployment policy. Existing project and task pins do not automatically upgrade.

The former V2 flag cannot disable default V2 dispatch. If the optional V3 workflow must be rolled back, disable its visit-workflow flag while retaining support for already pinned tasks. Retain the additive schemas and compatible client. Do not run script retirement migrations or overwrite native code with historical website generators.

## Local verification

The backend suite includes catalogue/source parity, configuration prerequisites, immutable combined templates, shared Python/TypeScript answer cases and evidence ownership/type/idempotency checks. Mobile tests cover a real SQLite upgrade, pinned configuration, one-file/multiple-answer links, unlinking, foreign-file rejection, queued-work immutability, staged sync and account isolation. TypeScript and Android export are checked separately.

Local results: 204 backend tests pass; the version 2 shared-contract/SQLite test, legacy questionnaire test, account-isolation test and submission-sync test pass; TypeScript and Android export pass. Python test-only dependencies were installed under the ignored `.local/test-deps` directory. No production deployment, migration or native handover was performed.

Unverified photo/video capture locations require an explanation before submission; the scout can reuse the recorded arrival explanation. These uploads remain flagged for coordinator review even after the explanation is recorded.

These local checks do not establish actual Frappe model sync, live R2 delivery or physical-phone behaviour. Those remain the staging/release acceptance checks above.
