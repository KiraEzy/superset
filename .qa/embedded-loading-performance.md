# Embedded dashboard loading investigation

Measured 2026-10-05 on `http://192.168.10.27:3010/?hero=ribbon#focal-bi`
using a fresh automated Chrome context. No saved dashboard, dataset, native source
or deployment configuration was changed by this investigation.

## Measured behavior

- Website config/token requests began about 12.6 seconds after navigation; their
  server response times were approximately 2 ms each.
- Superset dashboard definitions completed around 14.7 seconds. Chart-data
  requests began around 15.4 seconds.
- The source table completed at 26.18 seconds: 4.85 seconds before the request
  could be sent, then 5.94 seconds awaiting its response. It returned 53 cached
  rows. The annual chart completed at 27.01 seconds.
- Five native filter requests completed between 29.84 and 31.64 seconds; these
  also hit cache. Browser queue time reached 9.87 seconds.
- Direct sequential table API replays took 1.110 seconds cached, 4.479 seconds
  with force refresh, and 1.062 seconds cached. These replay times exclude the
  full page's concurrent request load.
- PostgreSQL EXPLAIN ANALYZE on the equivalent selected-record query measured
  11.481 ms planning and 1.128 ms execution, returning 53 rows. No long-running
  analytical query or lock wait was observed during sampling.
- The Superset frame loaded 73 resources totaling about 8.05 MB encoded body
  size. Small chart asset requests also queued behind other work. Frontend
  startup contributes, but it does not explain slow cached chart API responses.

## Identified cause

Saved datasets 22, 24 and 25 contain approximately 860,000 characters of SQL each:
the source snapshot is embedded as a large VALUES expression. Native
`SqlaTable.get_extra_cache_keys` calls `collect_rls_predicates_for_sql` for virtual
datasets before retrieving cached results. The SQL parser must process the entire
snapshot to determine the security-aware cache key.

A warmed native Flask test-client profile of the same authorized cached table
request measured 3.109 seconds overall, including 2.194 seconds generating cache
keys and 2.186 seconds collecting RLS predicates/parsing SQL. Profiling adds overhead;
these numbers identify where time is spent and are not direct production latency
estimates. The cache hit was confirmed. The first profile also included cold engine
imports; the warmed profile excludes those as the primary explanation.

The running Gunicorn configuration has one gthread worker with 20 threads. Eight
charts plus five filter queries cause concurrent Python parsing and browser request
queuing. The UI's “Waiting on database” label covers the complete chart request;
it does not prove PostgreSQL execution is the bottleneck.

## Recommended correction

Follow-up configuration inspection confirmed `DATA_CACHE_CONFIG` and `CACHE_CONFIG`
use Redis DB 1 with a 300-second default timeout. Datasets 22/24/25 and charts
131-138 have no cache-timeout overrides. Filter-state storage is separate from
chart-result caching. Extending result expiry alone cannot avoid SQL parsing before
cache lookup.

1. Import the reviewed snapshot into a physical PostgreSQL table, preserving raw
   data, types and source provenance. Reconcile counts and monetary totals.
2. Replace the inline VALUES portions with short references to that table; preserve
   existing dataset identities, native company/market logic, filter scope, permissions
   and RLS. Verify affected charts and guests before retiring the original snapshot.
3. Remeasure warm/cold dashboard loads. Then tune worker processes and production
   frontend delivery if still needed. Do not bypass security-aware cache validation.

The earlier website timeout fix only prevents the embed from being discarded after
45 seconds. It does not reduce this server-side parsing or frontend startup cost.

The configured Codex MCP runtime could not discover tools during the follow-up:
its header helper exceeded the runtime's 10-second limit. A standalone helper check
succeeded in 10.63 seconds without exposing its token. No dataset migration or
cache configuration change was applied through an alternative write path.

Evidence is in localization `test-results/loading-network.json`,
`.runtime/loading-profile.log` and `.runtime/chart-cprofile-warm.log`. The temporary
captured guest-token request was deleted from host and container after profiling.

## Optimization applied and verified

The reviewed source was materialized into
`examples.public.soa_qps5_awards_20261002`. Bidirectional EXCEPT ALL comparison
verified all 3,163 rows, including duplicates and derived fields. Datasets 24/25
retain their UUIDs and full column/metric metadata, using 201/418-character SQL
instead of 860,247/860,464 characters. Original dataset 22/dashboard 11 are intact.
The configured MCP connection failed and lacks in-place dataset update capability;
the SQL-only changes used Superset's authenticated native dataset API. No native
metadata-table SQL updates or renderer/core source changes were made.

The analytical `examples` role has SELECT on the new table. Its initial missing
grant was caught by guest verification and corrected before final acceptance.
Provisioning checks now verify reader access before updating dataset SQL.
Rollback and reapply both succeeded. The final receipt records active materialized
SQL; ownership hashes and the source row multiset were rechecked on reapply.

| Request | Before | After |
| --- | --- | --- |
| Sequential cached table API | 1,062-1,110 ms | 62-70 ms |
| Sequential forced-refresh table API | 4,479 ms | 190 ms |
| Table response during cached dashboard load | 4.85 s queue + 5.94 s server | 0.175 s queue + 0.219 s server |

The standard-browser page reached source rows at 18.95 seconds, down from
26.18 seconds to receive the earlier table response (different visual/network end
points). A separate direct-connection fresh-browser run, with uncached chart
results after rollback/reapply, displayed source rows at 7.02 seconds. Its chart
requests took 430-572 ms; cached/forced sequential replays were 82-114/207 ms.
Timing varies with load and browser cache; these are observed runs, not guarantees.

A separate client proxy-configuration delay remains outside the application.
Navigation showed about 12 seconds before DNS/connect/requestStart for the LAN IP;
localhost sent immediately. Windows auto-detection and a PAC URL are configured.
An isolated Chrome test with `--no-proxy-server` sent the LAN request immediately
(2.5 ms response start); disabling HTTPS upgrades retained the delay. Curl reached
the original server in 65-81 ms. A temporary production-preview server showed the
same delay and was stopped after the test. No Windows proxy settings were changed.
The precise PAC/discovery failure has not yet been isolated. A DIRECT rule alone
may not help if retrieving the PAC script itself causes the delay. Client proxy
changes are explicitly outside this optimization's scope and were not applied;
visitors do not need configuration changes to benefit from the server-side fix.

Final native embed checks pass on the exact ribbon URL: all plots, three locales,
both engines, independent embeds, guest isolation, and zero locale-triggered data
requests. Multi-company preservation passes with 150 records, HKD 183,079,390.79
and 52 department relationships. FDS remains 53/HKD 72,002,518.80/19. Native source
hashes (25) and immutable baseline hashes (357) pass. Ruff passes for the migration.
Evidence: localization `test-results/materialized-speed.json`,
`materialized-speed-direct.json`, `preservation.json`, and `lan-embed.json`.

Setup, rollback and refresh contracts are maintained in the
[snapshot operator guide](../local-data/soa-qps5/README.md).
