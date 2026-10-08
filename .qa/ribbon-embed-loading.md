# Embedded dashboard startup fix

Date: 2026-10-05. Website worktree:
`C:/Users/charleswong/Documents/GitHub/new-official-site-fds/.worktrees/another-new-hero`.

The website treated 45 seconds without an SDK readiness acknowledgement as a
confirmed failure and removed the iframe. Slow initial loading could therefore
never finish. A delayed-start regression reproduced the old `error` state.

`src/components/FocalBiDashboard.tsx` now uses a separate `slow` state. It retains
the pending iframe, displays translated waiting/retry text and accepts late
readiness. Explicit failed/denied requests still remove the iframe; manual Retry
still creates a fresh SDK context. Native Superset sources, saved dashboards,
permissions, token bindings and data configuration were not changed.

Verification:

- Delayed configuration beyond 45 seconds retains the same iframe and recovers:
  `e2e/focalbi-startup.spec.ts` passes.
- Existing unavailable/denied/retry regression passes.
- Website TypeScript check and production build pass; existing bundle-size warning
  remains.
- The exact URL `http://192.168.10.27:3010/?hero=ribbon#focal-bi` renders the FDS
  dashboard in automated Chrome. Screenshot review confirms the pie, bar, donut
  and annual series render. Baseline remains HKD 72,002,518.80, 53 records and
  19 department relationships.
- Full embed verification passes on that URL: three languages, both renderer
  choices, simultaneous independent embeds, search retention and guest isolation.
  All plots load with no retries or JavaScript errors; locale changes issue no
  chart-data requests. Evidence: localization `test-results/lan-embed.json` and
  `.runtime/ribbon-embed-fix.log`.

The user's original browser failure was not directly inspectable because no
computer-use browser was connected. The delayed-start defect was reproduced
independently; initial live data loading was slow but completed. Website README
documents the recovery behavior and its regression-test command.
