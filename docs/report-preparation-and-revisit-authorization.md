# Customer-question reports and authorized revisits

These native changes extend existing selected scout checks. They do not change the established customer report-release/payment policy, create additional invoices, deduct scout pay, or install historical scripts.

## Customer questions and report drafts

On each Field Request, select the accepted quotation, enter each agreed customer question in Customer-question coverage, and use **Link selected scout checks** to connect it to the already assigned service/shared checks. Save mapping changes, then confirm coverage. Confirmation checks this request's Accepted quotation, records its version and the reviewer's identity, and validates all links against selected checks. Changes to questions, links, selected checks or accepted quotation version require reconfirmation.

New customer-linked dispatches require confirmed customer-question coverage. The mapping and accepted project scope/version are pinned into the task snapshot alongside the existing questionnaire pin. Replacement revisits preserve that pin. There is no second questionnaire for the scout.

After all active tasks pass review, automatic report preparation creates a draft organized by customer question/site assignment. It includes scope references/versions, recorded visits and methods, actual recorded findings in the summary, source basis, limitations, candidate evidence and source references. Nothing infers independent verification from an absent source field. Missing answers, skipped checks, missing required evidence and missing verified visit records remain Not verified.

For historical tasks with no customer mapping pin, confirm coverage on the existing project during review, then use **Refresh from approved findings**. The report marks this as retrospective mapping. Unmapped projects still produce a draft warning, so lack of mapping does not roll back a valid scout approval; they cannot produce an approved report until mapping is complete. Existing task snapshots remain unchanged.

Review each report row, edit findings and summary as needed, and establish the source basis. Explain source-basis changes. A Not verified item needs a client-visible limitation and explicit acknowledgment. A recorded source gap cannot be relabeled as a supported finding. Every customer row and source reference stays present. Select permitted evidence, confirm coverage and evidence review, then generate the PDF. The generating reviewer must also approve that version; a different approver must regenerate it under their identity. All narrative, row, evidence selection, source snapshots and reviewer fields participate in the PDF content hash. Approved reports remain locked; new versions preserve earlier reports.

The PDF places customer-question findings in the main report, identifies only selected released evidence as E001, E002, etc., and displays recorded scope, visits, limitations and reviewer/version. No public evidence URL or device path is embedded. Private evidence remains in the existing selected-media bundle.

## Current failed-submission handling

The questionnaire revisit authorization flow described in older revisions of this guide is retired. New Task Brief submissions are reviewed using Approve, Reject, or Request clarification and resubmission. Reject closes that scout's assignment and returns the project to Awaiting Assignment; clarification asks the same scout for a full resubmission. There is no current Return to site authorization decision. Historical questionnaire records remain read-only.

## Deployment and acceptance

Existing questionnaire, request, quotation, submission and evidence records are retained. New assignment and review behavior uses Task Briefs; see [Task Brief source transition](task-brief-transition.md).

Acceptance must verify Task Brief submission review, report preparation/approval, private selected-media downloads, failed/retried requests and email worker delivery. No live migration, email delivery or publication is performed by these source changes. PDF QA uses the actual Jinja template with fictional normal/long records; verify the deployed Frappe PDF renderer as part of acceptance.
