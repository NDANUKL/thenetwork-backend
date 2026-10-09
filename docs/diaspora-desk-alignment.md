# Diaspora Desk production customization alignment

The backend now owns the changes encoded in `diaspora-desk/scripts` and
`diaspora-desk/frappe`. This is a migration of the checked-in script definitions;
it is not an inventory of additional changes made manually in the live database.
No production calls were made during this work.

## Source coverage

| Desk source | Backend destination |
| --- | --- |
| `frappe-county-fields.mjs` | Standard county fields on Diaspora Request and its evidence children; child project numbers |
| `install-frappe-alignment.mjs` custom fields | Standard fields in the Diaspora Request, Field Request, Field Task and evidence DocType JSON files |
| `common.py`, five event scripts | `fieldpulse/project_alignment.py`, native document hooks and the Field Task aggregate status handler |
| `assign_scouts.py` | POST `fieldpulse.project_alignment.assign_project_scouts`; short API name retained through `override_whitelisted_methods` |
| Two assignment Client Scripts | Native Diaspora Request / Field Request form JS |
| `install-frappe-dashboard.mjs`, dashboard assets | Packaged `fieldpulse/dashboard` assets; workspace JSON; installation and after-migrate dashboard synchronization |
| `repair_records.py`, `repair-frappe-requests.mjs` | Explicit System Manager-only `fieldpulse.project_alignment.repair_metadata` bench command |
| `repair-frappe-project15.mjs` | Record-specific correction documented below, deliberately excluded from automatic schema migrations |
| `smoke_test.py`, test runner | Offline regressions plus self-contained bench Field Request tests, without a production template or temporary Server Script API |
| Preview installer | Dashboard assets copied unchanged; staging browser checks still required |

## Changes made and why

These changes are implemented in the local backend checkout. They have not been
applied to a development or production site. The sections below distinguish
production behavior brought into the app from additional fixes made during the
port. File paths are relative to `thenetwork-backend`.

### 1. Promote site custom fields into the backend schema

Updated the four DocType JSON definitions under
`fieldpulse/fieldpulse/doctype/` with the following standard fields:

| DocType | Added fields | Why |
| --- | --- | --- |
| Diaspora Request | `county`, `project_details`, `customer_target_date`, `alignment_review` | Retain the customer's project descriptions, counties and requested timing, and expose unresolved scope for review. Development needs these fields even when the production Custom Fields have never been installed there. |
| Diaspora Request Evidence | `county`, `project_number` | Keep each evidence row attached to the correct project and county instead of treating the whole request as one location. |
| Field Request | `customer_target_date`, `alignment_review`, `project_number`, `project_title`, `project_key`, `deadline_preference`, `evidence_requirements` | Represent one operational project, preserve its source identity and customer timing, and prevent duplicate project records with a unique `project_key`. |
| Field Task | `project_number`, `project_title`, `county`, `request_type`, `priority`, `task_brief`, `evidence_requirements`, `responsibility` | Carry the project's context and each scout's responsibility into their task rather than requiring the scout to interpret the combined customer request. |

Derived metadata is read-only as in the Desk installer. `project_details` and
`project_key` are hidden; `project_key` is unique. `responsibility` remains
editable. The new fields are included in each DocType's `field_order`. Existing
field definitions, role permissions and legacy migration links are retained.

### 2. Move project mapping and expansion into native application hooks

Added `fieldpulse/project_alignment.py` and registered the mapping handlers in
`fieldpulse/hooks.py`:

| Event / function | Change | Why |
| --- | --- | --- |
| Diaspora Request `before_save` / `map_diaspora` | Calculate the customer target and review flag, collect project counties, and stamp project/county metadata onto matched evidence rows. | Keep source metadata consistent on saves without requiring a site Server Script. |
| Field Request `before_save` / `map_field_request` | Map the selected customer project into its operational record, including its unique key, type, county, evidence and brief. | Avoid mixing several projects' locations and evidence into one assignment. |
| Field Request `on_update` / `expand_projects` | Create missing sibling Field Requests from the source project plan, checking `project_key` before insertion. | Replace the old backend's single combined operational request with the production one-record-per-project behavior; repeated saves should reuse existing projects. |
| Field Task `before_save` / `map_task` | Copy project number/title, county, type, evidence, priority and brief; derive an absent due time from the project deadline. | Give each scout the same project context as the coordinator and carry the production due-time rule into development. |

