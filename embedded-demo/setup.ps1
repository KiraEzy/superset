# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
$ErrorActionPreference = 'Stop'
$demoRoot = $PSScriptRoot
$repoRoot = Split-Path $demoRoot -Parent
$secretPath = Join-Path $repoRoot 'docker/.focal-embed-secret.local'
$envPath = Join-Path $demoRoot '.env.local'
$utf8 = New-Object System.Text.UTF8Encoding($false)
function New-DemoSecret {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
if (-not (Test-Path -LiteralPath $secretPath)) {
    [System.IO.File]::WriteAllText($secretPath, (New-DemoSecret), $utf8)
}
$embedSecret = [System.IO.File]::ReadAllText($secretPath).Trim()
if ($embedSecret.Length -lt 32) { throw 'Embedding signing secret is too short.' }
docker cp (Join-Path $demoRoot 'bootstrap.py') superset_app:/tmp/bootstrap_embedding.py
if ($LASTEXITCODE -ne 0) { throw 'Cannot copy provisioning script. Start Superset first.' }
docker exec superset_app /app/.venv/bin/python /tmp/bootstrap_embedding.py
if ($LASTEXITCODE -ne 0) { throw 'Demo provisioning failed.' }
$configJson = docker exec superset_app cat /app/superset_home/focal-embed-demo.json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read provisioned dashboard identifiers.' }
$config = $configJson | ConvertFrom-Json
$sessionSecret = New-DemoSecret
if (Test-Path -LiteralPath $envPath) {
    $existing = Get-Content -LiteralPath $envPath | Where-Object { $_ -match '^FOCAL_SESSION_SECRET=' } | Select-Object -First 1
    if ($existing) { $sessionSecret = $existing.Substring('FOCAL_SESSION_SECRET='.Length) }
}
$lines = @(
    "FOCAL_EMBED_SECRET=$embedSecret",
    "FOCAL_SESSION_SECRET=$sessionSecret",
    "FOCAL_DASHBOARD_UUID=$($config.dashboardUuid)",
    "FOCAL_DASHBOARD_ID=$($config.dashboardId)",
    "FOCAL_DATASET_ID=$($config.datasetId)",
    "FOCAL_COUNTRY_FILTER_ID=$($config.countryFilterId)",
    'PORT=3100'
)
[System.IO.File]::WriteAllText($envPath, ($lines -join [Environment]::NewLine) + [Environment]::NewLine, $utf8)
docker restart superset_app superset_worker superset_worker_beat superset_mcp
if ($LASTEXITCODE -ne 0) { throw 'Could not restart Superset services.' }
Write-Output "Provisioned demo dashboard $($config.dashboardId). Run npm ci, npm run build, then npm start in $demoRoot."
