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

Field Request permissions are now defined on its DocType. The remaining
operational DocType permissions will be added with their corresponding
DocTypes, rather than creating permissions for nonexistent records.

## Clarissa's user

Clarissa must receive a Frappe **System User** account with the Field
Operations Coordinator role. The post-model-sync patch creates or updates
`groundscout.recruit@gmail.com`, enables it as a System User, and adds the
Coordinator role without removing any pre-existing roles. It deliberately does
not set a password or send an invitation email; an administrator must complete
that credential setup in Frappe Desk.