The shared parser supports middle-dot, en-dash, em-dash and spaced-hyphen intake
labels, canonical Kenyan county names, and request-type classification from the
project description/category. Project descriptions in `project_details` survive
an empty evidence checklist. Missing evidence/county or unresolved scope statuses
(`needed`, `scope_confirmation`, `unsupported`) keep the project under review.
Conflicting or unlabelled evidence requires review instead of a guessed mapping.

Briefs use the matching project's summary paragraph or retained description.
Automatic brief/type replacement is limited to initial mapping or unassigned
projects without tasks. Existing assigned records lacking project metadata cannot
be split automatically. Customer request links cannot be changed by mapping an
existing linked project; existing linked scout tasks cannot be moved to another
project or detached. Legacy unlinked tasks are retained, and new unlinked tasks
are allowed only through the existing `legacy_fp_task` migration exception.

### 3. Preserve customer timing and coordinator adjustments

The native project plan implements the production timing rules: `oneWeek` and
`twoWeeks` mean 7 and 14 calendar days from source creation/submission;
`specific` uses `deadline_date`; `flexible` has no customer target. The separate
`customer_target_date` records the original customer timing while `deadline`
remains the operational deadline. Mapping fills an empty operational deadline
and preserves a populated one. Task mapping fills an empty `due_at` with the
project deadline at `23:59:59`, preserving a populated task due time.

This prevents conversion from losing relative timing or overwriting coordinator
adjustments. The existing single-scout allocation API still honors an explicitly
supplied `due_at`, including when it reuses an active task.

### 4. Support multiple scouts and preserve API compatibility

Added the POST endpoint
`fieldpulse.project_alignment.assign_project_scouts(field_request, assignments)`.
It accepts a JSON array or a list of 1?20 scout assignment objects, rejects a
scout repeated within the batch, and requires distinct, nonblank responsibility
descriptions for a batch containing multiple scouts. Responsibility comparison
ignores case and surrounding whitespace. Each row may choose its own location
and questionnaire. A selected questionnaire's current version is recorded on a
new task.

The endpoint reuses a task for the same project/scout when its status is neither
Cancelled nor Approved. A repeated assignment does not rewrite that reused
task's responsibility, location or questionnaire. Completed/cancelled projects
and projects needing scope review cannot be allocated. Assignment advances an
Awaiting Assignment project to Assigned and advances a New/In Review customer
request to Assigned.

Changed `assign_field_request` in
`fieldpulse/fieldpulse/doctype/field_task/field_task.py` to delegate to this
endpoint, removing the old restriction that any existing task blocked another
scout. Its parameters and `{"field_task": ...}` response shape remain available;
the new endpoint returns `{"tasks": [...]}`. Added a
`override_whitelisted_methods` entry for the former `dd_assign_project_scouts`
API name so existing callers can reach the native implementation after the site
API Server Script is disabled. This compatibility path still needs live Frappe
verification.

Location and questionnaire are now optional in the single-scout wrapper, matching
the production Desk dialog. This is an intentional behavior change from the old
backend, which required both. Mobile flows that depend on those links must still
receive them before use. The existing On Leave assignment check continues through
the Field Task controller.

Manual Field Requests can be allocated without a customer `project_number`.
Both the endpoint and form guard apply that number requirement only to
Diaspora-linked requests. This avoids breaking manual operations or inventing a
customer project number; county and review checks still apply.

### 5. Fix premature completion with aggregate status updates

