# 24-hour Redis query-result caching

Verified 2026-10-06. The shared Docker operator configuration sets
`DATA_CACHE_CONFIG.CACHE_DEFAULT_TIMEOUT` to 86,400 seconds, replacing the
five-minute default. This covers native query results from tables/datasets for
charts, tables and filter options; it does not cache or refresh the physical
source tables themselves.

## Configuration and deployment

- Changed `docker/pythonpath_dev/superset_config_docker.py` only to add the
  query-data cache configuration and its environment import. An AST comparison
  confirms all previous operator settings remain unchanged.
- Native chart/dataset/database timeout precedence remains intact. All 51 saved
  datasets inherit the default; no resource-level overrides were present or added.
- Metadata/thumbnail defaults remain 300 seconds. Filter-state and Explore-state
  lifetimes and Redis connection settings remain unchanged.
- Reloaded the web, MCP and Celery services. A zombie-process error prevented
  the scheduler's normal restart. Both workers were recreated with the same
  installed image digest, and `init: true` was added to their image-tag Compose
  configuration to reap child processes. Both are running, with the worker healthy.
- Rendering/localization activation and website resource bindings were retained.
  No Superset/MCP query, permission or renderer implementation files changed.

## Verification

| Check | Result |
| --- | --- |
| Effective settings | PASS: query-data timeout is 86,400 seconds; all other cache configurations, dataset count and resource overrides match the pre-change state. |
| Real table request | PASS: authenticated native table query for dataset 24/chart 138 returns 53 FDS A/Minor records totaling HKD 72,002,518.80. |
| Redis lifetime | PASS: a forced request writes the real query-result key with a measured TTL of 86,400 seconds. |
| Cached repeat | PASS: the repeated request reports `is_cached: true`, the same cache key and identical records. |
| Worker recovery | PASS: both Celery containers run the original pinned image with Docker init enabled; web, worker and MCP health checks pass. |
| Repository checks | PASS: configuration parses, Compose resolves, `git diff --check` passes and no native Superset/MCP implementation diffs appear. |

Evidence: [table/cache result](../local-modules/focalbi-rendering/.runtime/redis-cache-query-result.json)
and [change receipt](../local-modules/focalbi-rendering/.runtime/redis-cache-change.json).
Pre/post effective settings, the prior operator config and the image-preserving
worker recovery overlay are in ignored `.runtime/` files. No Redis flush, source
table change or saved resource change was performed. Existing cache entries keep
their original expiry until replaced; the new lifetime governs new writes.

## Documentation

The [operator cache guide](../docs/admin_docs/configuration/focalbi-mcp.mdx#query-result-caching)
owns settings, reload guidance and cache semantics. The
[snapshot guide](../local-data/soa-qps5/README.md) links to that policy and makes
clear that source snapshot refresh is independent of Redis expiry. This backend
configuration change was validated through its native HTTP and Redis behavior;
no frontend rebuild or new browser acceptance run was needed.
