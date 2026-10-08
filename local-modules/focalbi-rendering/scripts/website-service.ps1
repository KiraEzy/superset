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
function Start-NativeWebsiteService($Settings, [string]$ModuleRoot, [string]$DashboardUuid) {
    if ($DashboardUuid -notmatch '^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$') { throw 'Invalid embedding UUID' }
    $environmentFile = Join-Path $Settings.website_root '.env.focalbi.local'
    $lines = @(Get-Content -LiteralPath $environmentFile -Encoding UTF8)
    $binding = @($lines | Where-Object { $_ -match '^FOCALBI_DASHBOARD_UUID=' })
    if ($binding.Count -gt 1 -or ($binding.Count -eq 1 -and $binding[0].Substring('FOCALBI_DASHBOARD_UUID='.Length) -notin @($Settings.original_embed.dashboardUuid, $Settings.native_embed.dashboardUuid))) { throw 'Website resource binding changed outside the module' }
    $listener = Get-NetTCPConnection -LocalPort 3011 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        $command = $process.CommandLine.Replace('/', '\').ToLowerInvariant()
        $knownWebsite = $command.Contains($Settings.website_root.Replace('/', '\').ToLowerInvariant()) -and $command.Contains('focalbi-demo')
        $knownLegacy = $command.Contains($ModuleRoot.ToLowerInvariant()) -and $command.Contains('token-service')
        if (-not ($knownWebsite -or $knownLegacy)) { throw 'Token port belongs to an unrelated process' }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
    }
    $lines = @($lines | Where-Object { $_ -notmatch '^FOCALBI_DASHBOARD_UUID=' }) + @('FOCALBI_DASHBOARD_UUID=' + $DashboardUuid)
    $lines | Set-Content -LiteralPath $environmentFile -Encoding UTF8
    if ($listener) {
        Stop-Process -Id $process.ProcessId
        if ($parent -and $parent.CommandLine.Contains('focalbi-demo')) { Stop-Process -Id $parent.ProcessId -ErrorAction SilentlyContinue }
    }
    $previousBinding = $env:FOCALBI_DASHBOARD_UUID
    try {
        $env:FOCALBI_DASHBOARD_UUID = $DashboardUuid
        $started = Start-Process -FilePath node.exe -ArgumentList @(('"' + (Join-Path $Settings.website_root 'node_modules/tsx/dist/cli.mjs') + '"'), 'server/focalbi-demo.ts') -WorkingDirectory $Settings.website_root -WindowStyle Hidden -PassThru
        return $started.Id
    } finally { $env:FOCALBI_DASHBOARD_UUID = $previousBinding }
}
