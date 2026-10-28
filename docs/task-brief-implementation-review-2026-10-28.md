# Task Brief implementation review ? 28 October 2026

## Verdict

**Partially implemented; not ready for release or an end-to-end completion sign-off.** The new Task Brief path is a real, independent architecture, not just a renamed questionnaire. However, a confirmed website defect blocks new request submission, several mobile/review edge cases fail, and the requested removal of the old architecture is incomplete.

This audit compares the supplied specification with the current local source in `thenetwork-backend`, `diaspora-desk` and `DiasporaDesk/mobile`. It excludes the historical `DiasporaDesk/backend-review` checkout. No application source was changed during this review. The production ownership policy remains controlling; disabled DD recovery scripts are not candidates for questionnaire cleanup.

Local checks are not deployment evidence. No staging migration, real Frappe transaction/permission run, physical Android/iOS run or live production verification was performed in this audit.

## Confirmed defects and gaps

### R1 ? Release blocker: freshly signed website requests fail submission

Sources: `diaspora-desk/src/lib/ai.js:367`, `src/app/api/assess-request/route.js:294`, `src/app/api/submit-request/route.js:257` and `:413`, `src/lib/assessment-proof-core.mjs`.

Assessment generation includes `assessment_status` in the object signed by `createAssessmentProof`. The submission route rebuilds `trustedAssessment` without that property and then verifies the original signature against the rebuilt object. The signing function authenticates every object key. Consequently the new generated assessment and submitted assessment cannot match, even when the client changes nothing.

Reproduced using the actual `normaliseSubmission` function and actual proof creation/verification functions, with a supported four-category assessment containing a Task Brief. The original object verifies; its normalized submission throws `Assessment proof does not match this request`. This prevents the client request from reaching Frappe through the normal website flow.

Fix: validate and preserve the same eligibility field in the signed contract on both routes. Add an integration regression from generated assessment through normaliseSubmission and proof verification, not only isolated proof tests.

### R2 ? High: editing an access-issue reason can crash the task screen and task loading

Sources: `mobile/components/TaskBriefScreen.tsx:31`, `:58`; `mobile/utils/taskBrief.mjs:75`; `mobile/db/repository.ts:418`.

The access reason is saved on every keystroke. When the user clears it, `access_issue` becomes an empty string. The completion evaluator throws an exception for an empty/whitespace reason instead of returning an incomplete result. It is called directly while rendering the task screen, outside an error handler. Task-list progress calculation calls the same evaluator on the saved draft.

Reproduced with both empty and whitespace draft reasons: `Access issue requires an explanation` is thrown. Because the draft can already be saved, reopening the task does not necessarily resolve the problem; task-list loading can also fail.

Fix: incomplete drafts must remain renderable. Return a missing-reason validation error, and reserve exception throwing for corrupt contracts. Test typing, clearing, restarting and reopening this draft.

### R3 ? High: a lost acknowledgement followed by approval leaves a permanent queued submission

Sources: `mobile/services/taskBriefs.ts:62-68`, `:91-94`; `mobile/db/repository.ts:251`; `fieldpulse/task_brief_workflow.py:181-189`.

The server correctly returns Submitted for an already-submitted UUID. But mobile checks the task status before calling that idempotent endpoint. If the server accepted the final submission, the acknowledgement was lost, and the coordinator approves it before the next sync, the fresh pull reports Approved. Mobile refuses to reconcile it, leaves queued=true/submitted=false, and counts it as outstanding work indefinitely. Cancelled/withdrawn queued work also lacks a terminal queue reconciliation path.

Reproduced with the existing SQLite-backed retry harness and actual `syncBriefs`: after simulating final acceptance, lost acknowledgement and an Approved task, the retry returns rejected=1 and the draft remains queued.

Fix: distinguish reconciliation of an already accepted UUID from a new submission. Preserve closed-task work, but clear/archive the queue with its authoritative terminal outcome. Test approval, cancellation and clarification between acceptance and retry.

### R4 ? High: clarification instructions do not reach the active Task Brief screen

