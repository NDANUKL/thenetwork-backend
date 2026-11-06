# Client report review - 6 November 2026

This records local source and verification. It is not evidence of a deployment or a live Frappe check. The [production ownership policy](production-script-ownership.md) controls deployment and historical-record handling.

## Requirements checked

| Requirement | Current native/frontend source |
| --- | --- |
| Approved submission creates a draft | `task_brief_workflow.review_response` creates a submission-linked DD Service Report in the same transaction as approval. |
| View draft report on FP Task Response | The native form adds the action for a Passed response without requiring a report lookup first. Its reviewer-only POST action opens an existing report or creates the missing draft for previously approved work. Source response and approved task are checked. |
| Remove Prepare client report on Diaspora Request | Removed from the native form. |
| Task Brief language | Current report and response forms use Task Brief/field-check wording. Historical data and deterministic historical readers remain for audit. |
| Simplified report form | Manual attachment, summary, limitations, next steps, assessment, source-basis and limitation acknowledgement inputs are hidden. The former Reviewed finding input is a read-only Scout answer. Stored historical fields are retained. |
| Populate the report | Pinned objective, field brief, assigned checks actually answered, and their scout answers are sourced automatically. An unanswered optional check is omitted; a missing required answer rejects preparation. Numeric zero is preserved. |
| Coordinator controls client evidence | Photo/video inclusion and captions remain editable before approval. Only reviewed evidence belonging to that report's sources is downloadable. |
| Optional coordinator remarks | Included in the PDF only when supplied. Changing remarks or evidence changes the generated content hash. |
| PDF preview | Native report form offers Preview report PDF after generation. Private storage remains internal; manual file replacement and changing the originating request are blocked. |
| Separate client downloads | Download report returns PDF; Download evidence returns a media-only ZIP. Both URLs identify the same approved report and enforce ownership. |
| Multiple approved submissions | The portal retains the newest published report for each submission, with separate matched downloads. It does not hide earlier submissions when another report is released. |
| Agreed PDF branding | Uses the same logo, embedded Carlito fonts, teal/navy palette and production renderer as quotations/receipts. PDF lists selected photo/video counts and directs the client to the ZIP. |
| No displayed internal IDs | PDF does not render request/task/brief references. Old automatically generated ID-bearing report titles are replaced in PDF context. ZIP filenames use neutral photo/video names instead of device filenames/UUIDs. Internal URL parameters are still used for authenticated routing. |

## Native ownership correction

The earlier explanation that standard DocType form JavaScript requires an explicit `doctype_js` registration was incorrect. Frappe loads standard DocType files from their module directory automatically; the proposed duplicate hooks were removed. See [Frappe's native form asset loader](https://github.com/frappe/frappe/blob/version-15/frappe/desk/form/meta.py). No Client Script or Server Script records are installed, modified or enabled by this change.

## Local evidence

- 68 focused Python report/coverage/Task Brief workflow tests pass.
- The native Desk regression verifies that View draft report appears for an approved response without an existing report and calls the POST open/create endpoint.
- 162 existing frontend unit tests and four new PDF/ZIP route tests pass; the new checks cover report selection, MIME types, no-store responses, and rejecting login/HTML responses.
- Next production build passes. The final dashboard button-spacing markup also parses successfully.
- Short, four-page and no-remarks report cases were rendered with Chrome and inspected. Extracted PDF text excludes the seeded internal references and includes the correct evidence counts. This preview does not replace a check with deployed Frappe/wkhtmltopdf.
- The broader backend run had 21 failures/errors. All 21 were reproduced on an isolated snapshot of the unchanged committed revision; they are not introduced by this report review. The repository-wide suite is therefore not fully green.

## Remaining rollout evidence

Follow the controlling policy: read-only Task Brief cutover inventory before deployment, ordinary backend migration/model sync, compatible frontend deployment, and real Desk/download checks. Check both a newly approved submission and a previously approved response without a draft. Verify cross-customer denial, selected media, multiple submission reports, and production PDF pagination. Existing approved report files are not rewritten by source changes.
