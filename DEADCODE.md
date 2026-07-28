# Dead Code Audit Report

## Summary

This audit identified and removed **630 files** and **5 additional private helper functions** from the EndoReg/LX-Annotate study workflow. The deletion removes **more than 102,000 lines**:

- **621 LX-Annotate frontend files / 100,741 lines**: 56 unreachable TypeScript/Vue source files, 48 unreferenced legacy browser assets, and 517 checked-in compiler outputs or declaration artifacts.
- **9 EndoReg files / 1,389 lines**: six obsolete or empty Django management commands, one unused streaming compatibility module, and two unsafe one-off maintenance scripts.
- **5 EndoReg private helpers / 39 lines**: four superseded video query helpers and one unused hashing compatibility helper.

No live report-import, anonymization, annotation, study-cohort, secure-streaming, hub-transfer, reconciliation, migration, model, or LuxNix worker-helper path was deleted. No class met the certainty threshold for deletion.

The frontend build configuration now treats TypeScript as source-only (`noEmit: true`) and lets Vite produce deployment artifacts. This prevents the deleted sibling `.js` and declaration files from being recreated or accidentally selected instead of their `.ts` sources.

## Files Deleted

### LX-Annotate generated artifacts

- `frontend/types/**` — 280 generated declaration files (15,709 lines). The directory was compiler output, was not imported or published as a package API, and is now ignored.
- `frontend/src/**/*.vue.js` — 83 emitted Vue script files (45,614 lines). Every live component is loaded from `.vue`; the emitted siblings were not Vite entry points.
- Generated `frontend/src/**/*.js` siblings and root Vite/Vitest config output — 142 files (20,034 lines). These duplicated TypeScript source and could shadow it through extensionless resolution.
- Adjacent generated `frontend/**/*.d.ts` files outside `frontend/types` — 11 files (434 lines).
- `frontend/tsconfig.dts.json` — declaration-only build configuration made obsolete by the source-only TypeScript configuration.

Generation was disabled in:

- `frontend/package.json`
- `frontend/tsconfig.app.json`
- `frontend/tsconfig.vitest.json`
- `frontend/tsconfig.node.json`
- `frontend/.gitignore`

### LX-Annotate legacy browser assets

The following three duplicate trees contained 48 old Bootstrap/Material Dashboard/plugin JavaScript files (12,597 lines):

- `frontend/public/assets/js/**`
- `frontend/src/assets/js/**`
- `frontend/src/stores/public/assets/js/**`

They had no references from `src/main.ts`, Vue code, Django templates, Vite configuration, router configuration, tests, documentation, Nix service configuration, or deployment scripts. The active Django template loads the Vite `src/main.ts` entry point.

### LX-Annotate unreachable TypeScript source

- `frontend/src/adapters/patientFinding.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/videoAxiosInstance.ts`
- `frontend/src/composables/useCurrentPatientId.ts`
- `frontend/src/composables/useErrorHandler.ts`
- `frontend/src/composables/usePseudonym.ts`
- `frontend/src/config/index.ts`
- `frontend/src/services/errorLogger.ts`
- `frontend/src/services/keycloak.ts`
- `frontend/src/stores/annotationStatsStore.ts` — duplicate of the active annotation statistics store.
- `frontend/src/stores/authStore.ts` — superseded by the active authentication stores.
- `frontend/src/stores/casesStore.ts`
- `frontend/src/stores/findingClassificationStore.ts`
- `frontend/src/stores/imageStore.ts`
- `frontend/src/stores/pdfStore.ts`
- `frontend/src/stores/settings.ts`
- `frontend/src/stores/userStore.ts`
- `frontend/src/tests/mediaStoreTest.ts`
- `frontend/src/types/annotation.ts`
- `frontend/src/types/api/evaluateRequirements.ts`
- `frontend/src/types/index.ts`
- `frontend/src/types/report.ts`
- `frontend/src/types/reports.ts`
- `frontend/src/types/timeline.ts`
- `frontend/src/utils/deepMutable.ts`
- `frontend/src/utils/errorHandler.ts`
- `frontend/src/utils/findingFilters.ts`
- `frontend/src/utils/formatting.ts`
- `frontend/src/utils/logger.ts`
- `frontend/src/utils/mediaStoreTest.ts`
- `frontend/src/utils/patient-id-validation.ts`