Sources: `fieldpulse/task_brief_workflow.py:216`, `fieldpulse/scout_notifications.py:127`; `mobile/services/sync.ts:121`, `services/taskBriefs.ts:18`, `components/TaskBriefScreen.tsx`, `app/(tabs)/tasks.tsx:172`.

Coordinator notes are stored and downloaded as review_feedback. However, loadBrief does not select that field and TaskBriefScreen never renders it. The task list displays only a generic Rework required label and rework type. The new review_response path also does not invoke queue_rework; the generic task-update notification hook does not emit a rework notification for Submitted -> In Progress.

A scout receives an editable revision but no actionable explanation of what to correct through the normal mobile task flow.

Fix: show coordinator notes and review decision prominently on the revision, preserve their provenance, and connect the new review action to the durable rework notification path. Test actual review-to-sync-to-screen delivery.

### R5 ? High: follow-up check subsets are rejected despite existing coverage

Sources: `fieldpulse/project_alignment.py:375-381`, `fieldpulse/task_brief_workflow.py:236-258`.

assign_project_scouts requires every required check to be present in the current API call. It does not combine proposed checks with other active/approved allocations. Initial multi-scout allocation works when submitted together. Incremental allocation and a follow-up visit for only selected checks do not work as the additional-evidence flow suggests.

Reproduced with a two-check brief: assigning only the second check fails with `Allocate every required field check to at least one scout` before existing task coverage is queried. If the first check is already approved, including that scout again can create unnecessary repeated work because approved allocations are excluded from the reusable-active-task lookup.

Fix: calculate coverage using current compatible allocations plus the proposed changes. Preserve required-check coverage without requiring every follow-up call to repeat the entire brief. Test initial allocation, incremental allocation, cancellation and selective additional-evidence visits.

### R6 ? High rollout gap: existing assignments disappear without a conversion plan being executed

Sources: `fieldpulse/api.py:44`, `fieldpulse/patches/v1_0/task_brief_categories.py`, `mobile/services/sync.ts:69-77`.

The backend feed now filters out every task without task_brief_version. The migration changes category labels; it does not convert existing tasks. The mobile authoritative pull marks absent tasks Withdrawn and archives their old upload queues. A deployment onto a site with existing open questionnaire assignments therefore interrupts those assignments, even though their backend status was not explicitly cancelled.

This is documented as manual cutover work, so it is a known uncompleted release prerequisite rather than a claim that records are deleted. It still prevents the requirement to avoid unnecessary assignment disruption from being signed off.

Required before rollout: inventory open tasks and unsent device work; decide conversion/cancellation/reassignment explicitly; verify recovery and status outcomes on staging. Do not infer that a category migration converts assignments.

### R7 ? Medium specification gap: questionnaire architecture still exists in executable code and schemas

Sources: `fieldpulse/api.py:102`, `fieldpulse/scout_v2.py:29`, `fieldpulse/scout_protocol.py`, `fieldpulse/scout_library.py`, `fieldpulse/legacy_questionnaires.py`, the FP Questionnaire/Question/Question Option/Question Response DocTypes; `mobile/db/database.ts:17-23`, `mobile/services/sync.ts`, `mobile/db/repository.ts`.

The three runtime catalogues, publishers, project questionnaire editor and retired mobile screen components were removed. New assignments use independent brief/check storage and validation. Nevertheless, fresh mobile databases still create questionnaire/question/option/response tables, the general sync pipeline still contains question processing, the backend still exposes question-response and evidence-link mutation APIs, and the old DocTypes and protocol modules remain.

Some retained code supports historical reports, but this is broader than a read-only audit record. It does not meet the specification's complete retirement/no-backward-compatibility requirement. A schema migration is not complete merely because fields are hidden or old screens are deleted.

Fix: define the smallest historical read model needed for existing records; retire remaining legacy mutation APIs and fresh-install schema/runtime dependencies. Preserve disabled DD recovery scripts as required by the separate production policy.

### R8 ? Medium: selection and declaration controls have no meaningful visible selected state

Sources: `mobile/components/TaskBriefScreen.tsx:77`, `:97`; `mobile/components/Buttons.tsx:64-86`.

