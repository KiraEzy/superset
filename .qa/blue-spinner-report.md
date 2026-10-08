# Blue loading spinner verification

Date: 2026-10-06. Status: **PASS**.

The operator configuration loads `docker/pythonpath_dev/focalbi_blue_spinner.svg`
through Superset's native `brandSpinnerSvg` token for light and dark themes.
The animation is a blue circular arc with a pale track and a reduced-motion
fallback. It applies independently of rendering/localization activation.
No native implementation, saved analytical resource, website binding, token
permission or immutable baseline renderer was changed.

Verification:

- Native startup spinner visually reviewed; rotation and reduced-motion behavior
  verified in automated Chrome.
- Embedded LAN page `http://192.168.10.27:3010/#focal-bi`: both FocalBI fork and
  Superset baseline use the configured SVG during chart loading. Distinct raster
  frames confirm animation; a separate browser-level reduced-motion check confirms
  the static fallback. Browser-level preference flags are used because document
  media emulation does not control the SVG image preference in this environment.
- Renderer switching sends no additional chart-data requests; guest loading returns
  HKD 72,002,518.80, 53 award records and 19 department relationships. No JavaScript
  errors were reported. The loaded dashboard screenshot was visually reviewed.
- Live bootstrap includes the spinner for both themes. Every other theme token
  matches the previous configuration. Native system-theme flags remain unchanged.
- Existing operator settings are preserved by AST comparison. Python syntax and
  ASCII SVG checks pass; all eight operator-document local links exist.
- Protected native hashes pass (30 files); immutable snapshots pass (357 files).
  Native implementation directories have no Git diff. `git diff --check` passes.

The service reload exposed a Docker web-container failure, "tried to kill
container, but did not receive an exit event", and a worker health-check failure
with a missing Docker filesystem path. The affected containers were recreated
using their existing pinned image and overlays. The web service now also has
`init: true`; the same setting was already enabled for workers. Web, worker and
MCP health checks pass, and the scheduler remains running.

Evidence: localization `test-results/blue-spinner.json`,
`blue-spinner-native-startup.png`, `blue-spinner-fork-chart.png`,
`blue-spinner-baseline-chart.png`, `blue-spinner-reduced-motion.png` and
`blue-spinner-embedded-loaded.png`. The focused probe and redacted before/after
theme receipts are in the module's ignored `.runtime/` directory.

Setup, precedence and rollback are documented in the
[operator guide](../docs/admin_docs/configuration/focalbi-mcp.mdx#loading-indicator).
