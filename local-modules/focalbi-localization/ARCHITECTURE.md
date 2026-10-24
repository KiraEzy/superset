# Universal content localization contracts

Combined builds include the rendering module's optional deck.gl interaction
adapter. Native-only builds retain the native import. Chart flags and their
defaults belong to [the rendering contract](../focalbi-rendering/ARCHITECTURE.md);
localization passes saved form data through unchanged.

## Boundary

This module decorates display output. Resource UUIDs locate catalogs; resource names,
IDs and business values never activate features. FDS is authored validation content.
Every applicable existing/future resource uses the same field and renderer adapters.
New visualization adapters extend the registry, without dashboard-specific branches.

Superset owns definition loading, native filters/data masks, query construction,
chart-data requests, aggregation, caching, authorization and RLS. These functions
and immutable baseline files remain unchanged. `scripts/build.ts` compiles owned
wrappers and version-checked presentation substitutions into separate assets;
native files are checked before and after compilation. The overlay is necessary
where Superset 6.1.0 does not expose extension slots, including guest startup.

The backend and authoring dialog use the `.supx` framework's namespaced REST API,
Python registration and Module Federation asset loader. Native guest startup skips
extension discovery; its presentation context is compiled directly into the guest
dashboard. Guests never load the editor. Localization works without rendering;
combined deployment passes localization through the same post-transform interface
for both renderer engines.

## Storage, discovery and authorization

`backend/src/focalbi_localization/catalog.py` owns schema v1: a version table and
UUID-keyed, revisioned catalogs in an independent PostgreSQL database/role.
Setup/migrations are explicit operator commands, not native Superset migrations.
Native resource definitions are read-only inputs to `resources.py`. SQLAlchemy
datasets are the initial dataset adapter; additional datasource types need adapters.

Entry identity is `(resource type, UUID, stable field key, locale)` with an optional
layout-item namespace. Dataset columns/saved metrics use their native UUIDs;
adhoc metrics use native option names, table overrides use raw column keys.
Source SHA-256 fingerprints suspend translations after original text changes.
CAS revisions reject lost updates; batch saves/imports run in one transaction.

API root: `/extensions/focalbi/content-localization/catalog`:

| Method/path | Contract |
| --- | --- |
| GET `resolve/{type}/{nativeId}` | Authorized native ID → UUID and edit capability. |
| GET/PUT `resource/{type}/{uuid}` | Field discovery/catalog read; revision-checked separate save. |
| GET `bundle/{type}/{uuid}?locale=...` | Scoped presentation descriptors, resolved text and dictionaries. |
| GET `export/{type}/{uuid}` | Author catalog in versioned import format. |
| POST `import` | Fully validated/authorized batch with explicit UUID/field remapping. |

Every operation checks native resource access. Writes additionally require native
edit permission and ownership (or native administrator access). FAB read permission
alone grants no datasource/dashboard access. Guests may resolve an authorized
dashboard and fetch only its presentation bundle, including its charts' dataset
metadata; author catalogs, exports and writes are denied. No SQL is accepted and
no source rows are read by the localization API. Category maps may contain only
deliberately authored presentation metadata approved for that dashboard's viewers.

## Field coverage and resolution

Dataset: column/saved metric labels and descriptions, optional raw-value dictionaries.
Chart: title/description plus configured text controls, adhoc metric labels and native
table column display overrides. Dashboard: title, tabs, headings, Markdown, native
filter name/description and per-layout-occurrence chart/title-template overrides.
Charts without internal visualization adapters retain shared headings and their
native internal rendering. The dialog identifies unsupported visualizations and
lists the registered internal-label types. Native editor inputs always edit the
original text; idle title previews use the selected translation. Chart descriptions
use the native safe Markdown component, with native HTML retained for fallback.

Initial internal adapters: `big_number_total`, `pie`, `echarts_timeseries_bar`,
`mixed_timeseries`, `table`. `presentation.ts` decorates native transformed props.
Resolution order is **dashboard occurrence → chart → dataset → original**. Missing
locales never borrow another Chinese script. Removed fields are not presented and
are omitted from the next author save after an explicit notice.

Only display formatters, headings and column labels change. Raw series names, data,
row/column keys, filter values, option ordering, events and chart identities remain
native. Duplicate translated labels retain distinct raw identities. Tooltip text is
escaped and attributes/callback inputs are preserved. Existing numeric/date/currency
formatters remain authoritative; locale does not change HKD or `DD/MM/yyyy`.
Native CSV exports keep source labels/values in this release.

