# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$moduleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $moduleRoot '../..')).Path
$settings = Get-Content -LiteralPath (Join-Path $moduleRoot '.runtime/settings.json') -Raw | ConvertFrom-Json
if (-not $SkipBuild) {
    Push-Location $moduleRoot
    try {
        cmd /c 'node --max-old-space-size=12288 --experimental-strip-types scripts/build.ts > .runtime/native-build.log 2>&1'
        if ($LASTEXITCODE) { throw 'Native bundle build failed; see .runtime/native-build.log' }
    } finally { Pop-Location }
}
python (Join-Path $moduleRoot 'scripts/snapshot.py') --verify
if ($LASTEXITCODE) { throw 'Baseline integrity check failed' }
if (-not (Test-Path -LiteralPath (Join-Path $moduleRoot 'dist/assets/manifest.json'))) { throw 'Native frontend assets are missing' }
$localizationRoot = Join-Path $repositoryRoot 'local-modules/focalbi-localization'
$localizationStatePath = Join-Path $localizationRoot '.runtime/activation.json'
$localizationState = if (Test-Path -LiteralPath $localizationStatePath) { Get-Content -LiteralPath $localizationStatePath -Raw | ConvertFrom-Json } else { $null }
if ($localizationState -and $localizationState.active) {
    # The composing module owns the combined asset bundle; retain its backend.
    & (Join-Path $localizationRoot 'scripts/activate.ps1') -WithRendering
} else {
    Push-Location $repositoryRoot
    try {
        docker compose -f docker-compose-image-tag.yml -f local-modules/focalbi-rendering/deployment/native.yml -f local-modules/focalbi-rendering/deployment/compose.yml up -d --no-deps superset
        if ($LASTEXITCODE) { throw 'Renderer overlay activation failed' }
    } finally { Pop-Location }
}
. (Join-Path $PSScriptRoot 'website-service.ps1')
$pidValue = Start-NativeWebsiteService $settings $moduleRoot $settings.native_embed.dashboardUuid
@{ owner = 'focalbi.rendering'; pid = $pidValue; originalEmbed = $settings.original_embed; active = $true; nativeEmbed = $settings.native_embed } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $moduleRoot '.runtime/activation.json')
python (Join-Path $moduleRoot 'scripts/doc_links.py') record
if ($LASTEXITCODE) { throw 'Documentation ownership recording failed' }
Write-Output 'Native dashboard rendering overlay and operator-controlled website binding activated. MCP and workers were not restarted.'
