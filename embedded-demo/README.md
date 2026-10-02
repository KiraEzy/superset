<!-- Licensed under the Apache License, Version 2.0. -->

# FocalBI embedded dashboard demo

A separate website at http://localhost:3100 embeds a full interactive Superset
dashboard. Select **US team** or **France team** to inspect the same dashboard
with different server-enforced row-level security. No Superset login is needed.

This is a local integration example, not production authentication. It binds to
127.0.0.1 and refuses to run with NODE_ENV=production. The viewer selector grants
access to bundled sample data only. It must be replaced by your real website's
authentication and entitlement checks before deployment.

## Setup

Requirements: running FocalBI Docker containers, the bundled Sales Dashboard and
examples database, Windows PowerShell, and Node.js 24.

From this directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./setup.ps1
npm.cmd ci
npm.cmd run build
npm.cmd start
```

Open http://localhost:3100. Keep the server terminal running; Ctrl+C stops it.
Subsequent starts require only `npm.cmd start`, with Superset running.

The setup script creates a separate dashboard and chart copies, configures the
EmbeddedViewer role and allowed origin, generates local secrets, and restarts
the Superset app, workers and MCP service. It does not modify the original Sales
Dashboard or its charts. Re-running setup reuses the demo dashboard, charts and
secrets, and reapplies the demo role and allowed origin while preserving other
configured allowed origins.

## Validate

With the server running:

```powershell
npm.cmd run build
npm.cmd test
```

Tests make real requests to the demo server and Superset. They cover anonymous
denial, session rotation/logout, token lifetime/signature, allowed origins,
dashboard authorization, and actual US/France query isolation.

For browser checks, select US team, apply Product line = Classic Cars, switch
dashboard tabs, then select France team. Check that values change and the
Country filter offers only the selected viewer's country. Leave the page open
for over five minutes to verify renewal, then end the demo session.

Configuration, contracts, deployment changes and limitations are maintained in
[the embedding guide](../docs/admin_docs/configuration/focalbi-embedding.mdx).

## License

Licensed to the Apache Software Foundation (ASF) under one or more contributor
license agreements. See the repository NOTICE for ownership information.
Licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
Distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for governing permissions and limitations.
