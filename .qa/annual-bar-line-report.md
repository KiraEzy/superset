# Annual awarded value and share chart

Verified 2026-10-06 on the LAN embedded dashboard. Saved chart 137 on dashboard
16 now displays awarded value as dark-blue bars on the left HKD axis and awarded
value share as an unfilled blue line on the right percentage axis.

## Change and boundary

Only saved presentation settings changed: primary series type is `bar`, both
area flags are false, and the old secondary-behind-primary setting is false in
the chart and dashboard occurrence. The secondary series remains `line`.
All other chart settings, metrics, formatting, titles, filter configuration and
dashboard color metadata were verified unchanged by authenticated API readback.
Datasources, analytical data and the original rollback dashboard 11 were not edited.
No renderer or Superset/MCP implementation changes or deployment rebuilds were
needed. The maintained browser assertion and operator documentation now reflect
the saved chart style.

## Verification

| Check | Result |
| --- | --- |
| Saved settings | PASS: native API readback matches the targeted changes; other chart settings and dashboard metadata remain intact. |
| Rendering | PASS: both Superset baseline and FocalBI fork show bar/line series, separate axes, retained colors and no line area fill. |
| Languages | PASS: English, Traditional Chinese and Simplified Chinese on both engines. |
| Timeline and totals | PASS: five annual observations; awarded value sums to HKD 72,002,518.80. KPIs remain 53 records and 19 department relationships. |
| Raw results | PASS: chart results remain identical across all renderer/language combinations. |
| Switching | PASS: zero new chart-data requests when switching engines or languages. |
| Tooltip | PASS: native shared hover tooltip shows both metrics; the inspected 2023 point displays `$22.6M` and `9.1%`. |
| Browser errors | PASS: no JavaScript errors in the final run. |
| Source integrity | PASS: 30 protected native files and 357 immutable baseline files retain their hashes. |
| Repository checks | PASS: changed browser test formatting and `git diff --check`; no tracked native Superset/MCP core changes. |

[Browser result](../local-modules/focalbi-rendering/test-results/annual-bar-line.json),
[Traditional Chinese screenshot](../local-modules/focalbi-rendering/test-results/annual-fork-zh-Hant.png),
[English baseline screenshot](../local-modules/focalbi-rendering/test-results/annual-baseline-en.png),
and [hover screenshot](../local-modules/focalbi-rendering/test-results/annual-tooltip.png).
Readback receipts, prior chart/dashboard settings and the temporary browser check
remain in the module's ignored `.runtime/` directory.

## Validation limits and documentation

Codex's configured FocalBI MCP failed initialization because its authentication
header helper exceeded the ten-second timeout, including a retry. The targeted
save therefore used the existing authenticated native Superset API; successful
MCP mutation is not claimed. Native computer-use's pipe remained unavailable
after retry/reset. Browser verification used automated local Chrome through
Playwright, and its task browser was closed afterward.

The [module README](../local-modules/focalbi-rendering/README.md) documents the
saved style and normal Explore editing. The
[operator guide](../docs/admin_docs/configuration/focalbi-mcp.mdx) distinguishes
chart 137 from the unchanged chart 119 rollback presentation. This configuration
change does not require a full module build or repository-wide test run.
