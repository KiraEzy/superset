# FocalBI content localization

Localize the **same saved resources** in English (`en`), Traditional Chinese
(`zh-Hant`) and Simplified Chinese (`zh-Hans`). Content language is independent
of Superset's application UI language. Native definitions, queries, permissions,
RLS, exports and formatting remain authoritative. Dashboard viewing controls follow
the selected content language; application navigation and editors keep their UI language.

The `.supx` packages the backend API and translation dialog. Superset 6.1.0 lacks
several presentation/editor extension hooks, so deployment also builds a removable
frontend adapter. Installing the `.supx` alone does not activate those surfaces.
See [ARCHITECTURE.md](ARCHITECTURE.md) for contracts and supported fields.

## Setup and activation

Use the existing [Docker operator setup](../../docs/admin_docs/configuration/focalbi-mcp.mdx)
and its installed `superset-frontend/node_modules`. Node 22.22+, Python, Docker
Compose and the PostgreSQL service are required. Do not update upstream packages
independently of the compatibility review.

```powershell
cd local-modules/focalbi-localization
# Localization alone:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/activate.ps1
# Compose with the rendering module:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/activate.ps1 -WithRendering
# Reuse an already verified build after configuration/backend changes:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/activate.ps1 -WithRendering -SkipBuild
docker exec superset_app python /app/focalbi-localization/scripts/health.py
```

Activation pins the Superset image digest, recreates only the web service, provisions
the `focalbi_localization` database and separate role, and runs owned migrations.
Credentials and permission receipts are ignored under `.runtime/`. Native database
tables and analytical connections are not used to store translations. Native FAB
permission grants required to expose the extension are recorded for removal.
MCP, workers and the website's token/dashboard binding are retained.

Artifacts are `dist/focalbi.content-localization-1.0.0.supx`,
`dist/native/assets` or `dist/combined/assets`, and `dist/client/`.
`compatibility.json` records source revision and protected query/display hashes.
Both builds stop on incompatible protected source; combined builds also verify the
immutable renderer snapshot. `--record-compatibility` is a maintainer operation
after a deliberate source review, not an upgrade workaround.

## Author translations

Save a dataset, chart or dashboard natively first. Open **Translations** in its
editor/preview, review original fields, and enter the desired languages. Dataset
edit dialogs provide the entry point inside the native datasource editor.
Dashboard fields include per-layout-occurrence chart overrides and existing
selection-aware title templates. **Save translations** is a separate transaction.
Closing discards unsaved translation drafts; native Save/Discard remains native.
Use **Content language** on dashboard or Explore to preview saved translations.

Blank/missing entries show original text. Changed originals suspend old translations
until explicitly reviewed. A conflicting save retains the draft and requires reload.
Category dictionaries are optional authored metadata, never harvested source rows.
Their JSON uses raw scalar values and locale text, for example:

```json
[{"value":"North","values":{"zh-Hant":"北區","zh-Hans":"北区"}}]
```

Export saved catalogs from the dialog or extension API. Imports require explicit
source UUID → target UUID mappings when copying resources, field mappings where
column/metric UUIDs change, current target revisions, and reviewed source hashes.
Bundle imports validate every resource and commit atomically.

FDS sample content is [fixtures/fds.json](fixtures/fds.json), not implementation.
Apply it using an authorized native session cookie file without printing credentials:

```powershell
python scripts/seed.py fixtures/fds.json --origin http://localhost:8088 --cookie .runtime/admin-cookie.json
```

The sample translates labels, themes, the remainder category and three department
names. Other free-text project records retain their source text. Census catalogs
are not seeded or changed.

## Website integration

### Built-in dashboard controls

Filter headings, Apply/Clear, option counts, table search/page size/empty results,
legend All/Invert, value sorting, donut totals and the renderer dropdown use the
module's built-in three-language control dictionary. They need no per-resource
catalog entries. Counts and already-formatted totals retain native values; custom
legend titles and table controls/messages retain their authored behavior.

Controls update from each viewer's locale even if its content catalog is unavailable.
No global Superset UI catalog is changed. Native and baseline files remain intact:
version-checked display substitutions run only while compiling the module's assets.

Native multiselect dropdowns include **Select all** and **Clear**, including
server-search filters. Select all adds the currently available matching options
and preserves existing selections; its count is the number of additional values.
It does not fetch every value in the database or bypass native option limits.
Clear removes the entire selection in that field. Both actions edit the native
filter draft. Multiselect fields omit the hover-only whole-field clear icon;
use the dropdown Clear action instead. Individual selection tags keep their remove icon.
**Apply filters** and required-field validation still apply.
Labels follow the viewer's English, Traditional Chinese or Simplified Chinese.
With a dropdown open, Tab reaches the action buttons; Enter or Space activates
them, and Escape closes the menu and returns focus to the filter.
Single-select dropdowns retain their native behavior. Implementation and adapters
are owned by [frontend/FilterDropdown.tsx](frontend/FilterDropdown.tsx) and
[scripts/source-loader.cts](scripts/source-loader.cts).