Each file had no import, call, test, router, configuration, template, documentation, or string-based dynamic-dispatch reference. Public barrel/API risk was checked before deletion.

### LX-Annotate unreachable Vue source

- `frontend/src/components/CaseGenerator/FindingGenerator.vue`
- `frontend/src/components/CaseGenerator/FindingGeneratorDemo.vue`
- `frontend/src/components/CaseGenerator/PatientAdder.vue`
- `frontend/src/components/EndoAI/VideoAnnotation.vue`
- `frontend/src/components/Examination/ClassificationCard.vue`
- `frontend/src/components/Examination/ExaminationForm.vue`
- `frontend/src/components/Examination/SimpleExaminationForm.vue`
- `frontend/src/components/Frames/SegmentFramePicker.vue`
- `frontend/src/components/Report/ReportViewer.vue`
- `frontend/src/components/Reporting/LookupActionsBar.vue`
- `frontend/src/components/SelectFramesDemo/Demo.vue`
- `frontend/src/components/VideoExamination/VideoClassification.vue`
- `frontend/src/components/common/FileDropZone.vue`
- `frontend/src/components/icons/IconCommunity.vue`
- `frontend/src/components/icons/IconDocumentation.vue`
- `frontend/src/components/icons/IconEcosystem.vue`
- `frontend/src/components/icons/IconSupport.vue`
- `frontend/src/components/icons/IconTooling.vue`
- `frontend/src/views/Anonymization.vue`
- `frontend/src/views/AnonymizationCorrection.vue` — the live route loads the correction component directly.
- `frontend/src/views/Examination.vue`
- `frontend/src/views/FramesDemo.vue`
- `frontend/src/views/PatientAdder.vue`
- `frontend/src/views/ReportGenerator.vue`
- `frontend/src/views/Validierung.vue`

Vite has one source entry point (`src/main.ts`), router views are explicit dynamic imports, and the application has no `import.meta.glob` or global component auto-discovery. These files were unreachable from both runtime and test roots and had no external/configuration references.

### EndoReg obsolete management commands

- `endoreg_db/management/commands/check_auth.py` (139 lines) — unreferenced diagnostic command with stale setup instructions.
- `endoreg_db/management/commands/fix_missing_patient_data.py` (271 lines) — unreferenced data repair that inserted fabricated/default patient data; unsafe for clinical provenance and superseded by current import validation.
- `endoreg_db/management/commands/fix_video_paths.py` (239 lines) — unreferenced legacy path repair superseded by `ReconciliationService` and `reconcile_media_integrity`.
- `endoreg_db/management/commands/list_routes.py` (31 lines) — duplicate of the active, documented, tested `show_urls` command.
- `endoreg_db/management/commands/validate_video_files.py` (211 lines) — carried its own deletion TODO and was superseded by tested media-integrity reconciliation.
- `endoreg_db/management/commands/video_validation.py` (18 lines) — empty no-op command scaffold.

All command names were searched across EndoReg, LX-Annotate, LuxNix systemd/Nix scripts, tests, documentation, shell scripts, and configuration. Other low-reference management commands were retained because Django commands are manual entry points and their implementations remain valid.

### EndoReg legacy video/maintenance modules

- `endoreg_db/services/video_files/_streaming_compat.py` (110 lines) — private compatibility wrapper with zero imports. Live code uses `endoreg_db.services.video_files.streaming`, which remains intact and tested.
- `endoreg_db/utils/maintenance/check_video_files.py` (210 lines) — standalone, hard-coded legacy script superseded by `reconcile_media_integrity`; its stale setup-guide reference was replaced with current management-command guidance.
- `endoreg_db/utils/maintenance/fix_video_path_direct.py` (160 lines) — unreferenced raw-SQLite repair script with a hard-coded video ID; unsafe and superseded by typed reconciliation services.

## Functions/Methods Deleted

### `endoreg_db/models/media/video/video_file_queries.py`

- `_check_hash_exists`
- `_get_all_videos`
- `_get_video_by_pk`
- `_get_video_by_content_hash`

These private free functions had zero references. Their live behavior is implemented by `endoreg_db.services.video_files.queries`, while `VideoQuerySet.next_after` remains the active model manager extension.

