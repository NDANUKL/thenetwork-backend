# Backend cleanup review ? 23 October 2026

Reviewed coordinator dashboard, Diaspora Request intake, Field Request assignment, Field Task, scout submissions, client reports, quotations/payments, shared constants, and their integration and migration references. Cross-checked apparent unused intake fields against the website submission endpoint and quotation fields against print templates. This is a source review; deployed data and external mobile clients were not inspected.

## Cleanup completed

- Removed the unused Scout Responsibility schema field and assignment payload handling (earlier change in this working tree). Old client payloads containing this optional key are ignored.
- Removed a task-brief construction block whose result was immediately overwritten by the structured project scope.
- Replaced the duplicate `fieldpulse.fieldpulse.constants` definitions with explicit imports from `fieldpulse.constants`. Both import paths remain valid and now include the same coordinator role.
- Removed repeated identical request/scope/evidence paragraphs in scout submission review. Distinct content and clarification answers remain visible.
- Hid raw internal fields from normal Desk forms: Field Task navigation JSON and assigned question codes; submission arrival/final-review JSON; report reviewed-submission references. These fields still support navigation, dispatch, evidence review and report generation and have not been deleted.
- Corrected the scout-picker test mock to accept setup/change handlers without a refresh handler.

## Reviewed and retained

| Area | Why it remains |
| --- | --- |
| Proposed completion date | Printed on quotation PDFs; not unused. |
| Submitted assessment, original submission snapshot, clarification history, risk flags | Populated by website intake; source-only backend searches miss that producer. Preserve customer context and traceability. |
| Scope review note | Already hidden and no longer required. An existing project-contract migration still checks for the schema field. Retain for migration compatibility and historical notes. |
| Location confirmation and scope confirmation | Separate dispatch gates: where the scout goes versus what they must check. Removing either changes operational behavior. |
| Payment terms and historical currencies | Terms are generated rather than manually entered; existing quotes/payments retain their recorded currency. These support historical records and customer documents. |
| Legacy task/agent links and old API aliases | Used by migrations, registration/synchronization, task compatibility and callers outside the coordinator form. No evidence that external users have stopped using these APIs. |
| Task status, submission review, QA and report approval | Different lifecycle stages and validation checks; similar names do not make them duplicates. |
| Disabled production scripts, snapshots and historical migrations | Recovery/audit references; not cleanup targets under production ownership instructions. |

## Validation

142 Python tests pass (excluding quotation-print tests, which require Jinja2 absent from this local Python environment). Scout-picker JavaScript checks pass. Submission-review rendering checks confirm identical context appears once while distinct scope/evidence, arrival and coverage remain. Both constants import paths return the same definitions. JavaScript syntax and Git whitespace checks pass.

Deployment and normal Frappe schema migration remain required. No production records or stored database columns were deleted.
