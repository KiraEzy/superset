# FocalBI content localization verification

Verified 2026-10-05 against the running Superset 6.1.0 development deployment.
Scope: the optional localization extension, native presentation adapters, composition
with the rendering module, and the website locale bridge. Existing unrelated
repository and website changes were retained.

## Running configuration

- Website: <http://192.168.10.27:3010/#focal-bi>.
- Superset: <http://192.168.10.27:8088>; MCP container healthy on port 5008.
- Localization and rendering are both active. The website retains company dashboard
  16, embedding UUID `52b05f1b-58a9-4e69-a879-a3e27af47cab`.
- Translation storage uses its own PostgreSQL database and role. Eleven authored
  catalogs remain after the seven recorded synthetic test resources were removed.
- Census resources were not modified. Services remain running.

## Results

| Verification | Result and evidence |
| --- | --- |
| Catalog backend | Six unit tests pass: revisions/atomic rollback, stale originals, dictionaries, validation and fallback. Python Ruff passes. |
| Presentation contracts | Twelve frontend tests pass, including locale precedence, raw identities, tooltip escaping, native formatter preservation, bridge validation and table/legend/zoom retention. |
| Native authoring | Dataset and Explore dialogs, independent save/discard, five unrelated visualization types, descriptions, active tabs and catalog-failure fallback pass. [Authoring result](../local-modules/focalbi-localization/test-results/authoring.json). |
| Live catalog APIs | Revision conflict, invalid fields, export, atomic import, changed-original fallback and duplicate translated labels with distinct raw identities pass. [API result](../local-modules/focalbi-localization/test-results/live-api.json). |
| LAN website | All four plotted charts and the source table load. English, Traditional Chinese and Simplified Chinese switching, two simultaneous embeds, iframe retention, table search and renderer switching pass. Zero locale-triggered chart-data requests, zero initial retries and no JavaScript errors. [Embed result](../local-modules/focalbi-localization/test-results/lan-embed.json). |
| Interaction preservation | Both renderers preserve raw query data, series, legend selections, annual zoom, date sorting and pagination across languages. Zero locale-triggered chart-data requests and no JavaScript errors. [Result](../local-modules/focalbi-localization/test-results/preservation.json). |
| Metrics | FDS remains HKD 72,002,518.80, 53 records and 19 department relationships. FDS plus OPM remains HKD 183,079,390.79, 150 records and 52 relationships. |
| Guest isolation | Authorized dashboard presentation bundle succeeds. Catalog authoring/export, writes and an unauthorized dashboard are rejected. Wrong-source bridge messages are ignored. |
| Token renewal | Native Embedded SDK obtained two guest-token responses and retained the rendered dashboard without JavaScript errors. [Result](../local-modules/focalbi-rendering/test-results/native-renewal.json). |
| Deployment/removal | Neither module, rendering alone, localization alone and both pass browser mode checks. Removing either module retains the other; translation data survives removal. Final state restored to both. |
| Builds | Native-only and combined localization bundles, standalone rendering bundle, extension package and website production build pass. Website lint passes. |
| Types | Module-owned TypeScript check passes; 4,054 existing upstream diagnostics are recorded separately. This is not a full-repository TypeScript pass. |
| Integrity | All 25 protected native source hashes and 357 immutable baseline files pass verification. No tracked Superset/MCP core files changed. |
| Documentation | All 24 local links in the module/operator documentation and this report resolve. Behavior and limits were reviewed alongside the implementation. |

Mode evidence: [both](../local-modules/focalbi-localization/test-results/mode-both.json),
[localization](../local-modules/focalbi-localization/test-results/mode-localization.json),
[rendering](../local-modules/focalbi-localization/test-results/mode-rendering.json),
[neither](../local-modules/focalbi-localization/test-results/mode-neither.json).
Screenshots reviewed: [Traditional Chinese embed](../local-modules/focalbi-localization/test-results/lan-embed-hant.png)
and [English embed](../local-modules/focalbi-localization/test-results/lan-embed-en.png).

## Limits

- Native computer-use had no connected browser surface (`apps: []`, `browsers: []`).
  Browser checks used automated local Chrome through Playwright; native computer-use
  acceptance remains unavailable, not claimed passed.
- The configured FocalBI MCP was not callable in this session. These changes and
  verification used the native authenticated Superset and extension APIs; container
  health does not establish a working Codex MCP connection.
- Earlier native initial chart-data timeouts were observed while iterating. The final
  embed and preservation runs required no retries. No native timeout/query behavior
  was changed.
- Bundles are developer builds with minification disabled. Upstream build size/CSS
  warnings remain. Production asset optimization is documented separately.
- The FDS catalog intentionally translates representative categories, not every
  free-text source record. Missing translations retain original text. Application UI
  strings and native CSV output remain governed by Superset, not content locale.

## Documentation and reproduction

The [module README](../local-modules/focalbi-localization/README.md) owns setup,
build, test, authoring, client integration and uninstall commands. The
[architecture](../local-modules/focalbi-localization/ARCHITECTURE.md) documents field
contracts, authorization, raw-value identity and independent module composition.
The [operator guide](../docs/admin_docs/configuration/focalbi-localization.mdx) is
linked from existing operator documentation and the repository README. Test logs,
credentials and generated artifacts remain in ignored module runtime directories;
credentials are not included in this report.