Changed `FieldTask._sync_field_request_status` to call the native `rollup_tasks`
implementation instead of mapping the current task's status directly onto its
parent. Previously, one Approved task could mark the project Completed while
other scouts were still working; cancelling one task could cancel the parent.

The new handler reads all non-cancelled tasks. A project becomes Completed only
when all of them are Approved; otherwise active progress yields In Progress or
Assigned. It preserves a project already marked Cancelled. Customer completion
also requires every expected project number to be represented and every active
project to be Completed, with no project-plan issues. A Rejected customer request
is preserved. If there are no non-cancelled tasks, this handler leaves the parent
status unchanged; cancelling every task does not automatically cancel the project.

The existing controller still owns status-transition validation, timestamps,
rework counts, scout workload/availability updates and reassignment history.
Derived project/customer statuses use targeted database updates so scout updates
do not require general edit permission on the customer record.

### 6. Prevent partial automatic conversion

Added a database savepoint in
`fieldpulse/integrations/diaspora_request.py`. When automatic operational
conversion fails, the handler rolls back the project-conversion work to that
savepoint and logs the error, preserving the existing fail-safe customer
submission behavior.

Without that rollback, a caught error during sibling creation could leave a
partially created set of projects. This fix is implemented but its real database
transaction behavior still needs staging verification. A failed conversion is
logged; the handler does not automatically retry it.

### 7. Add input checks and retain assignment permissions

The native parser reports malformed project JSON, non-array project details and
non-object detail entries as validation errors. Detail project numbers must be
positive integers, excluding booleans, and duplicates mark the plan for review.
Explicit counties in project details are normalized to the known county list;
when no canonical county is available, the parser can retain an explicitly named
county from the description, otherwise the project stays unresolved.

The assignment endpoint rejects malformed JSON, non-array inputs and non-object
assignment rows. These checks turn parser failures and ambiguous project identity
into actionable errors/review rather than accepting an unreliable mapping.
They do not constitute complete validation of every possible nested value type.

Assignment checks Field Request write permission, Field Task create permission
and Scout Profile read permission. Mapping requires customer read access or write
access to an existing linked operational request. Trusted conversion creates only
source-derived sibling projects with permission bypass; it does not grant the
website integration role general operational creation rights. Existing role
permissions and Custom DocPerm records are not changed.

### 8. Move both assignment buttons into native form scripts

Added `diaspora_request.js` and `field_request.js` beside their backend DocType
controllers. The Diaspora Request button opens the linked project, prompts for a
project when there are several, or opens a new linked Field Request when none
exists. The Field Request button provides the multi-scout table, responsibilities,
per-scout location/questionnaire choices, task feedback and form reload.

The forms require saved records and appropriate write access, explain review
blocks, and explain that changing status alone does not assign a scout. The Field
Request dialog calls the native endpoint and disables its submit button while
working. These changes reproduce the production workflow without separately
installing Client Scripts and preserve the manual-request exception above.

### 9. Package the operations dashboard and install it through app lifecycle hooks

Copied `operations.html`, `operations.css` and `operations.js` byte for byte into
`fieldpulse/dashboard/`. Updated the Field Operations workspace JSON to display
`DD Field Operations Dashboard` as its custom block while retaining its shortcut
definitions. Added `fieldpulse/alignment_install.py` to create/update the block,
load the packaged assets and copy the workspace roles onto it.

`fieldpulse/install.py` invokes synchronization after role creation on install;
`fieldpulse/hooks.py` invokes it after migration. This makes the dashboard part of
a normal backend deployment instead of a separate production REST installation.
The workspace remains available to its coordinator/System Manager roles and the
dashboard continues using signed-in permission-checked APIs. Synchronization
replaces this named block's assets with the repository versions; any independent
site edits to that block must be reviewed before deployment.

### 10. Adopt existing site customizations without running duplicate automation

Added `fieldpulse/patches/v1_0/adopt_desk_alignment.py` and registered it in the
`[pre_model_sync]` section of `fieldpulse/patches.txt`. The patch:

