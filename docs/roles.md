# FieldPulse roles

## Field Operations Coordinator

`Field Operations Coordinator` is a Desk role for operational allocation. It
is deliberately not a System Manager role and does not grant access to system
settings or unrelated applications.

The role is created by `fieldpulse.install.after_install` and included in the
app's Role fixture export.

| DocType | Access |
| --- | --- |
| Field Request | Create, read, write |
| Field Task | Create, read, write |
| Field Evidence | Read |
| Scout Profile | Read; availability override only if the On Leave policy later requires it |
| Diaspora Request | Read |

The first four operational DocTypes do not exist until Phases 2–5. Their
DocType-level permissions will be added with the corresponding DocTypes rather
than creating permissions for nonexistent records now.

## Clarissa's user

Clarissa must receive a Frappe **System User** account with the Field
Operations Coordinator role. Her actual email address is required before that
record can be created; no placeholder user is created by this app.
