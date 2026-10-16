# Permanent project conversion

The website sends project contract version 1 when its signed assessment contains
structured version 2 state. Every project retains its stable assessment ID,
service category, own scope, evidence tasks and eligibility. Submitted locations
carry an explicit array of project IDs, including shared visit memberships.
Neither project conversion nor location mapping reads display punctuation.

Diaspora Request owns conversion, on insert and update. A row lock serializes
conversion retries for that source. Field Request's existing unique project_key
is source reference plus stable project ID. The final coverage check requires
exactly one Field Request per eligible ID, rejecting combined, missing, extra
or duplicate records. Unsupported and overseas projects create no field work.
Project data is validated before creation. Unknown scope/county/evidence remains
under review; missing locations on supported authenticated submissions is an error.

Conversion exceptions propagate to Frappe's transaction owner. An API submission
rolls back rather than committing a customer request with a combined operational
fallback. There are no conversion-time commits and no swallowed exceptions.
Concurrent retries share the source row lock and database unique key. Existing
numbered records without IDs are adopted by explicit project number; assigned
unmapped combined records require review instead of automatic reassignment.
Legacy submissions without structured data use the isolated compatibility parser.
New versioned submissions cannot fall back to it.

Locations, verification, scope review notes, scout navigation and deadline syncing
are native helpers in project_locations.py. Original customer site revisions are
compared as data, preserving coordinator corrections until the customer changes
the matching site. Source changes invalidate location verification. Task creation
requires verified destinations for authenticated customer requests. Single-site
assignments get a navigable FP Location. Changes to the agreed project deadline
update unfinished task due dates. Project completion requires all active tasks to
be approved; aggregate completion requires all expected projects.

## Deployment order

Production now also has strict project-ID validation and exact coverage checks in
the site scripts, so the protection is active before this deployment. The audited
93-definition production configuration is versioned at
fieldpulse/configuration/production-configuration.json. The pre-model-sync identity
patch removes only duplicate Custom Field metadata, preserving its data columns.
The post-model-sync configuration adoption restores customer/detail/scout APIs,
forms, role permissions, quote DocTypes and print styling, while skipping the
temporary native-owned conversion scripts. See production-configuration-audit.md.

1. Back up the Frappe site and deploy this backend revision first.
2. Run bench --site YOUR_SITE migrate. The post-model-sync patch
   fieldpulse.patches.v1_0.permanent_project_contract installs identity/location
   fields, archives the temporary script definitions in a private File, then
   disables only the overlapping conversion, mapping and navigation scripts.
   Asking for customer details, quotation formats and coordinator form styling
   remain separate integrations.
3. On a staging site run bench --site YOUR_SITE run-tests --doctype "Field Request".
   Confirm a three-project submission produces three isolated Field Requests,
   repeated saves preserve the same references, and scout Due/map data survives.
4. Deploy the paired diaspora-desk website revision after backend migration.
   It adds contract version and server-derived site membership IDs. Existing
   signed assessments without version 2 state continue through compatibility mode.
5. Verify the Patch Log entry and that DD Field Project Mapping, DD Field Project
   Expansion, DD Task Project Mapping, DD Task Completion Rollup, DD Field Location
   Gate and DD Location Navigation Sync are disabled. Do not run an older installer
   that re-enables these scripts. The updated website installer skips them when
   it detects the native contract schema.

Offline regressions: python -m unittest discover -s tests -p "test_*project*.py".
The offline suite is not a substitute for the staging bench tests or a deployment
verification. Local preparation does not change the live site.

## Rollback

Roll back the backend revision before restoring the archived temporary scripts.
Preserve all identity columns and data. Script definitions can be restored from
the private before-permanent-project-contract.json backup. Never enable both
versions at once. Do not rename or reset existing request references.
