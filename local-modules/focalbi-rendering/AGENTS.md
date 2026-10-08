# FocalBI rendering fork

This is the company-wide rendering layer, not a dashboard-specific application.

- Never activate behavior by company name, dataset ID, chart ID, or dashboard ID.
  Identifiers select configured resources only. Domain values belong in configs.
- Add reusable, typed capabilities to registries and schemas. Exercise changes
  against an unrelated dataset and both rendering engines.
- Keep `vendor/baseline` immutable; `scripts/snapshot.py --verify` checks hashes.
  Fork renderer changes belong in `vendor/fork`, reusable viewer changes in
  `frontend`. Native Superset owns queries, filtering, aggregation and permissions.
  Do not recreate Steps 1–4 or add an independent dashboard definition service.
- Do not edit Superset/MCP core. Activation belongs in the module's deployment
  overlay. Preserve native guest authorization and query/result semantics.
- Preserve applied filters and table/legend/sort state across renderer switches.
- Retain copied Apache notices. New source files use Apache-2.0 headers.
- README owns commands; ARCHITECTURE owns contracts. Update both when affected.
- Run Python unit tests, module frontend type checking/build, baseline integrity,
  browser tests, and computer-use checks before declaring completion.