Selected options and the accepted declaration only add two spaces to their labels. They use the same button style and expose no selected/checked accessibility state. Scouts cannot reliably see which choices they selected or whether the declaration is checked. GhostButton's pale label styling also needs verification against this new light screen background.

Fix: explicit radio/checkbox or selected styling and accessibility state; test single/multiple selection and declaration toggling on device. This is a source-confirmed state-indicator defect; contrast has not been visually measured on a device.

### R9 ? Medium: an Unable to Verify report can retain a superseded observation

Sources: `mobile/components/TaskBriefScreen.tsx:33`, `:71`; `fieldpulse/report_preparation.py:34-44`.

Toggling Unable to Verify preserves an existing answer value. Report assembly prefers that value when creating findings, even when status is unable_to_verify. Reproduced with value='Fence is intact' and explanation='Could not establish the boundary': the report's findings remains 'Fence is intact'. Its assessment is correctly Not verified and its limitation contains the explanation; it is not silently labelled verified. Still, the old factual assertion should not be the principal finding after the scout retracts verification.

Fix: for Unable to Verify, use the explanation as the report finding and keep superseded observation text only in audit history, or make the distinction explicit.

## Other implementation observations

- The assignment dialog uses a comma-separated list of internal check IDs rather than a readable check picker. Functionality exists, but manual multi-scout allocation is error-prone, especially with UUID IDs created by the editor.
- `map_task` rewrites project_title and task_brief from the current Field Request on saves, while pin_assignment restores the descriptive approved title/objective only on new tasks. The active brief screen reads the immutable snapshot, but task-list metadata can diverge from it after a status update.
- Mobile capability validation does not require task_brief_version even though the pull advertises it. The backend rejects old clients for brief assignments; mobile should also clearly reject a backend without the brief contract.
- Optimistic UI updates occur before SQLite save succeeds. In particular, a failed queued=true save makes the screen read-only, while act awaits the rejected save promise before it can perform Sync now or the custom Back action. Add a failed-save recovery test rather than assuming local persistence always succeeds.
- New media is intentionally prohibited for answer-only clarification. Additional evidence is handled as a cancelled allocation plus a manually assigned new visit; no automatic linked replacement is created. This is only a partial implementation of a convenient additional-evidence workflow and is affected by R5.

## Requirement-by-requirement assessment

