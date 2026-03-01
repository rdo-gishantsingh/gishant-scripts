## COMPLETED

### [USER-661](https://ro.youtrack.cloud/issue/USER-661): HITRO---201-Animatic-ingestion-error

**Done**
- Fixed issue where animatic ingestion failed due to missing Ayon Animatic task errors.
- Verified fix allows sequences to publish successfully.

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

### [USER-558](https://ro.youtrack.cloud/issue/USER-558): Ayon-Settings---yaml-dump

**Done**
- Marked ticket as obsolete.
- Work superseded by [PIPE-617](https://ro.youtrack.cloud/issue/PIPE-617) (Ayon Bundle Manager), which provides comprehensive configuration management.

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

### [PIPE-678](https://ro.youtrack.cloud/issue/PIPE-678): Regarding-migrating/syncing-Editorial-data-from-old-storage-to-new-storage

**Done**
- Confirmed with Kasi (Edit team) that all data has been successfully copied to the new storage locations (`\\rdoshyd\jobs` and `\\rdoshyd`).
- Closed ticket upon confirmation.

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

### [USER-464](https://ro.youtrack.cloud/issue/USER-464): Ayon---MTL-Hookup-Tool-Not-Working-for-Crowd-Data

**Done**
- Ticket marked as obsolete (Shader variation setup is handled by Show FX TDs).

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

### [USER-686](https://ro.youtrack.cloud/issue/USER-686): Ayon---unwanted-loader-window-automatically-opens

**Done**
- Fixed the launcher behavior where an unwanted loader window persisted after opening a Nuke scene.
- Confirmed fix with Yogesh.

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

### [PIPE-716](https://ro.youtrack.cloud/issue/PIPE-716): Add-VFX-Reference-Platform-Python-packages-(3.10,-3.11,-3.13)

**Done**
- Created and merged Rez packages for Python versions aligned with VFX Reference Platform (CY2023, CY2024/25, CY2026).
- PR: https://github.com/redefineoriginals/rdo-rez-external-packages/pull/10
- PR: https://github.com/redefineoriginals/rdo-rez-external-packages/pull/11
- PR: https://github.com/redefineoriginals/rdo-rez-external-packages/pull/12

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

### [USER-529](https://ro.youtrack.cloud/issue/USER-529): Ayon-UE---Reuse-Rig-uasset

**Done**
- Implemented logic to check for existing `.uasset` files to prevent redundant conversion of Rigs in Unreal.
- Feature is complete and ticket is closed.

**Current Work**
- None

**Pending**
- None

**Blockers**
- None

## IN PROGRESS

### [USER-319](https://ro.youtrack.cloud/issue/USER-319): Ayon-Maya---Kitsu-Breakdown-Loader-MVP-Tool

**Done**
- Analyzed codebase and defined MVP scope (Context query, Kitsu fetch, Scene comparison, Load missing, BBOX stacking).
- Implemented MVP on feature branches.
- PR: https://github.com/redefineoriginals/rdo-maya-layout-shelf/tree/USER-319_KitsuBreakdownLoaderMVP
- PR: https://github.com/redefineoriginals/rdo-core-kitsu-utils/tree/USER-319_BreakdownUtils

**Current Work**
- Paused main tool development to refactor credential management (moved to PIPE-731) to allow API key usage instead of user login.

**Pending**
- Waiting for [PIPE-731](https://ro.youtrack.cloud/issue/PIPE-731) to merge to resolve authentication requirements.

**Blockers**
- Dependency on credential refactor (PIPE-731).

### [PIPE-731](https://ro.youtrack.cloud/issue/PIPE-731): Refactor-credential-management-for-Ayon-and-Kitsu-utils

**Done**
- Removed hardcoded credentials and implemented layered resolution (Env Vars -> User .env -> Team .env).
- Added Windows path support and `python_dotenv` dependency.
- PR: https://github.com/redefineoriginals/rdo-core-ayon-utils/pull/10
- PR: https://github.com/redefineoriginals/rdo-core-kitsu-utils/pull/12

**Current Work**
- Waiting for code review on the raised PRs.

**Pending**
- Code Review.

**Blockers**
- None

### [PIPE-727](https://ro.youtrack.cloud/issue/PIPE-727): Create-shared-logging-library-(rdo-core-logging)

**Done**
- Completed v0.2.0 major overhaul using `structlog` and `Rich`.
- Implemented context binding and zero-config start.
- PR: https://github.com/redefineoriginals/rdo-core-logging/pull/1

**Current Work**
- Addressing any feedback from the code review phase.

**Pending**
- Code Review.

**Blockers**
- None

### [PIPE-446](https://ro.youtrack.cloud/issue/PIPE-446): Data-Deletion-Process

**Done**
- None

**Current Work**
- None (Currently on hold to prioritize fixing existing PRs).

**Pending**
- None

**Blockers**
- None

### [PIPE-523](https://ro.youtrack.cloud/issue/PIPE-523): Update-AYON-publishers-to-link-Ayon-versions-and-Kitsu-revisions

**Done**
- Updated publishers to parse dict data to version creation.

**Current Work**
- None

**Pending**
- Clement Poulain (Code Review).

**Blockers**
- None

### [USER-422](https://ro.youtrack.cloud/issue/USER-422): Add-Write-Node-for-ProRes-MOV-Renders-in-Nuke

**Done**
- Implemented fix and provided test command for the Ayon launcher.
- Demoed to Yogesh and Venu; confirmed workflow meets requirements.

**Current Work**
- Waiting for final code review to merge.

**Pending**
- Code Review.

**Blockers**
- None

### [PIPE-617](https://ro.youtrack.cloud/issue/PIPE-617): Ayon-Bundle-Manager---Bundle-Lifecycle-&-Configuration-Management-Tool

**Done**
- Implemented CLI tool for bundle operations, config management, and deployment.

**Current Work**
- None

**Pending**
- Code Review (Status is "Code Review").

**Blockers**
- None

### [USER-424](https://ro.youtrack.cloud/issue/USER-424): Ayon-Maya---Model-High-Review-Validator

**Done**
- Deployed validator to the **staging bundle**.
- Configured settings to allow per-project control and category exclusion.

**Current Work**
- None

**Pending**
- Rich (Testing/Feedback on staging).

**Blockers**
- None

### [USER-660](https://ro.youtrack.cloud/issue/USER-660): BNCRO|Inconsistent-Character-Orientation-When-Importing-Animation-in-Unreal-via-Ayon

**Done**
- Identified bug in Unreal add-on regarding "_GRP" naming classification.
- Provided patch command for testing.

**Current Work**
- Waiting for confirmation from Ganesh/Kiran on the fix.

**Pending**
- Ganesh.kolanu (Testing).

**Blockers**
- None

### [USER-697](https://ro.youtrack.cloud/issue/USER-697): BNCRO-|-Long-Hair-&-Body-Characters-Shot-FBX-Cache-import-tool

**Done**
- None

**Current Work**
- Reviewing requirements against Rich's feedback regarding existing LayoutMain capabilities.

**Pending**
- None

**Blockers**
- None

### [USER-687](https://ro.youtrack.cloud/issue/USER-687): Ayon---File-Versions-Not-Visible-in-Ayon-Launcher-for-Comp-Team

**Done**
- Agreed with Comp team to remove the confusing work file list from the Launcher (relying on in-host tools).
- Implemented removal of UI element and deployed to **staging**.
- PR: https://github.com/redefineoriginals/ynput-ayon-core/pull/32

**Current Work**
- None

**Pending**
- Yogesh (Final confirmation in Staging to close ticket).

**Blockers**
- None

### [PIPE-693](https://ro.youtrack.cloud/issue/PIPE-693): Refactor-rdo-editorial-edl-ingester-into-modular-components

**Done**
- Decoupled logic into reusable libraries (media-utils, ayon-utils, kitsu-utils).
- Addressed all PR review comments.

**Current Work**
- Waiting for final approval/merge.

**Pending**
- Code Review.

**Blockers**
- None

### [PIPE-588](https://ro.youtrack.cloud/issue/PIPE-588): Add-on-Testing:-ayon-houdini

**Done**
- None

**Current Work**
- None

**Pending**
- Decision on closing ticket (recommended closing as we use the default Ayon addon).

**Blockers**
- None