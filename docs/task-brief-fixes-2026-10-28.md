# Task Brief corrective changes — 28 October 2026

These are local source changes across `thenetwork-backend`, `diaspora-desk` and `DiasporaDesk/mobile`. They address the [dated implementation review](task-brief-implementation-review-2026-10-28.md). The [production ownership policy](production-script-ownership.md) remains controlling. No deployment, handover patch, production conversion or live fieldwork was performed.

| Finding | Corrective source behavior |
| --- | --- |
| R1: assessment proof mismatch | Submission validates and preserves `assessment_status`. A regression passes a signed structured assessment through the actual submission normalizer and rejects status tampering. |
| R2: empty unsafe-access explanation | JavaScript and Python completion evaluators return an incomplete result. SQLite restart/listing and screen rendering remain usable. |
| R3: queued terminal submissions | Server reconciliation checks UUID ownership before returning an existing submission. Closed unsubmitted work leaves the queue with an explanation; withdrawn work remains saved. Approval is not overwritten. Clarification pulls archive the previous UUID and hydrate the new revision once. |
| R4: missing clarification instructions | The screen loads and displays coordinator feedback and correction type. The native review action queues the durable rework notification in the same transaction. Original response and revision lineage retain provenance. |
| R5: follow-up allocation | Required coverage combines proposed checks with compatible active/submitted/approved allocations. Cancelled and old-version allocations do not supply coverage. The assignment dialog provides a labeled check picker. |
| R6: legacy work disappearing | Migration blocks unresolved legacy allocations. Scout sync refuses an incomplete cutover before publishing authoritative membership. Mobile also preserves historical tasks omitted by a feed. This prevents silent withdrawal; it does not complete operational conversion. |
| R7: questionnaire retirement | Old response-push/evidence-link endpoints are removed, public legacy revisit dispatch is retired, historical questionnaire schemas reject writes/deletes, and old Desk actions are removed. Fresh mobile schema v15 omits questionnaire/answer/upload-queue tables; old installations retain their saved tables/files. Active sync, progress and queue views use Task Brief data. Deterministic historical report readers and audit schema remain intentionally read-only. |
| R8: ambiguous selections | Radio/checkbox controls expose checked accessibility state, visible marks, selected styling and readable colors. |
| R9: stale unverified findings | Report findings use the inability explanation, never the superseded observation; the source response retains the original text for audit. |

Additional review observations addressed: task-list title/objective remain pinned after project changes; mobile rejects a backend without the Task Brief capability; failed optimistic persistence restores saved state so Submit failure does not lock the screen or prevent Back/Sync.

## Local verification

- Backend: 413 unit tests passed.
- Website: 148 tests passed; Next production build passed.
- Mobile: 44 tests passed, including SQLite lifecycle and UI tests covering fresh/upgrade schemas, retained unsent legacy work, access drafts, terminal acknowledgements, correction pulls/notes, queue paging, visible selections and failed-save navigation. Type checking passed.
- Retired mobile mutation test scenarios are preserved under `mobile/tests/historical-questionnaires/` as `.reference` audit files. Their current workflow replacements are `task-brief-lifecycle.test.cjs` and `task-brief-sync.test.cjs`; pure historical read tests remain separately available.

## Required rollout evidence

1. Take a staging backup and run `bench --site <site> execute fieldpulse.task_brief_cutover.inventory` before switching the deployed workflow. The helper is read-only; its `device_work_verified` value deliberately remains false because server queries cannot prove a phone has no unsent work.
2. Inventory each affected device and recover/export its original work and capture files before upgrading. Explicitly finish/cancel old allocations using the existing release, or approve new request-specific briefs and assign replacement work. Do not map old question categories into new checks. Do not bypass the guard or simply mark all old work cancelled.
3. Deploy coordinated revisions and run normal migration. Check real Frappe permissions, immutable snapshots, notification transactions, required-check coverage, deposit gating and report approval on staging. Retired DD recovery scripts remain disabled and untouched.
4. Verify Android/iOS permission denial, unsafe access, airplane mode, restart, capture interruption, account switch, lost final acknowledgement followed by approval/correction/cancellation, and storage pressure. Test the Desk check picker and review actions in real Desk.

The live legacy inventory, device reconciliation, staging migration and physical-device lifecycle are still unverified. Passing local checks is not a release sign-off.

## Authorized resolution of the production migration blocker

The owner subsequently supplied a failed `thenetwork.frappe.cloud` migration traceback listing 12 open legacy tasks, then explicitly authorized removing those assignments. The corrected hook cancels exactly those IDs once on that site, without deleting any records or evidence. It closes associated pending revisit authorizations, records the prior task status in an audit comment, refreshes workload, and resets only nonterminal projects with no remaining active or approved allocations. The Patch Log entry prevents later migrations from cancelling a reopened assignment again. Unknown legacy tasks still block cancellation and migration. Scout sync includes the cancelled task states.

Deploy the corrected backend revision and retry the normal Frappe Cloud deployment/migration. This exception needs no SSH access and no separate command. The original steps above still apply to other legacy work. Production success and recovery of any unsent device work have not been verified locally.
# Field-check generation and editor follow-up

Local source now preserves supported draft checks when the overall assessment needs confirmation, reports the actual review reasons, rejects empty supported generation, and still removes operational checks for ineligible work or deterministic safety restrictions. The initial AI prompt explicitly requires request-specific checks for requested photos, video updates and notes. Desk exposes photo and video minimums together and restores the previous status after a rejected approval. Mobile already supports both capture kinds; no mobile schema change is needed.

`brief-2026-00447-repair.json` is a validated, request-specific proposed replacement for the existing draft, based on the owner's supplied original request. It is not a category template, migration or deployed change. Its proposed minimums are two milestone photos and one video, with text notes. Apply through the normal coordinator draft editor after checking current saved status; never overwrite an approved version. The live record has not been repaired by these source changes. Browser control stopped during the earlier inspection, so no live approval or record update is claimed.

