param([switch]$NoBrowser, [switch]$RebuildIndexes)
. (Join-Path $PSScriptRoot 'app_common.ps1')
$startedHere = $false
$state = $null
Push-Location $script:AppRoot
try {
    New-Item -ItemType Directory -Force -Path $script:RuntimeDirectory | Out-Null
    $state = Read-AppState
    $api = if ($null -ne $state) { Get-OwnedProcess $state $state.Api } else { $null }
    if ($RebuildIndexes -and $null -ne $api) { throw 'Run Stop-App.cmd before rebuilding indexes.' }
    if ($null -eq $api) {
        # Recover only recorded, validated children from a previous API crash.
        if ($null -ne $state) { Stop-OwnedApp $state }
        Assert-PortsFree @(8000, 50051, 50052, 50053)
        Initialize-AppPython
        Initialize-AppIndexes -Rebuild:$RebuildIndexes
        $arguments = '-m coordinator.api_server --config "{0}" --data-directory "{1}" --host 127.0.0.1 --port 8000' -f $script:CoordinatorConfig, $script:DataDirectory
        $api = Start-Process -FilePath $script:Python -ArgumentList $arguments -WorkingDirectory $script:AppRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $script:RuntimeDirectory 'api.stdout.log') -RedirectStandardError (Join-Path $script:RuntimeDirectory 'api.stderr.log')
        $basePython = & $script:Python -c 'import sys; print(sys._base_executable)'
        $state = [pscustomobject]@{ ProjectRoot = $script:AppRoot; Python = $script:Python; BasePython = [string]$basePython; DataDirectory = $script:DataDirectory; Api = (Get-ProcessRecord $api.Id); ApiChildren = @(); Nodes = @() }
        Write-AppJson $script:StateFile $state
        $startedHere = $true
    }
    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($null -eq (Get-OwnedProcess $state $state.Api)) { throw 'The API process exited or failed its ownership check. See api.stderr.log.' }
        Save-AppNodeRecords $state
        try { $health = Invoke-AppApi '/api/health'; if ($health.status -eq 'ok') { $ready = $true; break } } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'The HTTP API did not become ready within 60 seconds.' }
    # Invoke-RestMethod emits a JSON array as one pipeline object in Windows PowerShell 5.
    $nodes = Invoke-AppApi '/api/nodes'
    if ($nodes.Count -ne 3) { throw 'The local launcher requires the three default search nodes.' }
    foreach ($node in $nodes) {
        if ($node.state -ne 'running') {
            $number = [int]$node.node_id.Split('_')[-1]
            Assert-PortsFree @(50050 + $number)
            Invoke-AppApi "/api/nodes/$($node.node_id)/start" 'Post' | Out-Null
            Save-AppNodeRecords $state
        }
    }
    $deadline = (Get-Date).AddSeconds(120)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        Save-AppNodeRecords $state
        try {
            $search = Invoke-AppApi '/api/search' 'Post' @{ query = 'python'; top_k = 1 }
            if ($search.healthy_nodes -eq 3 -and $search.eligible_nodes -eq 3 -and $search.verified_nodes -eq 3) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'All three nodes did not become healthy and verified within 120 seconds. Inspect API logs and try Stop-App.cmd, then Start-App.cmd -RebuildIndexes.' }
    Write-Host "Distributed Search is running at $script:BaseUrl (3 verified nodes)."
    Write-Host "Runtime, Python environment and logs: $script:RuntimeDirectory"
    Write-Host 'Run Stop-App.cmd to stop it. Run Start-App.cmd again after a reboot.'
    if (-not $NoBrowser) { Start-Process $script:BaseUrl | Out-Null }
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace
    Write-Host "Logs: $script:RuntimeDirectory"
    if ($startedHere -and $null -ne $state) {
        try { Save-AppNodeRecords $state; Stop-OwnedApp $state } catch { Write-Warning "$($_.Exception.Message)`n$($_.ScriptStackTrace)" }
    }
    exit 1
} finally { Pop-Location }
