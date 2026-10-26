# Questionnaire streamlining: review and implementation plan

Review date: 24 October 2026. Original review status: proposal only; no runtime, mobile, production or migration changes had been made at that point.

Implementation update: source changes are now documented in [questionnaire-streamlining-implementation.md](questionnaire-streamlining-implementation.md). The text below remains the original review. Same-site services use a combined questionnaire/task rather than grouping independently assigned tasks into a new visit DocType.

The owner's **Scout Questionnaire Library** is the target behaviour. A verbatim UTF-8 copy is retained in [scout-questionnaire-library.md](scout-questionnaire-library.md). This supersedes the earlier PDF as the proposed source for a new version, without changing existing assignments.

## Recommendation

Implement a version 2 questionnaire protocol across the native backend and `DiasporaDesk/mobile`. This needs coordinated changes to coordinator configuration, structured answers, evidence storage, offline sync, validation and reporting. Editing question labels or removing the mandatory-video flag alone will not implement the supplied library.

The scout flow should be: task information, two opening questions, applicable assigned service checks, one optional closing question, then an automatically assembled submission summary. Explain an obstacle once and reuse it. Capture a file once and link it to the checks or checklist items it actually supports.

## Findings from the current repositories

| Area | Current implementation | Required change |
| --- | --- | --- |
| Library | `fieldpulse/configuration/scout-questionnaires.json` contains 15 services, each with five service questions and exactly one `mandatory_evidence` question. | Transcribe the supplied library into a new version with its actual question counts, service-specific options and conditions. |
| Publication | `scout_templates.install_templates` creates protocol 1 checks. `FPQuestionnaire.validate` requires S1–S4, S_EXTRA and exactly one mandatory photo-and-video question. | Add version-aware publication validation. Version 2 must support two opening questions, an optional closing question, and explicit per-question media policies. Keep version 1 validation intact. |
| Assignment | `scout_templates.prepare_project` selects service questions and forces retention of the mandatory-media question. `DD Scout Check` stores only a question link and label. | Configure checklist items, reference values, conditional checks, capture instructions and permitted confirmation methods before assignment. Validate configuration and pin it on the task. |
| Answer choices | `mobile/utils/scoutProtocol.ts` supplies generic service results; `RevisedQuestionnaire.tsx` adds generic source, concern and demonstration controls. | Render each question's specific choices and assigned item rows, with only relevant follow-up controls. |
| Repeated text | Both `scout_protocol.answer_issues` and mobile `questionIssues` require written findings for S1/S2 and most service answers. | Require text only when the library asks for it. Allow references to a recorded location/access explanation. |
| Evidence | Backend and mobile require both Photo and Video for `mandatory_evidence`. Other questions display a generic invitation to attach media. | Display the exact configured requirement for every question, including no media. Derive conditional requirements from the answer or checklist item. |
| Reuse | Local `attachments.question_response_id` and server `Field Evidence.question_response` associate a file with one answer. Submission validation queries evidence through that association. | Introduce explicit links from a single evidence object to multiple question/item requirements. Repeating an ID in answer JSON alone is insufficient. |
| Written confirmation | `fieldpulse/evidence.py::_validate_question_response` accepts only Photo/Video for `service_check`. The revised mobile screen exposes photo/video capture. | Support approved document attachment for institutional/issuer confirmation as well as authorised photo or recorded verbal confirmation. |
| Exceptions | A generic incomplete reason and concern-specific `media_unavailable_reason` exist. | Record exceptions against each required attachment subject, using the supplied reason list. An exception permits explained submission but never fulfils the requirement. |
| Summary | The mobile final card asks Yes/Partly/No coverage plus additional text and sometimes an incomplete reason. | Generate completed/blocked checks, fulfilled/missing/excepted evidence and reused evidence from the answers. Avoid making the scout repeat findings. |
| Review/report | `scout_submissions.py` gathers evidence by its owning answer; `scout_reports.py` reads generic result/text/source/concern fields. | Include checklist outcomes, linked evidence, recorded sources and exceptions in coordinator review and client-report preparation. Deduplicate released files. |
| Multiple services | A Field Task is pinned to one questionnaire/version and scope. | Add a site-visit grouping model for several service tasks at one site if they are assigned together; share opening/closing records and evidence within an explicitly authorised visit. |

