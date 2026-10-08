# SOA-QPS5 physical snapshot

## Purpose

The company-comparison dashboard uses saved datasets 24 and 25. Their original
SQL embedded all 3,163 source records in a large VALUES expression. Native Superset
parsed that expression for security-aware cache keys on every chart/filter request,
including cache hits. This operator migration stores the identical snapshot in
`examples.public.soa_qps5_awards_20261002` and replaces the repeated source SQL with
a short table reference. Dataset 22 and original dashboard 11 remain unchanged.

The data is the existing DPO SOA-QPS5 snapshot retrieved on 2 October 2026; this
operation does not fetch fresher records. It retains every source value and the
legacy derived columns, with the original PostgreSQL output types. Source provenance
and the original dashboard are described in the
[SOA-QPS operator guide](../../docs/admin_docs/configuration/focalbi-mcp.mdx).

## Contracts

- Superset's authenticated dataset API updates only the SQL and explicitly
  preserved defaulted flags. Dataset/column/metric UUIDs, labels, descriptions,
  ownership, filters, caches and chart references remain intact.
- Existing native company selection and market-denominator Jinja logic stays in
  saved dataset SQL. Neither renderer nor localization implementation is changed.
- The physical table has a source-SQL SHA-256 ownership comment. The existing
  analytical connection role receives SELECT on this table only.
- Before changing datasets, bidirectional EXCEPT ALL checks prove equality of
  the complete source row multiset, and SET ROLE checks analytical read access.
- A receipt stores original SQL and native metadata. UUID, SQL and metadata
  checks reject unexpected edits. Failed updates attempt to restore prior SQL.
- Configuration selects resources; the script contains no company-specific
  selection or rendering behavior. All business values remain snapshot content.
- The snapshot is persistent PostgreSQL data, not a cache. Redis chart-result
  caching uses the [operator query-result cache policy](../../docs/admin_docs/configuration/focalbi-mcp.mdx#query-result-caching),
  with a 24-hour default expiry. Cache expiry does not refresh this snapshot.

## Commands

Run from the repository root with an authorized native Superset session cookie.
Never print or commit that cookie. The shared client validates its origin.

```powershell
# Prepare the change without modifying the database or saved datasets:
python local-data/soa-qps5/materialize.py --cookie local-modules/focalbi-localization/.runtime/admin-cookie.json
# Apply once on a deployment that has not yet been materialized:
python local-data/soa-qps5/materialize.py --cookie local-modules/focalbi-localization/.runtime/admin-cookie.json --apply
# Restore original inline SQL; retain the physical snapshot:
python local-data/soa-qps5/materialize.py --cookie local-modules/focalbi-localization/.runtime/admin-cookie.json --rollback
# Re-enable from the same receipt after ownership and row-equality checks:
python local-data/soa-qps5/materialize.py --cookie local-modules/focalbi-localization/.runtime/admin-cookie.json --reapply
```

`materialize.json` identifies the source, target UUIDs, physical database/table,
container, provisioning role and analytical reader role. Review these before reuse.
The normal apply operation refuses an existing table or receipt. Retain ignored
`.runtime/materialization.json` as the rollback ledger; do not delete it on uninstall
of the rendering/localization modules. Those modules do not own analytical data.

For a future data refresh, use a versioned table, reconcile it against its reviewed
source, update references through native Superset, and validate all metrics and
guest scopes. Do not silently overwrite this snapshot or rely on cache expiry to
refresh source data. Physical-table deletion is deliberately not automated.

## Verification

Ruff checks apply to `materialize.py`. Rollback/reapply was exercised against the
running deployment. The localization module's documented embed and preservation
checks exercise the same native dashboard: 53 FDS records, HKD 72,002,518.80,
19 department relationships, and FDS+OPM totals of 150, HKD 183,079,390.79 and 52.
See [the performance report](../../.qa/embedded-loading-performance.md) for measured
before/after timings and the separate client proxy-discovery delay.
