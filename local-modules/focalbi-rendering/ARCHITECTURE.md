# Native dashboard rendering overlay

## Boundary

The module reuses Superset's dashboard application. It has no separate viewer,
data service, filter store, query builder or aggregation engine. Native Superset
and MCP source remain unchanged by this module.

| Stage               | Owner                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------- |
| 1. Load definitions | Native routes, bootstrap/API loaders, saved charts, layout, metadata and datasets.                      |
| 2. Manage filters   | Native Redux/data masks, filter scopes, Apply, cross-filters and own state.                             |
| 3. Build queries    | Original visualization plugins' buildQuery registrations and query context.                             |
| 4. Fetch results    | Native chart actions, chart-data API, cache, guest authorization, RBAC/RLS and loading/error lifecycle. |
| 5. Transform/draw   | Module dispatch chooses copied baseline or fork implementations.                                        |
| Display headings    | Module header derives titles from successful native request selections.                                 |

Native editor Save/Discard/undo remains authoritative. Explore renders natively
outside the dashboard context. Chart addition, removal and arrangement require no
module dashboard JSON, source provisioning or rebuild. Unsupported chart types
use their native renderer with a fallback label; native filters are not fallbacks.

## Integration

`scripts/build.ts` uses native Webpack entries/configuration. Replacements wrap
DashboardBuilder, SliceHeader, SuperChartCore and table interaction restoration;
aliases import their original implementations. Native buildQuery registrations
are never replaced. SuperChartCore retains native ChartProps, hooks and lifecycle.
The bar adapter preserves rawFormData when adding the native bar-series default.
It honors native sum-sort controls for a single categorical bar series by ordering
returned value/category pairs. Multi-series sorting stays native; query results,
rank membership, null values and totals are unchanged. Both engines use the adapter.

`frontend/registry.tsx` registers transform/component pairs, not ChartPlugins.
Keys: big_number_total, pie, echarts_timeseries_bar, mixed_timeseries and table.
New types extend this registry and the capability declarations in settings.ts.
No company, resource ID or dataset name may activate implementation behavior.
IDs locate configured resources only. Business calculations remain native.

## Optional presentation contract

Settings live on a native layout item's `meta.focalbi_rendering`, validated by
`frontend/settings.ts` and documented in [presentation.schema.json](presentation.schema.json).
Every dashboard can omit these settings.

- `title`: native select-filter ID, single-selection template using `{selection}`,
  and multiple-selection text. The filter must target a column and include the
  chart in its native scope. Empty selections retain the saved chart name.
- `highlight`: native filter ID, returned dimension, palette, remainder color and
  optional per-label colors. Pie/bar options change colors only, never grouping,
  ranking, rows or metric values. Unsupported/missing dimensions show a warning.
- `secondaryBehindPrimary`: mixed-timeseries drawing order. Metrics, axes, formats,
  opacity and time grain otherwise come from native chart settings.

The edit-mode Presentation popover uses native updateComponents; dashboard
Save/Discard/undo/redo govern persistence. Titles use successful request values,
not filter drafts. Native requests retain native per-chart loading/error behavior;
there is no custom dashboard-wide transaction or failed-request override.

Both engines receive identical data and presentation inputs. Preference is local
storage `focalbi.renderer`, default fork. Switching changes component dispatch only,
without navigation, query or data-mask action. ECharts legend/zoom state persists.
Native client-table sort/search/page/column state is restored across a component
swap; subsequent data updates and user actions retain native behavior. Native own
state remains authoritative for server pagination.

Post-transform presentation callbacks are carried through a stable raw-props
envelope. Changing display metadata updates the envelope's callback through native
postTransformProps without recreating the loadable renderer. The independent
[localization module](../focalbi-localization/ARCHITECTURE.md) composes through this
interface. Activation/removal scripts retain localization when it is active.

## Business calculations and access

The company example uses native saved datasets, SQL metrics and scoped filters.
Native SUM/COUNT/COUNT DISTINCT perform aggregation. A null-aware JSON pair counts
distinct company-department relationships. Trusted saved Jinja SQL consumes the
company filter inside a comparison dataset to retain the eligible market
denominator and group unselected companies. Annual ratios use SQL NULLIF.
Native SQL template processing is an independent operator flag, not renderer
activation; only trusted native dataset authors should edit these templates.

The retired extension endpoints, Python source fetch/count and aggregation pipeline,
custom filter panel, standalone React viewer, per-dashboard business JSON/schema
and replacement token service are removed. Duplicate shared core code is retired;
immutable renderer snapshots remain. Embedding uses native `/embedded/<uuid>` and
the SDK. The website issuer accepts only an operator-approved resource; native
Superset owns guest expiry, dashboard/dataset access and RLS. Renderer switching
cannot broaden access. The original dashboard is the rollback target.

Ownership cleanup refuses renamed or externally shared resources.
[README.md](README.md) owns deployment, verification and removal commands.
