# Scout questionnaires, review and client reporting

For the streamlined version 2 implementation and its disabled-by-default rollout gate, see [questionnaire-streamlining-implementation.md](questionnaire-streamlining-implementation.md). The earlier questionnaire behaviour described below applies to version 1 assignments. Production script ownership remains governed by `production-script-ownership.md` and `native-integration.md`.

## Source and installation

The supplied Diaspora_Desk_Revised_Scout_Questionnaires.pdf is represented in fieldpulse/configuration/scout-questionnaires.json, including its SHA-256 and exact service question labels/details. Native installation creates 15 Published FP Questionnaires, 75 service questions, and the shared visit/final-evidence questions (150 FP Question records total). Each service keeps its required photo-and-video question. Normal Frappe migration runs this idempotent installer after model sync. No website installer or retired site script is used.

Services: land/plot; property/building; construction progress; business/shop; vehicle; equipment/funded asset; adult enrolment; university fees; adult attendance; adult clinic; document comparison/issuer confirmation; receipt confirmation; purchase/delivery; general site visit; merchant survey/interviews.

## Coordinator: before dispatch

1. Open the Field Request. Clear service wording such as a plot check selects its published template automatically. Ambiguous wording requires an explicit Scout service selection; adult services require adult/university context for automatic selection.
2. Save to load the template. Review Selected service checks against the client request. The full template starts selected; remove irrelevant checks. Shared S1-S4 and the mandatory service media question are retained by the server.
3. Confirm Selected checks match the agreed client request. Changes to the service/checks clear an existing confirmation. Existing deposit and verified-location gates still apply.
4. Assign the scout. The Field Task records the selected template/version, question codes and a snapshot of the full client request, task scope, clarifications and evidence tasks. A new published version does not change an existing assignment.

Existing assigned tasks and offline drafts continue on their recorded questionnaires. New service allocations use this library. Reassigning or upgrading questionnaires after work has begun needs a separate operational review; this release does not rewrite collected work.

## Scout app

The revised questionnaire checks a current location and accuracy against the assigned site's geofence before Start. Location issues can be sent to the coordinator as an incomplete visit. The arrival record contains device/site coordinates, radius, accuracy, timestamp and task/scout identity; the backend recomputes the result.

Displayed questions require findings or explained exceptions. Source statements, visible concerns and requested demonstrations have follow-up fields. Photos and short videos are captured inside service questions and captioned. Draft answers, captions, arrival and final-card entries are stored in the account's SQLite database. Schema v5 upgrades retain existing offline data.

Submit opens the full-request review card. Coverage has no preselected answer. Partly/No requires outstanding checks and follow-up text. Missing mandatory media/checks uses Send incomplete task for review with a reason. A Yes declaration is still subject to coordinator review.

Sync creates an owned server draft, sends answers, uploads and verifies media, and only then finalizes the response. Failed work remains queued. An incomplete response preserves all review reasons; it is not marked normally complete. Rework creates a fresh response after sync while retaining the old submission and review history.

## Coordinator: submissions and report

1. In Field Operations, use Scout submissions / Review scout submissions. The response view brings together the request, scope, clarifications, arrival, answers, media, final coverage and review reasons. Field Task and response lists show review flags/reasons.
2. Open media through the protected preview action. Approve or Request rework, with notes comparing the evidence to the full request. Approval records the reviewer/time and completes the task through the existing aggregate workflow.
3. Once every active task is approved and the Diaspora Request is Completed, use Prepare client report on that request. This creates/reopens a draft DD Service Report populated from reviewed findings, source statements, limitations and final observations.
4. Edit the summary and findings for the client. Select permitted photos/videos and review client-facing captions. Confirm the evidence selection. Explain any withheld or unresolved evidence in Limitations.
5. Generate report PDF. Selected photos appear in the PDF; selected videos are referenced and downloadable in the portal. Preview the file and change the report to Approved only after the report is ready for the client. Editing narrative, captions or selection after generation requires regeneration before approval.
6. Approval publishes the complete PDF and selected media to the owning client's portal. Approved reports are locked; corrections use a new version. The client reviews/downloads first, then pays the 50% balance if satisfied or raises an issue.

Only approved reports are exposed. Evidence downloads require both request ownership and explicit release in the approved report, and validate the approved source submission. Object integrity is checked against the verified upload before inclusion/download. The balance requires completed fieldwork, a published approved report and the verified deposit.

## Rollout and acceptance

Deploy the backend through the existing native Frappe Cloud process, run normal migration and build the Desk assets. Confirm 15 service templates exist and that the coordinator can read questionnaire/questions, scout responses and evidence. Any site-specific Custom DocPerm overrides need staging verification. Keep the existing native handover configuration and disabled script records as they are.

Build and distribute an updated native mobile binary: recording permissions changed. Publish the client website after the backend endpoints/schema are available. Retain the normal full site/database/files backup and pre-release revisions.

Local validation covers backend policy/install/permissions/payment/report tests, real SQLite migration/pull/draft/media/final review, sync failure/idempotency cases, TypeScript and an Android bundle, plus portal download/browser checks. A fictional PDF layout sample is generated from the report template.

Before production rollout, exercise the full flow on a staging Frappe site and a physical phone: model sync, role permissions, land template mapping/selection, geofence inside/outside/accuracy/denied permission, camera photo and video permissions, offline app restart and sync retry, normal/partial/incomplete submissions, coordinator rework and approval, private R2 previews, PDF generation with photos, client PDF/video downloads before balance payment, cross-client denial, checkout and payment reconciliation. No local mock or bundle test establishes live Frappe/R2/Pesapal delivery.


### Client report download
The portal exposes one Download report action. It delivers a private ZIP containing a text-only report.pdf and coordinator-selected evidence under Photos/ and Videos/. The PDF lists supporting filenames and captions without embedded images. Approval, customer ownership, source submission QA and verified upload checks still apply. Individual evidence routes remain available for compatibility. Bundles are limited to 500 MB; each source upload remains limited to 100 MB. Deploy the backend and website together; no mobile update is required for this delivery change.


### Arrival, capture and later submission
For revised questionnaires, geofence status is calculated from the saved arrival record, not the location where the scout finishes or submits. Scouts can resume saved drafts and submit offline/at home without requesting another position. Each uploaded photo/video is independently checked against the assigned site using its capture GPS, accuracy and timestamp; missing, inaccurate and outside readings require an explained incomplete/review submission. Arrival exceptions can unlock the form only with an explanation and remain flagged for coordinator review. No exception is marked as verified presence. Coordinator review displays capture GPS status and accuracy. Capture uses foreground high-accuracy readings, not background tracking. Deploy backend and mobile together; verify permissions, GPS failure, on-site media, off-site media, offline draft reopening and submission from home on a physical phone before release.
