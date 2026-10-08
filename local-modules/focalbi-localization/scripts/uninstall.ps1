# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
param([switch]$PurgeData)
$ErrorActionPreference = 'Stop'
$moduleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $moduleRoot '../..')).Path
$statePath = Join-Path $moduleRoot '.runtime/activation.json'
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.owner -ne 'focalbi.localization') { throw 'Activation record is not module-owned' }
$renderingStatePath = Join-Path $repositoryRoot 'local-modules/focalbi-rendering/.runtime/activation.json'
$rendering = if (Test-Path -LiteralPath $renderingStatePath) { Get-Content -LiteralPath $renderingStatePath -Raw | ConvertFrom-Json } else { $null }
$restoreRendering = $rendering -and $rendering.active
$assetLine = if ($restoreRendering) { '      - ./local-modules/focalbi-rendering/dist/assets:/app/superset/static/assets:ro' } else { '' }
$restore = @"
services:
  superset:
    image: apachesuperset.docker.scarf.sh/apache/superset@sha256:5822dff49c41fd745ce33e38af502f9c64df30d133aeba148c5d89b35a1004ef
    command: ["/usr/bin/run-server.sh"]
    environment:
      SUPERSET_CONFIG_PATH: $($state.originalConfig)
      PYTHONPATH: /app:/app/superset-core/src:/app/docker/pythonpath_dev:/app/pythonpath
"@
if ($assetLine) { $restore += "`n    volumes:`n$assetLine`n" }
$restore | Set-Content -LiteralPath (Join-Path $moduleRoot '.runtime/restore.yml') -Encoding UTF8
$grantsPath = Join-Path $moduleRoot '.runtime/grants.json'
if (Test-Path -LiteralPath $grantsPath) {
    Get-Content -LiteralPath $grantsPath -Raw | docker exec -i superset_app python /app/focalbi-localization/scripts/remove-grants.py
    if ($LASTEXITCODE) { throw 'Module permission restoration failed' }
    '[]' | Set-Content -LiteralPath $grantsPath -Encoding UTF8
}
if ($PurgeData) {
    docker exec superset_app python /app/focalbi-localization/scripts/purge.py
    if ($LASTEXITCODE) { throw 'Ownership-checked purge failed' }
}
Push-Location $repositoryRoot
try {
    docker compose -f docker-compose-image-tag.yml -f local-modules/focalbi-localization/.runtime/restore.yml up -d --no-deps superset
    if ($LASTEXITCODE) { throw 'Native service restoration failed' }
} finally { Pop-Location }
$state.active = $false
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
Write-Output "Localization disabled. Rendering retained: $([bool]$restoreRendering). Translation data retained: $(-not $PurgeData). Website binding unchanged."
