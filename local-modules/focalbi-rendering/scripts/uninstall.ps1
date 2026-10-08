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
param([switch]$KeepResources, [switch]$DeleteFolder, [string]$Username = 'admin', [int]$PostId)
$ErrorActionPreference = 'Stop'
$moduleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $moduleRoot '../..')).Path
if ((Split-Path $moduleRoot -Leaf) -ne 'focalbi-rendering' -or (Split-Path (Split-Path $moduleRoot -Parent) -Leaf) -ne 'local-modules') { throw 'Invalid module removal path' }
if ($DeleteFolder -and $KeepResources) { throw 'Folder deletion requires resource cleanup' }
$settings = Get-Content -LiteralPath (Join-Path $moduleRoot '.runtime/settings.json') -Raw | ConvertFrom-Json
function Invoke-RecordedCleanup([string[]]$Arguments, [string]$Log) {
    $ErrorActionPreference = 'Continue'
    $output = & docker @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { $_.ToString() } | Set-Content -LiteralPath $Log -Encoding UTF8
    if ($exitCode) { throw 'Native ownership/cleanup checks failed; see .runtime/cleanup.log' }
}
if (-not $KeepResources) {
    # Copy administrative cleanup inputs; no runtime module mount is needed.
    docker exec superset_app mkdir -p /tmp/focalbi-rendering-cleanup
    if ($LASTEXITCODE) { throw 'Cannot prepare cleanup workspace' }
    docker cp (Join-Path $moduleRoot 'scripts/cleanup-owned.py') superset_app:/tmp/focalbi-rendering-cleanup/cleanup.py
    if ($LASTEXITCODE) { throw 'Cannot copy cleanup tool' }
    docker cp (Join-Path $moduleRoot '.runtime/resources.json') superset_app:/tmp/focalbi-rendering-cleanup/resources.json
    if ($LASTEXITCODE) { throw 'Cannot copy ownership ledger' }
    $postArguments = @()
    if ($PostId) { $postArguments = @('--post-id', $PostId) }
    $cleanupArguments = @('exec', '-u', 'root', 'superset_app', '/app/.venv/bin/python', '/tmp/focalbi-rendering-cleanup/cleanup.py', '--ledger', '/tmp/focalbi-rendering-cleanup/resources.json', '--username', $Username) + $postArguments
    Invoke-RecordedCleanup ($cleanupArguments + @('--dry-run')) (Join-Path $moduleRoot '.runtime/cleanup.log')
    Invoke-RecordedCleanup $cleanupArguments (Join-Path $moduleRoot '.runtime/cleanup.log')
    $receipt = Get-Content -LiteralPath (Join-Path $moduleRoot '.runtime/cleanup.log') | Where-Object { $_.StartsWith('FOCALBI_CLEANUP_LEDGER=') } | Select-Object -Last 1
    if (-not $receipt) { throw 'Missing cleanup receipt' }
    $receipt.Substring('FOCALBI_CLEANUP_LEDGER='.Length) | Set-Content -LiteralPath (Join-Path $moduleRoot '.runtime/resources.json') -Encoding UTF8
}
# Keep ordinary operator configuration, including native SQL-template settings.
$localizationRoot = Join-Path $repositoryRoot 'local-modules/focalbi-localization'
$localizationStatePath = Join-Path $localizationRoot '.runtime/activation.json'
$localizationState = if (Test-Path -LiteralPath $localizationStatePath) { Get-Content -LiteralPath $localizationStatePath -Raw | ConvertFrom-Json } else { $null }
if ($localizationState -and $localizationState.active) {
    # Compile without renderer imports so its folder can be removed independently.
    & (Join-Path $localizationRoot 'scripts/activate.ps1')
} else {
    Push-Location $repositoryRoot
    try {
        docker compose -f docker-compose-image-tag.yml -f local-modules/focalbi-rendering/deployment/native.yml up -d --no-deps superset
        if ($LASTEXITCODE) { throw 'Native frontend restoration failed' }
    } finally { Pop-Location }
}
. (Join-Path $PSScriptRoot 'website-service.ps1')
$pidValue = Start-NativeWebsiteService $settings $moduleRoot $settings.original_embed.dashboardUuid
@{ owner = 'focalbi.rendering'; pid = $pidValue; active = $false; originalEmbed = $settings.original_embed } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $moduleRoot '.runtime/activation.json')
Write-Output 'Native assets and original website embed target restored. No renderer module is mounted. MCP and workers were not restarted.'
if ($DeleteFolder) {
    python (Join-Path $moduleRoot 'scripts/doc_links.py') remove
    if ($LASTEXITCODE) { throw 'Documentation ownership changed; folder deletion stopped' }
    $resolvedTarget = (Resolve-Path -LiteralPath $moduleRoot).Path
    $allowedTarget = (Join-Path $repositoryRoot 'local-modules/focalbi-rendering').Replace('/', '\')
    if ($resolvedTarget -ne $allowedTarget) { throw 'Resolved delete target failed containment check' }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}