- Validates the six named Desk Server Script targets/events or API method, the
  two named Client Script DocTypes, and the promoted Custom Field types.
- Saves the matching customization definitions and existing workspace/dashboard
  definitions into a private `desk-alignment-before-adoption.json` File before
  changing them. This definition backup supplements the full site backup; it is
  not a backup of all customer/project/task records.
- Disables the six named Server Scripts and two named Client Scripts so native
  handlers and site scripts do not both execute the same workflow.
- Removes only the listed Custom Field metadata rows directly, leaving physical
  columns and field values for standard model sync. It clears Frappe caches.

This avoids duplicate handlers and custom/standard field collisions when the app
is deployed to a site that already has the production customizations. Incompatible
field types or unexpected script targets stop adoption before these mutations.
The patch checks targets and types, not full script-body equality: compare live
customization bodies with their checked-in sources before deployment. Unrelated
scripts, fields and Custom DocPerm records remain outside its adoption list.

### 11. Provide explicit metadata repair and preserve customer-specific data

Ported the repair into the System Manager-only bench function
`fieldpulse.project_alignment.repair_metadata`, avoiding the old need to install,
execute and delete a temporary API Server Script. It updates source customer
target/review metadata and matched evidence project/county fields, then saves
only Awaiting Assignment Field Requests with no linked tasks. It reports repaired
records and existing assignments preserved. The source review flag now also
considers each project's unresolved review flag, even when the overall plan has
no parsing issues.

Repair is an explicit command rather than an automatic migration because
assigned work may already contain coordinator decisions. It does not create a
first operational record for a source with no linked Field Requests, reassign
scouts or rewrite existing task work. Such cases need separate operational review.
The `DD-2026-00015` correction remains documented below rather than becoming an
automatic customer-data patch: matching IDs across sites are not sufficient proof
that the customer records match.

### 12. Add regression tests and deployment documentation

Added `tests/test_project_alignment.py` with 14 offline tests covering project
isolation/type mapping, label separators, all timing preferences, pending projects,
conflicting evidence, malformed project details, deadline/brief preservation,
assigned-record protection, task metadata/due time/legacy behavior, task-link
immutability, assignment validation/permissions/retries, manual allocation,
aggregate completion, and cancelled/rejected status preservation.

Added `tests/test_alignment_adoption.py` with three offline tests covering a clean
site, refusal of an incompatible field type, and definition backup before Custom
Field metadata removal. These use a simulated Frappe adapter, so they do not prove
real event ordering or schema/data preservation on a live database.

Added two real Frappe tests in
`fieldpulse/fieldpulse/doctype/field_request/test_field_request.py` for project
splitting, repeat saves, multi-scout assignment/retry, task transitions and complete
rollup, plus retention/blocking of pending projects. They create their own source
and scout fixtures instead of copying a production customer record. They are
provided but have not been run in this checkout.

Added this guide and a README link so maintainers can trace each source, reason,
compatibility choice, migration step and remaining verification requirement.
Python compilation, JavaScript syntax, schema field ordering/uniqueness and
byte-for-byte dashboard parity checks also passed locally. The mobile pull API
was inspected and already returns all task fields, so no mobile API source change
was made; rendering and mobile end-to-end behavior remain unverified.

## Behavior retained

Each known project creates its own unique Field Request using `request:project`
as its key. Project briefs and evidence remain isolated. Projects with missing
scope, evidence or county stay review-only, including projects retained in
`project_details` when their evidence checklist is empty. One/two-week dates use
submission date plus 7/14 calendar days; flexible dates are blank. Customer target
and coordinator deadline are separate, and existing operational deadlines and
task due times are preserved. New due times use 23:59:59 in site-local time.

Assignment supports 1–20 scouts with responsibilities, optional location and
questionnaire, and reuse of each scout's active task. Multiple scouts in a batch
must have distinct responsibilities. The existing single-scout API delegates to
this implementation and retains its `field_task` response key. Task transitions,
On Leave checks, workload calculation and reassignment history remain in the
existing Field Task controller. Questionnaire version is captured at allocation.

