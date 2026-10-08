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
param([switch]$WithRendering, [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$moduleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $moduleRoot '../..')).Path
$runtimePath = Join-Path $moduleRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$mode = if ($WithRendering) { 'combined' } else { 'native' }
$integrityArguments = @((Join-Path $PSScriptRoot 'integrity.py'))
if ($WithRendering) { $integrityArguments += '--with-rendering' }
& python @integrityArguments
if ($LASTEXITCODE) { throw 'Localization compatibility checks failed; activation stopped' }
if (-not $SkipBuild) {
    Push-Location $moduleRoot
    try {
        $buildArguments = @('--max-old-space-size=12288', '--experimental-strip-types', 'scripts/build.ts')
        if ($WithRendering) { $buildArguments += '--with-rendering' }
        $ErrorActionPreference = 'Continue'
        & node.exe @buildArguments *> (Join-Path $runtimePath ('build-' + $mode + '.log'))
        $buildExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($buildExit) { throw "Localization $mode build failed; inspect .runtime/build-$mode.log" }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $moduleRoot "dist/$mode/assets/manifest.json"))) { throw 'Localization assets are missing' }
$statePath = Join-Path $runtimePath 'activation.json'
$state = if (Test-Path -LiteralPath $statePath) { Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } else { $null }
if ($state -and $state.owner -ne 'focalbi.localization') { throw 'Activation record is not module-owned' }
if (-not $state) {
    $inspection = docker inspect superset_app | ConvertFrom-Json
    $originalConfig = @($inspection[0].Config.Env | Where-Object { $_ -like 'SUPERSET_CONFIG_PATH=*' } | ForEach-Object { $_.Substring('SUPERSET_CONFIG_PATH='.Length) }) | Select-Object -First 1
    if (-not $originalConfig) { $originalConfig = '/app/docker/pythonpath_dev/superset_config.py' }
    $priorAssets = @($inspection[0].Mounts | Where-Object { $_.Destination -eq '/app/superset/static/assets' } | Select-Object -First 1).Source
    $state = @{ owner = 'focalbi.localization'; active = $false; originalConfig = $originalConfig; priorAssets = $priorAssets; priorRendering = [bool]$priorAssets; mode = $mode }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
}
$environmentPath = Join-Path $runtimePath 'localization.env'
if (-not (Test-Path -LiteralPath $environmentPath)) {
    $passwordBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generator.GetBytes($passwordBytes)
    $generator.Dispose()
    $password = [Convert]::ToBase64String($passwordBytes).Replace('+','-').Replace('/','_').TrimEnd('=')
    @("FOCALBI_LOCALIZATION_DATABASE_URI=postgresql+psycopg2://focalbi_localization:${password}@db:5432/focalbi_localization", ('FOCALBI_LOCALIZATION_ORIGINAL_CONFIG=' + $state.originalConfig)) | Set-Content -LiteralPath $environmentPath -Encoding UTF8
}
# Deploy the exact .supx contents through the installed LOCAL_EXTENSIONS loader.
$extensionRoot = Join-Path $runtimePath 'extension'
New-Item -ItemType Directory -Force -Path $extensionRoot | Out-Null
$extensionDist = Join-Path $extensionRoot 'dist'
New-Item -ItemType Directory -Force -Path $extensionDist | Out-Null
$extensionAbsolute = (Resolve-Path -LiteralPath $extensionDist).Path
$packageDist = (Resolve-Path -LiteralPath (Join-Path $moduleRoot 'dist/extension')).Path
# This ignored, module-owned deployment tree must match the packaged extension.
foreach ($deployed in Get-ChildItem -LiteralPath $extensionAbsolute -File -Recurse) {
    if (-not $deployed.FullName.StartsWith($extensionAbsolute + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Extension cleanup path escaped the module' }
    $relative = $deployed.FullName.Substring($extensionAbsolute.Length + 1)
    if (-not (Test-Path -LiteralPath (Join-Path $packageDist $relative))) { Remove-Item -LiteralPath $deployed.FullName -Force }
}
Get-ChildItem -LiteralPath (Join-Path $moduleRoot 'dist/extension') | Copy-Item -Destination $extensionDist -Recurse -Force
@"
services:
  superset:
    volumes:
      - ./local-modules/focalbi-localization/dist/$mode/assets:/app/superset/static/assets:ro
"@ | Set-Content -LiteralPath (Join-Path $runtimePath 'assets.yml') -Encoding UTF8
Push-Location $repositoryRoot
try {
    docker compose -f docker-compose-image-tag.yml -f local-modules/focalbi-localization/deployment/compose.yml -f local-modules/focalbi-localization/.runtime/assets.yml up -d --no-deps --force-recreate superset
    if ($LASTEXITCODE) { throw 'Localization service activation failed' }
    $ErrorActionPreference = 'Continue'
    docker exec superset_app python /app/focalbi-localization/scripts/setup.py *> (Join-Path $runtimePath 'setup.log')
    $setupExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($setupExit) { throw 'Localization persistence/permission setup failed; inspect .runtime/setup.log' }
    $receipt = Get-Content -LiteralPath (Join-Path $runtimePath 'setup.log') | Where-Object { $_.StartsWith('FOCALBI_LOCALIZATION_SETUP=') } | Select-Object -Last 1
    if (-not $receipt) { throw 'Missing module permission ownership receipt' }
    $provisioned = $receipt.Substring('FOCALBI_LOCALIZATION_SETUP='.Length) | ConvertFrom-Json
    $grantsPath = Join-Path $runtimePath 'grants.json'
    $priorGrants = if (Test-Path -LiteralPath $grantsPath) { @(Get-Content -LiteralPath $grantsPath -Raw | ConvertFrom-Json) } else { @() }
    @($priorGrants + @($provisioned.grants) | Sort-Object -Property role,permission,view -Unique) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $grantsPath -Encoding UTF8
    $ErrorActionPreference = 'Continue'
    docker exec superset_app python /app/focalbi-localization/scripts/health.py *> (Join-Path $runtimePath 'health.log')
    $healthExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($healthExit) { throw 'Localization database/extension health failed; inspect .runtime/health.log' }
} finally { Pop-Location }
$state.active = $true
$state.mode = $mode
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
Write-Output "Localization active ($mode). Native dashboard binding and token service retained."