```powershell
node --experimental-strip-types scripts/client.ts
# In a consuming website, install the generated dist/client/*.tgz package.
```

Pass `dashboardUiConfig.urlParams.content_locale` through the native Embedded SDK.
Attach `createLocaleBridge(iframe, locale)` from
`@focalbi/content-localization-client` to its existing iframe, then call
`bridge.setContentLocale(locale)`. Call `bridge.destroy()` on teardown.
The bridge checks exact origin, source window and protocol version, queues the latest
language until ready, and acknowledges applied metadata. Configure the dashboard's
native Allowed Domains with **exact origins** including ports.

The FDS website relays `useI18n().locale` through its existing outer embed document
to the SDK iframe. Language changes keep both frames mounted. No additional token
service, dashboard UUID or query parameters beyond `content_locale` are required.

## Verification

```powershell
python -m venv .runtime/venv
.runtime/venv/Scripts/python.exe -m pip install -r requirements-test.txt
.runtime/venv/Scripts/python.exe -m unittest discover -s tests -v
node --experimental-strip-types scripts/test-frontend.ts
node --experimental-strip-types scripts/test-controls-overlay.ts
node --max-old-space-size=12288 --experimental-strip-types scripts/typecheck.ts
node --max-old-space-size=12288 --experimental-strip-types scripts/build.ts --with-rendering
node --experimental-strip-types scripts/verify-browser.ts
python scripts/verify-api.py
node --experimental-strip-types scripts/verify-authoring.ts
node --experimental-strip-types scripts/verify-embed.ts
node --experimental-strip-types scripts/verify-preservation.ts
node --experimental-strip-types scripts/verify-controls.ts --rendering
node --experimental-strip-types scripts/verify-filter-actions.ts
python scripts/integrity.py --with-rendering
```

Live browser verification uses the documented development login by default; set
`FOCALBI_TEST_ORIGIN`, `FOCALBI_TEST_USERNAME` and `FOCALBI_TEST_PASSWORD` as needed.
Credentials/tokens stay out of output. Evidence goes to ignored `test-results/`.
Own TypeScript diagnostics fail the check; existing upstream diagnostics are recorded
separately. Native computer-use verification requires a connected browser surface.

`verify-filter-actions.ts` opens the guest FDS page on port 3040 by default; set
`FOCALBI_TEST_URL` to another instance of that page. It checks dropdown shortcuts,
search, required-filter validation, keyboard access and all three viewer languages.
Evidence is saved under `test-results/filter-actions/`. It changes only the browser's
filter drafts, never saved dashboard definitions or translation catalogs.

`verify-api.py` uses the authorized cookie produced by `verify-browser.ts`, creates
synthetic resources through native APIs, and records their UUIDs in
`.runtime/localization-test-resources.json`. It does not change census resources.
`verify-authoring.ts` checks dataset/Explore dialogs, all five unrelated chart
types, descriptions, failed catalogs and active tabs. Remove only that recorded
fixture after validation with `python scripts/cleanup-tests.py`; retain the ledger
until cleanup succeeds. For deployment checks, `scripts/verify-mode.ts` accepts
`--localization` and/or `--rendering` to assert the expected active modules.

## Removal and rollback

To revert only the multiselect shortcuts, restore their `SelectFilterPlugin`
adapter changes in `scripts/source-loader.cts`, the exports in `frontend/hooks.ts`,
the three `filter.*` control messages, and the associated tests/documentation as
one change. Remove the now-unused `FilterDropdown.tsx` and `filterActions.ts` files,
then rebuild and activate the same composition using the commands above.
Review the diff before restoring files that contain subsequent work. This keeps
the rest of localization, rendering, saved filters and translation catalogs intact.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall.ps1
# Explicitly destructive: also delete the owned translation database and role.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall.ps1 -PurgeData
```

Default removal restores the original configuration and whichever rendering module
is active, removes recorded extension permission grants, and retains translation
data. Website resource/token binding remains unchanged. Retain `.runtime/` when
reinstalling to preserve credentials and ownership records. Delete the module folder
only after disabling it and confirming there are no mounts referencing it.

Rendering activation/removal composes through this module when localization is active.
Removing rendering retains localization and restores rendering's recorded website
target. Re-enabling both uses the same native data path; no duplicate dashboard is
created. The developer bundles disable minification; review bundle size and optimize
deliberately before production deployment.