### `endoreg_db/utils/hashs.py`

- `_sha256_field_file`

This private compatibility helper had zero references. Active report and video import workflows use `get_pdf_hash`, `get_video_hash`, and the typed storage/file-operation helpers.

No additional frontend symbol deletion was required after the file cleanup: `vue-tsc --noUnusedLocals --noUnusedParameters` completed successfully.

## Verification Notes

### Audit method

- Mapped frontend runtime reachability from `src/main.ts`, explicit router imports, and test roots; checked imports, dynamic imports, callbacks, Pinia stores, Vue components, tests, templates, and Vite configuration.
- Searched exact names, basenames, partial names, import strings, command strings, comments, documentation, Nix/systemd scripts, Django URLs, package barrels, and test monkeypatch targets across all three repositories.
- Treated Django management commands, migrations, REST endpoints, Celery tasks, model/public exports, Vite entry points, tests, and Nix/systemd units as entry points.
- Checked dynamic loading: Django command discovery, router lazy imports, `getattr`/import strings, Vue component discovery, Vite globbing, and test-only direct calls.
- Used strict Pyright and Vue TypeScript unused-symbol diagnostics, then manually excluded framework callbacks, public API, test-only helpers, and recovery entry points.

### Import, annotation, streaming, study, and hub safeguards

- Preserved `endoreg_db/import_files/report_import_service.py`, report anonymization/materialization/integrity services, upload APIs, and `frontend/src/views/reporting/ReportingShell.vue`.
- Preserved active video import/anonymization, temporal inference, post-validation, frame processing, current `services.video_files.streaming`, HLS views, encrypted-storage handling, and media-integrity reconciliation.
- Preserved study-cohort grouping/filtering source and endpoints, including report/video case grouping and hypothesis-filter preview behavior.
- Preserved all hub payload, transfer-ledger, authentication, worker, retry, cleanup, and recovery code.
- Preserved every helper in `modules/nixos/services/lx-annotate-local/scripts.nix` and the associated systemd services/options. LuxNix was a reference/configuration root for this audit; no LuxNix runtime helper was removed in this pass.
- Preserved migrations and valid manual commands, including low-reference recovery/data-loading commands. Test-only private streaming and temporal-history helpers were also retained.

### Completed checks

- `vue-tsc --noEmit --noUnusedLocals --noUnusedParameters`: passed.
- Frontend production `npm run build`: passed; 494 modules transformed.
- Focused frontend Vitest suite: **42 passed** across report upload, reporting shell preload, study cohort grouping/filtering, authenticated video streaming, reporting routes, and video annotation status/edit controls.
- EndoReg Pyright: **0 errors**. Remaining warnings are missing third-party stubs and private helpers directly exercised by tests; they were not deleted.
- Ruff on the modified EndoReg Python files: passed.
- EndoReg report import/anonymization integration suite: **3 passed**.
- EndoReg video import service suite: **16 passed**.
- EndoReg report-import, video-service, transfer-job, hub-endpoint, and secure-HLS contract suites: **61 passed**.
- Django `manage.py check`: completed successfully with only the expected deployment warning that asynchronous Celery features require `CELERY_BROKER_URL` in the current shell.
- Scoped `git diff --check` for every cleanup path: passed. The whole EndoReg
  worktree check still reports an unrelated pre-existing extra blank line at EOF
  in `endoreg_db/endoreg_rust_backend.pyi`; this pass did not modify that file.

The first direct backend pytest attempt failed before collection because the non-devenv shell could not locate `libstdc++.so.6` for NumPy. The identical suites were rerun inside the declared `devenv` environment and passed; this was not a product-code failure.

## Estimated Impact

The requested 5,000-line target was exceeded safely: this pass removes **more than 102,000 lines**, primarily because checked-in compiler output represented nearly the entire frontend source tree multiple times.

Expected runtime behavior is unchanged. The practical impact is a single authoritative TypeScript/Vue source tree, fewer obsolete clinical-data repair paths, less chance of Vite resolving stale JavaScript instead of TypeScript, smaller reviews and source distributions, and clearer ownership of current import, secure-streaming, reconciliation, study, and hub workflows.
