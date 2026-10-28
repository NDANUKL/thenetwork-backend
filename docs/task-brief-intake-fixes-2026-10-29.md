# Local intake and recovery fixes — 29 October 2026

Source changes only; no deployment or live request modification was performed.

- Field Request now asks for Task Brief approval rather than a legacy project evidence summary.
- Open Task Brief opens the existing project draft, then the approved brief. When neither exists it recovers the original intake brief by exact project ID. Manual/historical requests without initial output get an explicitly labelled manual draft; no new AI call is made. Existing draft edits and assigned versions are preserved.
- Initial assessment no longer copies combined request questions/risk summaries into every project brief. Generation explicitly requires project-local reasons. Request-wide safety review retains valid independent project checks under review; project-specific unsafe or ineligible scope still has no actionable checks. Supported empty briefs fail validation and use the existing generation retry.
- Scout password reset now loads fieldpulse/templates/emails/password_reset.html through the Frappe app template loader. The previous emails/password_reset.html path did not resolve to the packaged template.

Existing saved empty or mixed-scope drafts are not automatically rewritten: their original intake output and coordinator edits must be inspected before repair. The latest four production records were not inspected, so their individual causes remain unverified. Email transport configuration and delivery require deployment verification.

Validation: website unit tests; backend workflow, session and actual Jinja template rendering tests; Desk form behavior tests. The full backend suite has an unrelated stale legacy-radius expectation (expects Inside although the temporary geofence allowance is now disabled). No geofence behavior was changed.

Deploy through the ordinary native/website workflow described in [production ownership](production-script-ownership.md). No handover migrations or retired scripts are involved.
