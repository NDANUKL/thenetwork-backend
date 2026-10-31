# Scout rework and client report drafts

The native coordinator review action requires a rework type, one or more assigned question codes and instructions. The original submission, answers, evidence and review remain intact. Repeating a decision on a reviewed submission is rejected.

* **Correct answers** creates a separate Draft revision with new response/answer UUIDs. It retains the verified arrival, answers and verified evidence links. Evidence reuse is limited to failed correction ancestors with the same task and scout. It cannot bridge a site revisit or another assignment. This path requires a pinned protocol-v2 questionnaire and verified arrival; older questionnaires and arrival exceptions require Return to site.
* Questionnaire-based **Return to site** is retired. New Task Brief work uses the coordinator's current Reject or Request clarification and resubmission decisions; it does not create an authorization hold.

The task returns to In Progress and its rework count increments. Mobile sync requires `rework_version=1` for outstanding revisions. It hydrates the server-created revision once, preserves subsequent local edits, archives prior local responses, and displays the coordinator's instructions and flagged questions. Original capture metadata and labels remain frozen. Missing local files can be previewed online using authorized short-lived evidence URLs.

Rework creates a Desk Notification Log and a durable **DD Scout Notification** outbox record. Email uses the existing Resend sender configured in DD Access Settings. Worker enqueue failures leave Pending records for the five-minute scheduler. Delivery retries reuse a stable provider idempotency key; uncertain delivery beyond 23 hours requires operator review. Email is supplementary: feedback remains in task sync and the app. No native device push notification is claimed.

Approving the last active task automatically prepares a Draft DD Service Report. The existing request lock serializes review and report creation. An existing editable report is returned without overwriting coordinator edits. Approved reports are never overwritten. Findings, attributed statements, structured item values, limitations and candidate photos/videos are populated from approved submissions. Internal evidence requirement IDs and device paths are omitted from generated narrative. The coordinator reviews the summary and findings, selects permitted client evidence, generates the PDF and explicitly approves publication.

## Rollout and acceptance

1. Deploy the native backend, run the normal Frappe migration to install the added fields and DD Scout Notification DocType, build assets and restart workers/scheduler. Preserve disabled historical scripts and existing backup policy.
2. Release the compatible scout app. SQLite migration 9 adds rework metadata without deleting existing work. Older clients receive an update-required error for outstanding revisions.
3. Check a submitted v2 task using Correct answers: require question selection and notes; verify email/inbox and mobile feedback; edit a copied answer; retain evidence; sync and approve. Repeat the pull while an offline correction is pending and verify it is preserved.
4. Confirm historical questionnaire records remain read-only and current Task Brief review exposes only its supported decisions.
5. Check arrival-exception review, repeated decisions, lost upload acknowledgements, wrong-scout evidence access, cross-task and cross-revisit evidence reuse, worker/email outages and retries.
6. Approve the last task of a multi-task request: verify one draft report, all approved findings and limitations, retained evidence provenance, no unselected files in the client download, and no publication/email to the client until report approval.

Local unit/SQLite tests are not a substitute for this Frappe/mobile/email acceptance pass. No live migration, notification delivery or publication is performed by the source changes.


## Revisit ownership

Answer corrections remain bound to the original scout and task. New allocations are made through the approved Task Brief workflow.

A different scout receives a separate Assigned Field Task and a blank response. The original immutable questionnaire/site snapshot is retained. No original answers or evidence are copied. Original and replacement task links, source submission, reassignment reason and history are retained for coordinators. The original task keeps its scout and is cancelled after the replacement is created within the review transaction. The new task starts with zero rework failures and no acceptance/start timestamps. Repeating the review cannot create another replacement.

The receiving scout gets the durable revisit notification. The original scout receives a Desk assignment-ended alert and a cancellation on app sync. Cancellation overrides queued local status, removes obsolete upload queue entries, preserves local work as archived and blocks subsequent saves/submissions. An offline device learns the withdrawal on its next successful sync; server APIs reject submissions against the cancelled task immediately.

The cancelled original is excluded from active-task report readiness; the replacement must be independently submitted and approved. The report evidence lineage rules cannot reuse original-scout evidence in the replacement.

Acceptance: test both assignment choices; correction attempts with a different scout; missing reasons; disabled/on-leave/duplicate scouts; repeated review; new scout blank questionnaire and fresh arrival; original scout pending work during cancellation; separate ownership and source access; notifications; and report readiness waiting for the replacement. Deploy backend migration and the compatible scout app together. No client-website contract change is needed.
