# Verified arrival and flexible field collection

Implemented locally on 24 October 2026. This extends the streamlined questionnaires with template version 3 and visit workflow version 2; it keeps questionnaire protocol 2 for the typed answers. No production changes or native handover were performed.

## What changed

- The task brief is available before arrival. Answers and the capture workspace unlock only after a fresh GPS reading passes the actual assigned radius and accuracy checks. The historical testing-radius override is not used for new workflow assignments.
- A failed arrival has its own explained review submission. It contains no questionnaire answers or media, never unlocks the questionnaire and cannot be approved as completed fieldwork. Coordinators can arrange a corrected assignment or request rework when appropriate.
- After verified arrival, scouts can switch between **Checks**, **Capture evidence** and **Complete findings**. Quick outcomes and short notes are saved immediately. Exact reference/quantity/office-response reminders appear before leaving. Notes remain available as findings to expand rather than re-enter.
- The capture workspace shows assigned subjects before the corresponding answers are written, including conditional instructions. Known outcomes remove irrelevant capture requests. Visual services have assigned photos and an overview video; registry/institution work retains explicit permitted written/photo/verbal confirmation. Explained missing evidence remains unfulfilled.
- Automatic editable file labels come from the assigned subject/item. Reuse is a selection of supported checks; there is no new caption to type for each link. Extra description is required for an unclear subject, or for an issue not already described in its linked finding.
- The new workflow uses `expo-camera`. GPS is sampled immediately before the photo shutter or recording start, with sample time and capture time stored separately. There is no continuous/background tracking. Missing, inaccurate, off-site or stale capture GPS preserves the file but needs an explained coordinator review.
- Imported documents retain import provenance and do not acquire a claimed capture time/GPS from the place of attachment.
- Finishing written answers, file descriptions and submission later does not request another arrival reading or replace the saved arrival. Offline SQLite v8 preserves previous drafts and adds the new capture metadata. Capture-only records do not inflate the answered-question counter.
- Coordinator review shows capture origin, sampling time and subject details. The client report starts with automatic labels plus any recorded file description; the coordinator can refine client-facing captions.

## Compatibility and activation

Versions 1 and 2 remain immutable; existing assigned work/drafts keep their earlier workflow. A new version 3 task snapshot pins `visit_workflow_version: 2`, resolved questions and the assigned site reference/radius. Older clients receive an update requirement for these new assignments.

Keep both `dd_questionnaire_v2_enabled` and `dd_scout_visit_workflow_enabled` off until the compatible backend/schema and mobile binary have passed staging. The new flag enables installation/selection of version 3 templates; it does not upgrade existing project pins. On an approved staging deployment, enable both flags and run `fieldpulse.scout_v2.install_templates`, or use the services selector to install the chosen templates on demand. Existing projects need a reviewed selection of the new service revision for future tasks.

A **new native mobile binary is required** for `expo-camera` and its camera/microphone permissions. An Android JavaScript export is not a distributed native build. Disable new workflow dispatch for rollback while retaining the schemas/client support required to finish already pinned work. Do not retire live scripts or run handover migrations as part of this feature.

Follow `production-script-ownership.md` and `native-integration.md` for any deployment. These source changes do not establish live-site parity or authorise production handover.

## Verification and physical acceptance

Backend regression tests cover the strict-versus-legacy radius distinction, GPS accuracy/time, forged arrival status, locked failure route, later submission, default visual video coverage, routine automatic captions, issue clarification, capture provenance and preserved older templates. Python and TypeScript share `tests/fixtures/scout-visit-contract.json`.

Mobile tests use real SQLite to check pre-arrival write/capture rejection, immutable saved arrival/capture metadata, later queueing, a separate unanswered arrival exception, automatic evidence reuse, imports without invented GPS and migration compatibility. The existing questionnaire/account/sync suites remain required.

Local results: 216 backend tests pass. Mobile TypeScript, visit-workflow, streamlined-questionnaire, legacy questionnaire, submission-sync and account-isolation checks pass. The coordinator review rendering test verifies the unanswered exception route, hidden approval action and escaped capture details. Android export passes; this is a bundle check, not a native APK or device acceptance test.

Before rollout, test a plot/construction visit, a shop and a registry on a physical phone. Verify actual camera/microphone/GPS permissions, capture GPS at the shutter/start rather than the end of a video, denied/weak indoor GPS, video stop/cancel/background behaviour, camera failure/retry, offline restart in each workspace, save/complete from home, unlink/removal, coordinator rework and report release. Verify native Frappe model sync and live R2 verification on staging. Local tests and bundling do not substitute for these checks.
