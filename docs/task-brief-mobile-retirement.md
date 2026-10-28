# Completed inactive mobile source retirement

Root: `Documents/DiasporaDesk/mobile`. The user explicitly approved deletion after reviewing this manifest. The files below have been deleted. The Task Brief assignment routes were already active.

Deleted files:

- `components/RevisedQuestionnaire.tsx`
- `components/StreamlinedQuestionnaire.tsx`
- `components/QuestionnaireHeader.tsx`
- `components/TaskStartPanel.tsx`
- `scripts/refresh-service-catalogues.py`
- `scripts/audit-scout-interactions.cjs`
- `tests/fixtures/service-catalogues.json`
- The obsolete catalogue-specific tests `service-catalogues.test.cjs`, `scout-interactions.test.cjs`, `scout-branches.test.cjs`, `school-fee-policy.test.cjs`.

The renderer-only `tests/question-index.test.cjs` and orphaned `tests/scout-interaction-harness.cjs` were also deleted after reference inspection confirmed they depended only on the removed workflow.

Shared camera, input, GPS, private storage, diagnostics and evidence components are retained. Historical saved responses/files are not deleted. The old questionnaire URL redirects to the Task Brief route. Historical diagnostic labels and dated audit documents may still name the removed screens; they are not executable imports.

Validation after deletion: TypeScript `tsc --noEmit` passed; all 44 remaining mobile tests passed. No executable references to the removed components or catalogue fixture remain. The diagnostics audit now checks all six source directories and the active Task Brief screen rather than assuming over 100 error boundaries. Its error-reporting rules remain unchanged.