A project completes only when every non-cancelled task is Approved; a customer
request completes only when every expected project exists and all active projects
are Completed. Rejected customer requests and cancelled projects are preserved.
New tasks require a project link, with the legacy FP Task migration exception.
Existing project/task links cannot be changed or detached. Permission checks and
source-derived sibling insertion follow the Desk scripts; role definitions and
Custom DocPerm records are not broadened.

Manual Field Requests retain allocation without a customer project number; their
county and review checks still apply.

Malformed project/assignment JSON now returns a validation error, duplicate or
invalid project numbers require review, and explicit counties are canonicalized.
Conversion uses a database savepoint so an operational failure cannot leave a
partially created set of projects while the customer submission is retained.

## Deployment to development/staging

1. Back up the database and public/private files; use a restorable clone first.
2. Deploy this revision and run `bench --site <dev-site> migrate`.
3. The pre-model-sync `adopt_desk_alignment` patch backs up matching Custom
   Fields, Server Scripts, Client Scripts, workspace and dashboard to a private
   `desk-alignment-before-adoption.json` File. It checks script targets and field
   types, disables only the six named Desk Server Scripts and two named Client
   Scripts, and removes only their Custom Field metadata. Physical columns and
   field values are retained for standard DocType model sync. Other scripts,
   custom fields and permissions are retained. A rerun skips absent definitions.
4. Migration installs the dashboard with the workspace's existing roles. Native
   form scripts use the app endpoint, so Server Scripts need not be enabled.
5. Run `bench --site <dev-site> run-tests --doctype "Field Request"`. Confirm
   conversion, two-scout retry, task status transitions, workload and aggregate
   completion with real Frappe events.
6. If aligning existing development records is needed, run
   `bench --site <dev-site> execute fieldpulse.project_alignment.repair_metadata`.
   This is intentionally explicit: it maps source/evidence metadata and saves
   only Awaiting Assignment projects with no tasks. Assigned records are reported
   as preserved and need manual operational review. Review the command output.
7. Verify coordinator form buttons, dashboard desktop/mobile views, county filter,
   drilldowns, permission-denied states, and scout mobile pull/accept/start/submit.
   Mobile pull already returns all task fields; mobile rendering of the newly
   exposed metadata is not proven by that API alone. Optional location and
   questionnaire match the production assignment dialog; complete them before
   exercising mobile flows that need those links.
8. Compare live site customization definitions with the checked-in Desk scripts
   to catch edits made outside those scripts. Do not treat passing offline tests
   as proof of complete live-site parity.

Do not rerun the Desk installers after backend adoption: they recreate duplicate
site event scripts and Client Scripts. Keep them for history and restoration.
Rolling back requires restoring the pre-migration database/files backup alongside
the old backend revision; simply reverting code is insufficient because the
adoption patch disables site scripts and promotes fields to standard metadata.

## Record DD-2026-00015

The Desk repair populated four descriptions from that particular customer's
submitted summary: land in Turkana County, construction on a house in Kitui
County, salon business in Kilifi County, and a document check at a Huduma Centre.
The first three use `location_question_status: needed`; the fourth uses
`scope_confirmation`. No county is invented for the fourth. These are customer
data, not portable schema defaults: transfer them through an authorized database
clone/export, or confirm the source summary before manually applying the original
repair on development. Never infer that a matching document ID on a different
site identifies the same customer. No automatic record-specific patch is shipped.

## Validation performed locally

`python -m unittest discover -s tests -v`: 17 passing offline regressions using a
simulated Frappe adapter. Python compilation and JavaScript syntax checks cover
all added Python modules, native form scripts and dashboard script. Dashboard
assets match their Desk sources byte for byte. Bench integration tests, migration
against a real database, browser rendering and mobile end-to-end checks are
provided/required but were not run in this Windows checkout (no bench/site).
