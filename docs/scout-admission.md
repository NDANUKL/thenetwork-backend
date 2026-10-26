# Scout admission, deactivation and reactivation

New mobile registrations create a disabled User (password handled by Frappe) and a Pending Scout Application. They receive no Field Agent role, FP Agent, Scout Profile or session. The mobile application displays the pending decision and returns to the sign-in form.

In Field Operations, use **Review scout applications**, or search for **Scout Application** in Desk. Administrator, System Manager, Admin and Field Operations Coordinator can approve or reject Pending applications. Approval enables the User, assigns Field Agent and creates/links the agent and scout profile in the same transaction. Rejection requires a reason and retains the disabled identity. Repeated or competing decisions cannot approve an already reviewed application. Decision identity, time and reason are retained.

Only approved scouts can be deactivated; Pending and Rejected applications use their review controls. Legacy existing profiles retain their approved status. Open an existing **Scout Profile → Deactivate**, supply a reason, and confirm the action. This disables the linked User, removes API credentials and outstanding password-reset keys, suspends FP Agents and revokes sessions after the decision commits. Password login and authenticated requests also check the current access decision. New assignments reject deactivated scouts. Historical tasks, submissions, finances and profiles remain available to staff; review and reassign outstanding work separately.

Use **Scout Profile → Reactivate**, with a reason, to restore a deactivated scout's existing User/Profile and suspended FP Agent. A linked Scout Application must already represent an approved scout; Pending, Rejected or mismatched applications cannot be approved through reactivation. Legacy scouts without an application can be restored without creating another application/profile. The original approval and deactivation audit is retained, and reactivation records the staff member, time and reason. Leave status, workload and historical assignments remain as recorded. Revoked sessions/API keys are not restored; the scout must sign in again. No automatic reactivation notification is introduced.

Existing scouts retain their access without reapplying. Account Access is separate from recent app Activity and declared Availability. A quiet scout marked Inactive has not been deactivated. Pending/rejected/deactivated identities cannot be enabled through ordinary User edits; application deletion and scout identity deletion/renaming cannot be used to bypass decisions. All access changes use authorized Desk actions. Version history retains repeated deactivate/reactivate cycles.

The signup block identifies the retained email/User. A different email can submit a new application, which still requires human approval. Deactivation denies server access immediately once committed; it cannot remotely erase already cached offline data on a disconnected phone.

## Deployment and verification

This is a native backend and mobile source change. No production edits, handover, script retirement or deployment are implied. Live verification on 26 October 2026 confirmed that native handover completed on 16 October 2026; the earlier conflicting backend notes have been corrected. Deploy this feature through the native application workflow. Do not update or re-enable retired site scripts or rerun the handover migrations for this feature.

On an already approved native installation, deploy the backend and run normal schema migration to install Scout Application and the Scout Profile access fields, then build assets and clear cache. Deploy backend before distributing the new mobile build. Older mobile builds may report a missing session after successful application submission; applicants should update rather than repeatedly sign up.

On staging run:

```
bench --site <staging-site> run-tests --doctype "Scout Application"
```

Verify a real registration leaves the User disabled with no profile; Pending and Rejected accounts cannot use either mobile or standard Frappe login; approval creates exactly one profile with the supplied county/phone; simultaneous decisions cannot both succeed; ordinary scouts cannot call review/deactivation/reactivation APIs. Test Deactivate with an already signed-in phone and API token, retry password login/reset/signup, and verify no new assignment can use that scout. Reactivate the same scout and confirm fresh sign-in works, old sessions/keys remain invalid, profile/approval identities and leave status are retained, and no duplicate profile is created. Confirm an existing scout still works, and staff can read historical evidence and reassign open tasks. Check the pending mobile screen on Android/iOS and long reason text in Desk.

Local regression tests cover the state/permission guards, registration without a session, legacy access, revocation scheduling and transactional failure propagation. Real Frappe schema/event integration and device UI verification require staging; offline mocks do not establish production readiness.

Framework references used for the implementation: [document row locking](https://github.com/frappe/frappe/blob/version-15/frappe/model/document.py), [authentication hooks](https://github.com/frappe/frappe/blob/version-15/frappe/auth.py), and [session revocation](https://github.com/frappe/frappe/blob/version-15/frappe/sessions.py). Session deletion commits internally, so explicit revocation is scheduled after the admission transaction commits.
