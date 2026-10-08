# Universal content localization

- Every feature must apply identically to all supported resources. Resource IDs
  locate configuration, never activate behavior. FDS is test content only.
- Native Superset owns definitions, query building, filters, chart-data fetching,
  aggregation, caching, permissions, and RLS. Never rewrite those stages.
- Never edit Superset/MCP core or immutable renderer snapshots. Integrate through
  this module's extension and removable frontend/deployment adapters.
- Keep raw keys and values intact. Localize display text, not interaction identity.
- Keep translation state in the module-owned database. Native Save/Discard and
  translation Save are separate transactions.
- Update README (commands), ARCHITECTURE (contracts), operator documentation,
  compatibility provenance, and meaningful tests with behavior changes.
- Test native-only and combined deployment, guest isolation, zero chart requests
  on locale switch, interaction persistence, and removal restoring the other module.