Translated dynamic templates preserve `{selection}` and use successful native
request selections, not filter drafts. They consume optional reusable native layout
presentation metadata; no custom selection/aggregation layer is introduced.

## Locale and interaction state

Priority: runtime bridge/native selection → explicit URL → saved native preview
preference → browser language → English. Regional aliases normalize to the three
canonical codes. Embedded viewers never inherit stored preview preferences.

The bridge protocol is `{type:'focalbi-content-locale', version:1, action, ...}`.
`hello`/`ready` acknowledge initialization; `set` carries a locale and request ID;
`ack` confirms the current metadata bundle. Both ends check source window and exact
origin; the inner frame accepts only native dashboard Allowed Domains. The helper
queues the latest language until ready. Invalid versions/locales/origins are ignored.

Metadata requests use generation guards against stale responses. Failures leave
readable original text, with a native preview warning. A locale change does not
navigate, recreate a frame, change native query inputs or request chart data.
Post-transform callbacks preserve renderer identity; filters, tabs, legend/zoom,
sort/search/pagination and renderer preference remain owned by their existing layers.
`EchartState.ts` observes raw native legend/zoom events and restores their display
state after native `notMerge` redraws. It resets on changed native result data, retains
raw identity keys, and never dispatches filter actions or chart-data requests.
The post-transform adapter also supplies the remembered keys before drawing, so
transient metadata fallback and engine changes retain the same display state.
`DataTable.tsx` distinguishes metadata redraws from new native results and column
identities. Display redraws retain client sort, search and pagination; native user
actions, changed query results and removed columns keep native reset behavior.
These adapters observe existing containers and add no layout DOM wrappers.
Repackaging equivalent native JSON results retains interaction identity. No result
data is changed or used to construct a query by these state adapters.

## Maintenance

`controls.ts` owns typed built-in dashboard-control messages; `ControlMessages.tsx`
resolves them from the individual viewer context, without global locale state or
catalog requests. Resource IDs do not participate. `TableControls.tsx` implements
the native search/page-size presentation contracts and forwards native callbacks
and input references. Custom controls/messages remain authoritative.

`FilterDropdown.tsx` adds localized Select all/Clear buttons to native multiselect
filter menus through the version-checked `SelectFilterPlugin` compilation adapter.
`filterActions.ts` collects enabled, loaded options matching the current search;
it skips synthetic new-option rows and deduplicates by raw scalar identity, not
translated labels. Select all unions those values with the current selection.
Clear sends an empty array to the same native `handleChange` callback used by
individual selections. Zero, false, empty strings and null remain valid identities.
No extra option fetch, query builder, reducer or data-mask implementation is added.
Loading/disabled states prevent actions; required validation and Apply remain native.
The toolbar does not appear on single-select filters. Native source and immutable
renderer copies remain unchanged. Multiselect inputs disable native `allowClear`
so whole-field clearing lives in the dropdown; individual tag removal remains native.
Removing this module removes the toolbar and restores the native clear affordance.
Search text is observed on input, before native debouncing, so rapid typing and
option refreshes cannot turn Select all into a selection of unmatched options.
Only the popup's local state changes on input: rerendering the parent Select here
would cancel its pending native debounce. The observer detaches on unmount.
Popup focus adapters reserve Tab for the buttons and suppress native blur resets
only during popup focus transitions; keyboard activation returns focus to the input.

The post-transform adapter supplies legend selector titles without changing action
types and localizes recognized native total text without recalculating its value.
Version-checked compilation adapters cover filter controls, native/baseline/fork
sort controls, table search-column labels and the rendering toolbar. Their on-disk
sources stay byte-identical. No filtering/query operations are substituted.
Use `@apache-superset/core/translation` for native translation functions. In the
pinned host, the eager `@superset-ui/core` runtime does not expose `t`, despite
its type declarations; module type checks alone do not catch that import failure.


`compatibility.json` pins Superset 6.1.0 source revision/protected file hashes;
Docker overlays pin the running image digest. Native frontend lockfiles own package
versions. Review upstream adapter/source changes before refreshing provenance.
No edits to core or immutable baseline copies are permitted to bypass compatibility.

Activation states compose: neither, rendering, localization, or both. Localization
owns combined assets/backend only while active. Rendering scripts delegate composing
builds to it; removing either preserves the other. Own removal restores prior native
configuration, removes recorded grants and retains catalogs unless explicitly purged.
[README.md](README.md) owns setup, test, upgrade and removal commands.
