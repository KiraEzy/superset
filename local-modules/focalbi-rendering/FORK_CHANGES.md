# Rendering maintenance

Baseline project revision: b991c57336e667c328b3be2b2db5bdb7fc45067a.
provenance.json records source paths, hashes and the native dependency lock hash.
Apache notices remain intact. Baseline renderer bytes are immutable; fork files
are an independent copy. The presentation-only migration retires duplicated
shared core/component code and reuses native shared packages unchanged.

Initial fork renderer sources match baseline. General shared presentation adapters
provide optional headings, selection colors, layering and interaction restoration.
Both engines receive the same data and presentation inputs. They do not aggregate
or change metric meanings. The old custom viewer, source fetch/count pipeline,
aggregation backend, business JSON and replacement token service are removed.
The shared bar adapter honors native sum-sort controls for one categorical series;
the snapshot transform only handles that enum for multiple series. It preserves
category/value pairs and eligible rank membership in both engines.

For an extension or upgrade:

1. Review native revision, licenses, ChartProps, hooks and dependency compatibility.
2. Add typed transform/component registrations and reusable capability declarations.
   Never replace native buildQuery, filters, source definitions or access checks.
3. Exercise unrelated datasets and existing dashboards, native chart addition/removal,
   optional metadata Save/Discard/undo, native requests/results and renderer parity.
4. Verify switching preserves interactions without queries; record intentional fork
   changes here and update architecture/operator documentation in the same change.

Native image/dependency upgrades require a deliberate rebuild and compatibility
review. Renderer activation changes web assets only; MCP and background services
continue to use ordinary native provider configuration.
