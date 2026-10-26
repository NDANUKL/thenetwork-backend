# Scout mobile profile and leave

Scouts use Mobile > Profile > My profile & availability to edit their full name, county and phone number online. The authenticated session determines which profile is updated; callers cannot supply a scout ID, user, activity status or task counters. Full names require at least two names. Updates also align the User name and legacy FP Agent contact details.

Go on leave sets On Leave and blocks new assignments through the existing Field Task validation. Existing tasks stay assigned; the app asks scouts to arrange any handover with their coordinator. Return from leave derives Busy or Available from the current Assigned, Accepted and In Progress task count. Profile edits do not clear leave. Activity and task counters remain automatic.

Field Operations Coordinators retain read access. A permission hook denies mutations even when a coordinator also has Supervisor permissions; Scout Profile validation also rejects direct coordinator saves. Desk shows all fields read-only. Mobile self-service explicitly authorizes only a scout's own profile. Administrator retains administrative access.

Deploy the backend changes, run normal Frappe migration/asset build, then release the mobile update. No production deployment was performed locally. Verify on staging with separate scout and coordinator sessions: edit and reload profile details, go on leave, reject a new assignment, finish an existing task, return with/without active tasks, reject cross-account requests and direct coordinator saves. Test offline failures and retry; the app never reports a failed online change as saved.