Existing assets worth retaining: questionnaire version pinning, client-request snapshots, saved arrival records, per-file capture metadata, account-scoped SQLite, upload-before-finalisation sync, coordinator approval/rework and controlled client evidence release. Preserve their behaviour while extending the protocol.

This is a local source review. It does not establish the deployed site's current behaviour or migration state. `docs/scout-questionnaires-and-reports.md` contains rollout language that differs from the explicit production ownership policy; use `docs/production-script-ownership.md`, `docs/native-integration.md` and the ownership registry as the controlling deployment guidance.

## Proposed scout experience

1. **Task information.** Show reference, service(s), client questions, assigned checks, address/pin/landmarks, reference files or prior reports, contact/access arrangements, authorisation/restrictions and the media summary. Reuse existing reference data. Expand the existing snapshot, which currently captures request/scope/clarifications but not all these structured details.
2. **Location and access.** Ask whether the site matches and what access was obtained. Yes/full access needs no repeated explanation. No/uncertain location requires the specified photo or an evidence exception. A site-not-found attempted visit can proceed directly to review. Partial/no access blocks only affected checks; exterior or other possible checks remain available.
3. **Assigned checks.** Use the supplied options. Render item rows for areas, milestones, goods, identifiers, assets, document fields and delivery items. Show source role/office once per source and reuse it where appropriate. Keep direct observation distinct from reported information.
4. **Evidence beside the relevant requirement.** Show the subject and media type. Offer capture, link an existing visit file, or unable to capture. A link must identify what subject/item the file supports; coordinator review can reject unsuitable coverage. No duplicate upload or recording is required.
5. **Optional closing note.** Ask only whether anything else is relevant. Do not require a second account of findings, obstacles or follow-up already recorded.
6. **Submission summary.** Show completed checks, unchecked items and reasons, evidence coverage, reused files, exceptions and unexplained gaps. Each entry links back to its question. Explained limitations can be submitted for coordinator review, visibly unresolved. An unverified visit must never be labelled fully verified.

Keep the saved arrival/capture-location policy separate from the answer to whether the site matches the brief. A GPS result cannot automatically answer that question. Preserve the ability to finish text and submit later from home.

## Version 2 contract

### Template and assignment

Use explicit declarative metadata rather than inferring behaviour from question wording. Pin both template and resolved assignment configuration; later coordinator edits must not silently change the form shown to an already assigned scout.

- Stable service/question/item IDs, protocol version, exact wording, answer type and allowed outcomes.
- Display rules for assigned demonstrations, issuer/representative questions, previous-report comparisons and service-specific branches.
- Assigned checklist items with reference descriptions/values and any requested quantities/readings.
- Conditional required fields and explanation rules; supported unable outcomes for every assigned check.
- Evidence requirements with stable requirement IDs, subject instructions, media type, applicable answer/item conditions and required coverage. Explicit `none` is valid; unspecified is not.
- Prerequisites: recorded authorisation/institutional arrangements where required, approved fields and the selected confirmation method. A general free-text evidence brief does not replace this configuration.

Extend `DD Scout Check` (or associated standard child DocTypes) for coordinator configuration. Add the required task/visit snapshot fields and permission rules. Template defaults and task additions must be resolved server-side before dispatch; the scout cannot decide which evidence is mandatory.

### Answers, explanations and sources

Use typed answer data for single choice, multiple choice, text, field comparison and checklist rows. Store item outcomes separately; do not pack several asset statuses into a single findings paragraph.

Allow an answer/item to refer to a recorded explanation or source. Validate that those references belong to the same authorised visit and make sense for the blocked check. Record an office/role and attributed information when used. Persist branches so hidden stale values do not fulfil an inactive requirement or leak into reports.

### Evidence and exceptions