| Requirement | Assessment | Evidence / qualification |
| --- | --- | --- |
| Request-specific AI Task Brief | Implemented in source; website delivery blocked | Initial assessment schema contains task_brief; server validates it and Field Request insertion seeds a Draft. R1 blocks normal website submission. |
| Objective, scope, title, deliverables, access/safety instructions | Implemented | Structured schema and active scout display. Final model quality still needs representative request evaluation. |
| Tailored response types and necessary photo/video counts | Implemented | text/single/multiple/none, explicit per-check evidence minima; no category-to-check lookup in the new path. Conciseness/non-repetition is instructed, not established by live model tests. |
| Exactly four categories | Implemented in the new contract | Backend/website schemas agree. Category constants are duplicated across sources rather than maintained through a single generated definition. Old architecture cleanup remains R7. |
| Unclear/unsafe/out-of-scope flags | Implemented with limits | Intake safety checks, separate eligibility state, review reasons, empty actionable checks for unresolved output and coordinator approval guard. Not a proof of semantic safety for arbitrary model output or coordinator edits. |
| Coordinator add/edit/remove/reorder and approval | Implemented in source | Native Desk grid/editor and server-controlled approval/version fields; real Desk interaction and permission verification still required. |
| Versioned immutable approved briefs; no regeneration on opening | Implemented | Project lock, version allocation, content digest, immutable approved record, pinned task snapshot. |
| Manual multi-scout subsets | Partly implemented | Initial allocation and independent drafts work; incremental/follow-up coverage fails in R5. |
| AI stops at intake | Implemented in inspected runtime | AI calls found in request assessment/generation only, including intake retries/clarifications; none found in scout collection, coordinator evidence review or reporting. |
| Live GPS proximity and accuracy unlock | Implemented in source | Device location sample, independent radius/accuracy checks, server arrival timestamp and GPS validation. Real-device checks remain. |
| Safe access issue without unsafe approach | Partly implemented | Reason and available actual GPS supported; empty editable reason crashes (R2). |
| Unable to Verify plus mandatory reason | Implemented, with reporting edge case | Completeness permits explained inability without pretending evidence was verified; R9 concerns stale finding text. |
| Additional observations | Implemented | Optional locally persisted field and deterministic report inclusion. |
| Camera capture and per-capture GPS/time | Implemented in source | Camera obtains a foreground GPS sample at capture/record start; timestamp, accuracy and capture-sample age checked. |
| Task/scout/check evidence association | Implemented | Explicit submission/check references; task/scout ownership independently checked on the server; original stored metadata protected. |
| Offline persistence and original-metadata sync | Partly implemented | Account-scoped private files, SQLite drafts, capture recovery and idempotent uploads exist. Terminal-state retry and failed-save recovery need work. |
| Deterministic completion/counts | Implemented | Independent Python/JS validators; distinct uploaded file references, response types, evidence counts and metadata validity. |
| No repetitive technical checklist questions | Implemented in active brief flow | GPS/counts/completion are calculated; only observations and final declaration are requested. |
| Final review and correction before submission | Partly implemented | Answers/media/status/missing requirements shown and edit action provided; state indicators fail R8 and draft validation fails R2. |
| Independent backend validation and audit | Implemented in source; integration verification pending | Server loads uploaded evidence, validates brief and ownership, preserves submitted responses and revisions. New workflow API integration tests are thin. |
| Coordinator approve/reject/clarify/add evidence | Partly implemented | Decisions exist, but clarification delivery fails R4 and follow-up allocation fails R5. |
| Deterministic report with coordinator approval | Implemented in source, with R9 | No report AI; findings/evidence assembled and approved-release safeguards reused. Real PDF/client delivery not exercised. |
| Complete obsolete architecture removal | Not complete | R7; deleted catalogues/screens do not remove remaining schemas, protocols and mutation paths. |
| Existing requests/payments/assignments not unnecessarily disrupted | Partly verified | Deposit/report-payment controls remain in source; R1 and R6 are material regressions/rollout gaps. |
| Intended end-to-end workflow | Not complete | Website submission blocker plus correction/retry gaps; no live end-to-end demonstration. |

## Verification performed

- Backend: 416 existing tests passed during this review.
- Website: 146 existing tests passed during this review.
- Mobile: TypeScript check passed and all 44 existing tests passed during this review.
- Confirmed backend/website Task Brief schemas are structurally equal; website/mobile JS rule files are byte-identical; all three contract fixtures match.
- Confirmed runtime AI calls are confined to website request intake in the searched source.
- Additional probes reproduced R1, R2, R3, R5 and R9 without changing application source.
- R4, R6, R7 and R8 are supported by the connected source paths described above; they were not claimed as physical-device/Frappe integration runs.

The passing test count should not be used as an end-to-end acceptance criterion. Existing proof tests sign and verify the same object rather than traversing the submit-route normalizer. The brief retry test does not change task status to Approved between acceptance and acknowledgement retry. New backend workflow tests largely cover pinning/coverage invariants using mocks; they do not exercise the entire save/review/notification/report transaction on a real site.

## Recommended completion order

1. Fix R1 and add the real intake-to-submission contract regression.
2. Fix draft-safe access validation, terminal queue reconciliation and clarification-note delivery (R2?R4).
3. Fix allocation coverage across existing work and targeted follow-ups (R5).
4. Finish the planned legacy retirement and explicit existing-assignment cutover (R6?R7).
5. Fix selected-state UI and Unable to Verify report presentation (R8?R9); cover failed persistence and metadata display consistency.
6. On backed-up staging and physical devices, verify the full lifecycle with multiple scouts, unsupported requests, unsafe access, inaccurate GPS, airplane mode, app restart, partial upload/lost acknowledgement, clarification, additional evidence, report generation/approval/customer download and the unchanged payment gates.

Do not deploy or declare the specification complete solely because the current test suites pass.
