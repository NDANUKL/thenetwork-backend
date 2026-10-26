# Published questionnaire conflicts during migration

If `after_migrate` reports `Questionnaire source changed: publish a new version
instead of overwriting DD-land-v1`, the installed record's hash differs from the
current catalogue hash. This error alone does not establish which questions differ.

The migration hook now uses `install(preserve_published=True)`. Existing Published
questionnaires with conflicting hashes are retained unchanged, with a warning in
the `fieldpulse` logger. Their question rows, stored hashes, publication metadata,
project pins and assignment history are preserved. Missing service templates are
still installed. The same preservation applies to the opt-in v2/visit installer.
Conflicting unpublished records still fail for review.

Explicit installation and service selection remain strict by default. This fix
does not accept changed source as the same publication or automatically switch
assignments. To publish revised content, issue a new version through the normal
review process. Preserving a historical publication is not a source-content audit.

Deploy the revision containing this fix, then rerun **Migrate Site**. Retrying on
the old deployed revision will encounter the same exception. Confirm migration
completion and review preservation warnings against the installed publications.
No production migration, handover or script retirement was executed by this fix.