Keep one physical file record with its identity, upload verification, capture metadata and caption. Add a many-to-many evidence-link relation containing the response/question/item and requirement covered. Keep version 1's existing direct association for compatibility.

Store exceptions independently of files: requirement ID, reason code, optional detail and reusable explanation reference. Reasons are photography/recording prohibited; permission refused; subject/item inaccessible; site/item not found; safety concern; technical problem; other with explanation.

Distinguish `not required`, `required and missing`, `attached and verified`, and `unavailable with explanation`. Here, verified upload/location does not establish that the file depicts the required subject; that remains part of coordinator review. Never infer fulfilment solely from a nonempty attachment ID, caption or exception reason.

Validate task/visit ownership, question membership, item membership, media type and upload integrity for every link. Do not allow evidence from another scout, visit, client or obsolete rework response to satisfy a requirement merely because its ID is known. Unlinking one answer must not delete a file still used by another; deleting a shared file must expose the affected requirements.

### Same-site services

Recommended design: a visit groups explicitly selected compatible Field Tasks for the same scout and site/access arrangements, while retaining each task's service questionnaire, scope, response and approval history. Shared opening/closing records live on the visit; evidence can be linked to its authorised member tasks. This requires a standard visit DocType, membership rules, mobile visit persistence and grouped review/navigation, not just grouping screens by coordinates.

Use a separate location/access section for another site or different access arrangements. Do not merge unrelated historical tasks automatically. Validate membership and completion independently of payment and project rollups. Approval of one task must not complete unfinished companion services.

## Service-specific acceptance cases

| Service | Essential acceptance condition |
| --- | --- |
| Land | Three checks; photo coverage for identity/boundaries, use and entrance; reuse images; no routine video or legal boundary/ownership conclusion. |
| Property | Only assigned areas/features; area overviews and necessary issue images; one walkthrough only when assigned; function videos only where configured. |
| Construction | Milestone rows; comparison only with supplied prior material; issue images conditional on issues; representative confirmation only when assigned; one assigned walkthrough. |
| Business | Storefront/signage coverage; per-item availability and condition; no item photo for unobserved/unavailable goods; issue photos only when needed; representative answers conditional. |
| Vehicle | Assigned identifiers and condition views; inaccessible sections explained; video for demonstrated assigned functions, with one clip permitted to cover several; not-demonstrated requires explanation. |
| Equipment | Asset/identifier rows; photo coverage of present assets; damage photos conditional; demonstrated assigned functions require video. |
| Adult enrolment | Authorisation gate; approved fields; confirming office/role recorded once; only the selected written/photo/verbal confirmation method. |
| University fees | Record-search outcome and approved payment fields; no photograph of a nonexistent/refused record; selected confirmation method only. |
| Adult attendance | Assigned period/activity and institution's answer; no student/classroom media; selected confirmation method only. |
| Adult clinic | Approved visit/payment details only; selected confirmation method; no diagnosis, treatment details or patient images. |
| Documents | Supplied-file comparison requires no new photo; physical inspection requires specified fields; issuer branch only when assigned; matching does not imply authenticity. |
| Receipts | Reuse supplied receipt; issuer confirmation and field differences; photograph only permitted issuer confirmation when that method is selected. |
| Purchase/delivery | Item/quantity/specification rows; damage photos conditional; delivery details and demonstrations only when assigned; reusable demonstration clips. |
| General visit | Explicit custom questions, outcomes, sources and media instructions; block assignment with an unspecified evidence policy or missing required capture subject. |
| Merchant survey | Stop after declined/ineligible/unconfirmed eligibility; approved profile/checklists/interview questions; declined-to-answer supported; no default media or transaction-screen capture. |

## Implementation order and completion gates

### 1. Catalogue and shared contract

Transcribe all 15 services from the retained source into a new catalogue version. Define the metadata, answer, source, exception and evidence-link schemas and build common JSON test cases for Python and TypeScript. Include declaration/condition validation so malformed configuration cannot be published or assigned. Preserve the earlier catalogue as a historical fixture/source for existing version 1 records.

