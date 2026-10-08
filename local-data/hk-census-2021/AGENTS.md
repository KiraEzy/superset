# Census data workflow

This directory owns data preparation, source provenance and native Superset
resource specifications. It does not own application or renderer features.

- Use the configured FocalBI MCP for datasets, charts and dashboard controls.
- File ingestion uses the existing authenticated Superset upload endpoint.
- Native dashboard editing owns layout, cascade configuration and publication.
- Never modify Superset/MCP core or the FocalBI rendering module for census data.
- Keep districts, reference totals and statistical populations distinct.
- Do not average medians, manufacture joint distributions or infer microdata.
- Preserve source symbols, bilingual metadata and official definitions.
- Record created resource IDs and remove only verified workflow-owned resources.
