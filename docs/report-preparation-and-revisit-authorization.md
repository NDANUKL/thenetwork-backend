# Customer-question reports and authorized revisits

These native changes extend existing selected scout checks. They do not change the established customer report-release/payment policy, create additional invoices, deduct scout pay, or install historical scripts.

## Customer questions and report drafts

On each Field Request, select the accepted quotation, enter each agreed customer question in Customer-question coverage, and use **Link selected scout checks** to connect it to the already assigned service/shared checks. Save mapping changes, then confirm coverage. Confirmation checks this request's Accepted quotation, records its version and the reviewer's identity, and validates all links against selected checks. Changes to questions, links, selected checks or accepted quotation version require reconfirmation.

New customer-linked dispatches require confirmed customer-question coverage. The mapping and accepted project scope/version are pinned into the task snapshot alongside the existing questionnaire pin. Replacement revisits preserve that pin. There is no second questionnaire for the scout.

After all active tasks pass review, automatic report preparation creates a draft organized by customer question/site assignment. It includes scope references/versions, recorded visits and methods, actual recorded findings in the summary, source basis, limitations, candidate evidence and source references. Nothing infers independent verification from an absent source field. Missing answers, skipped checks, missing required evidence and missing verified visit records remain Not verified.

For historical tasks with no customer mapping pin, confirm coverage on the existing project during review, then use **Refresh from approved findings**. The report marks this as retrospective mapping. Unmapped projects still produce a draft warning, so lack of mapping does not roll back a valid scout approval; they cannot produce an approved report until mapping is complete. Existing task snapshots remain unchanged.

Review each report row, edit findings and summary as needed, and establish the source basis. Explain source-basis changes. A Not verified item needs a client-visible limitation and explicit acknowledgment. A recorded source gap cannot be relabeled as a supported finding. Every customer row and source reference stays present. Select permitted evidence, confirm coverage and evidence review, then generate the PDF. The generating reviewer must also approve that version; a different approver must regenerate it under their identity. All narrative, row, evidence selection, source snapshots and reviewer fields participate in the PDF content hash. Approved reports remain locked; new versions preserve earlier reports.

The PDF places customer-question findings in the main report, identifies only selected released evidence as E001, E002, etc., and displays recorded scope, visits, limitations and reviewer/version. No public evidence URL or device path is embedded. Private evidence remains in the existing selected-media bundle.

## Revisit authorization

Answer correction stays with the original scout and retains the original visit/evidence. It must not require another site visit or new photo/video capture. New captures are blocked in the app and upload API for a correction; request a revisit instead.

Requesting Return to site now creates **DD Revisit Request** and places the original task in **Awaiting authorization**. It creates no response revision, replacement assignment or scout dispatch notification. Pending work is nonactionable in the app and server APIs. The same-scout/replacement-scout choice remains, with a reason required for a replacement.

Record the cost arrangement (Existing agreement, Business-funded, Additional client charge), contract/arrangement reference, scout compensation agreement reference and authorization notes. Additional client charges require a client acceptance reference. These are coordinator-attested references, not automated verification of an external contract or payment. No financial mutation occurs here. Additional scope must go through the separate agreed scope/change-order process; it cannot be smuggled into a revisit of the original pinned checks.

**Awaiting authorization -> Authorized -> Dispatched**. Authorize signs the exact proposal and commercial terms but creates no fieldwork. Dispatch rechecks the terms hash, source state and scout availability, creates the blank revision/replacement through the existing workflow, and queues the receiving scout's notification atomically. Retrying a completed dispatch returns the same task. Arrival and media capture must occur after dispatch. Same-scout work restarts only through the authorized dispatch action; another scout receives a separate Assigned task and must record their own work.

Decline/Cancel require reasons and leave the failed fieldwork unresolved rather than marking it complete. Return for changes and Reopen return the commercial record to pending review, clear its authorization and require a new sign-off. Changes to proposal or commercial terms after authorization are blocked. Document version history preserves these decisions. Pending authorizations must be resolved before their task is cancelled or another normal assignment is created for that project.

## Deployment and acceptance

Run normal Frappe model migration to add DD Customer Check, DD Report Check, DD Revisit Request and the added fields/status. Build Desk assets and restart workers. Release the compatible scout app (`rework_version=2`); older clients receive an update-required response for authorization holds. Existing questionnaire, request, quotation, submission and evidence records are retained.

Acceptance must verify real Frappe model sync, reviewer roles, scope-link confirmation/reconfirmation, historical mapping, missing answer/media and source-basis handling, PDF regeneration/sign-off, private selected-media downloads, same/replacement scout dispatch, authorization changes, failed/retried requests, original scout holds with queued work, and email worker delivery. No live migration, email delivery or publication is performed by these source changes. PDF QA uses the actual Jinja template with fictional normal/long records; verify the deployed Frappe PDF renderer as part of acceptance.