Gate: every source question, option, conditional branch and capture instruction is accounted for; the old immutable template hash and validation paths remain supported. This phase must not publish version 2 to active assignment automatically.

### 2. Backend configuration and validation

Change `scout_templates.py`, `scout_protocol.py`, the questionnaire controller, question/configuration DocTypes, Field Request Desk controls and assignment snapshot. Add visit grouping and evidence links/exception persistence. Update `evidence.py`, `scout_submissions.py`, `api.py` and relevant permissions/sync payloads. Resolve requirements and review reasons on the server from pinned metadata and trusted uploaded files.

Gate: invalid assignment configurations are rejected; valid explained attempted visits can be submitted; conditional/photo-only/no-media/document cases behave correctly; forged links and cross-account access fail. Old templates and submissions retain their original rules.

### 3. Mobile form and offline sync

Change `components/RevisedQuestionnaire.tsx`, `utils/scoutProtocol.ts`, `db/repository.ts`, SQLite migrations, sync payload ingestion and `services/sync.ts`. Dispatch the renderer explicitly by protocol capability: currently `app/task/[id]/questionnaire.tsx` sends all `service_check` questions to the same revised renderer. Add typed choice/checklist controls, conditional follow-ups, source/explanation reuse, document attachment, a visit evidence picker and generated summary.

Persist evidence objects and links separately; upload each file once, then sync verified links before finalising all affected responses. Retain queued-work immutability, retry idempotency, account isolation and rework history. Draft edits must not resurrect removed links. Unsupported clients should receive a clear update requirement before version 2 work is assigned or opened.

Before writing Expo code, follow `DiasporaDesk/mobile/AGENTS.md` and read the exact Expo v57 documentation. This review did not change mobile code.

Gate: real SQLite upgrade tests retain old drafts/queues; capture-once reuse survives restart/offline sync; unlink/delete, failed upload, link retry and document confirmation behave correctly; backend and mobile pass the same protocol fixtures.

### 4. Coordinator review and client report

Extend submission review and `scout_reports.py` to show per-item outcomes, source attribution, reused evidence coverage and unmet/excepted requirements. Update the Desk response view and report generation/selection paths. List each physical file once in client exports while retaining every supported finding. Review acceptance does not erase the original limitations or mark an exception fulfilled.

Gate: approving one same-site service does not approve the others; rework preserves the original response; private downloads and client release restrictions still hold; generated reports retain limitations and avoid unsupported authenticity/ownership claims.

### 5. Staging and controlled rollout

Deploy additive backend/schema support first with version 2 assignment gated off. Verify existing clients and version 1 submissions. Distribute a compatible mobile build, verify protocol capability, then explicitly enable version 2 for new assignments. Existing pinned projects need an explicit reviewed upgrade for future tasks; do not force-upgrade their assigned/in-progress tasks.

Follow `docs/production-script-ownership.md`, `docs/native-integration.md` and `fieldpulse/configuration/native-ownership.json`. Runtime source belongs in native Python/standard DocTypes. Temporary production script source remains in `diaspora-desk`; if a corresponding live script needs a change, back up and mirror the targeted definition there and in the backend, then verify it. Do not run old website generators over native source. Source implementation does not authorise native handover or retirement migrations.

Stage real Frappe model sync, role permissions and physical-phone GPS/camera/video/document permissions. Exercise all service families, missing-site and denied-access visits, merchant refusal, same-site multi-service reuse, offline restart/retry, coordinator rework, report downloads and cross-client denial. Preserve the simplified assignment dialog without Responsibility or Location inputs, and the verified-deposit assignment gate.

Rollback stops new version 2 assignments while retaining the server/client support needed for already pinned version 2 work. Do not roll back additive schemas or erase submissions. Native production handover remains a separate owner-approved operation.

## Review outcome

Proceed with a coordinated version 2 implementation using the supplied library as the source of truth. The highest-value changes are conditional structured answers, removal of blanket video requirements, per-requirement exceptions and genuine single-upload evidence reuse. All four need to land together before claiming the scout flow implements the new library.
