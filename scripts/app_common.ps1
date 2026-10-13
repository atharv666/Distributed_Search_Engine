# Shared helpers for the local Windows launcher. No machine-wide settings are changed.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:AppRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$hasher = [Security.Cryptography.SHA256]::Create()
try { $digest = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($script:AppRoot.ToLowerInvariant())) }
finally { $hasher.Dispose() }
$key = ([BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()).Substring(0, 8)
# USERPROFILE avoids packaged desktop-app virtualization of LOCALAPPDATA.
$script:RuntimeDirectory = Join-Path $env:USERPROFILE "DistributedSearchEngine\$key"
$script:DataDirectory = Join-Path $script:RuntimeDirectory 'data'
$script:Python = Join-Path $script:RuntimeDirectory '.venv\Scripts\python.exe'
$script:ConfigDirectory = Join-Path $script:RuntimeDirectory 'config'
$script:CoordinatorConfig = Join-Path $script:ConfigDirectory 'coordinator_config.json'
$script:StateFile = Join-Path $script:RuntimeDirectory 'app.json'
$script:BaseUrl = 'http://127.0.0.1:8000'

function Write-AppJson($Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}

function Read-AppState {
    if (Test-Path -LiteralPath $script:StateFile) {
        return Get-Content -LiteralPath $script:StateFile -Raw | ConvertFrom-Json
    }
    return $null
}

function Get-SafeProcessStartUtc($Process) {
    if ($null -eq $Process) { return $null }
    try {
        $Process.Refresh()
        if ($Process.HasExited) { return $null }
        $started = $Process.StartTime
        if ($null -eq $started) { return $null }
        return $started.ToUniversalTime().ToString('o')
    } catch [System.InvalidOperationException] { return $null }
    catch [System.ComponentModel.Win32Exception] { return $null }
}

function Get-ProcessRecord($ProcessId, $NodeId = '', $Details = $null) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $startedUtc = Get-SafeProcessStartUtc $process
    if ($null -eq $startedUtc) { return $null }
    if ($null -eq $Details) { $Details = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" }
    if ($null -eq $Details) { return $null }
    return [pscustomobject]@{
        ProcessId = $process.Id
        StartedUtc = $startedUtc
        NodeId = $NodeId
        ExecutablePath = $Details.ExecutablePath
    }
}

function Get-OwnedProcess($State, $Record) {
    if ($null -eq $State -or $null -eq $Record -or $State.ProjectRoot -ne $script:AppRoot -or $State.Python -ne $script:Python) { return $null }
    $process = Get-Process -Id $Record.ProcessId -ErrorAction SilentlyContinue
    $startedUtc = Get-SafeProcessStartUtc $process
    if ($null -eq $startedUtc -or $startedUtc -ne $Record.StartedUtc) { return $null }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($Record.ProcessId)"
    if ($null -eq $details -or [string]::IsNullOrEmpty($details.CommandLine)) { return $null }
    # Windows venvs have both a redirector and a base-Python child process.
    if ($details.ExecutablePath -ne $script:Python -and $details.ExecutablePath -ne $State.BasePython) { return $null }
    if ($Record.NodeId -eq '') {
        if (-not $details.CommandLine.Contains('-m coordinator.api_server') -or -not $details.CommandLine.Contains($script:CoordinatorConfig) -or -not $details.CommandLine.Contains($script:DataDirectory)) { return $null }
    } else {
        if ($Record.NodeId -notmatch '^node_[123]$') { return $null }
        $indexPath = Join-Path $script:DataDirectory "indexes\nodes\$($Record.NodeId)_index.json"
        $number = $Record.NodeId.Split('_')[-1]
        $shardPath = Join-Path $script:DataDirectory "shards\shard_$number.jsonl"
        if (-not $details.CommandLine.Contains('-m search_node.server') -or -not $details.CommandLine.Contains("--node-id $($Record.NodeId)") -or -not $details.CommandLine.Contains($indexPath) -or -not $details.CommandLine.Contains($shardPath)) { return $null }
    }
    return $process
}

function Invoke-AppApi($Path, $Method = 'Get', $Body = $null) {
    $parameters = @{ Uri = "$script:BaseUrl$Path"; Method = $Method; TimeoutSec = 10 }
    if ($null -ne $Body) { $parameters.ContentType = 'application/json'; $parameters.Body = ($Body | ConvertTo-Json -Compress) }
    return Invoke-RestMethod @parameters
}

function Assert-PortsFree($Ports) {
    $occupied = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in $Ports })
    if ($occupied.Count -gt 0) {
        $description = ($occupied | ForEach-Object { "port $($_.LocalPort) (PID $($_.OwningProcess))" } | Select-Object -Unique) -join ', '
        throw "Another process is listening on $description. Close that application yourself, or run Stop-App.cmd if this is a previously tracked app. No unrelated process will be stopped."
    }
}

function Invoke-AppPython($Executable, $Arguments) {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments 2>&1 | Tee-Object -FilePath (Join-Path $script:RuntimeDirectory 'setup.log') -Append | Out-Host
        $result = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    if ($result -ne 0) { throw "Python command failed (exit $result). See $script:RuntimeDirectory\setup.log." }
}

function Initialize-AppPython {
    if (-not (Test-Path -LiteralPath $script:Python)) {
        $launcher = Get-Command python.exe -ErrorAction SilentlyContinue
        $prefix = @()
        if ($null -eq $launcher) {
            $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
            $prefix = @('-3')
        }
        if ($null -eq $launcher) { throw 'Install Python 3.10 or newer and add it to PATH, then run Start-App.cmd again.' }
        Write-Host "Creating reusable Python environment in $script:RuntimeDirectory\.venv ..."
        Invoke-AppPython $launcher.Source ($prefix + @('-c', "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or newer is required'"))
        Invoke-AppPython $launcher.Source ($prefix + @('-m', 'venv', '--system-site-packages', (Join-Path $script:RuntimeDirectory '.venv')))
        Invoke-AppPython $script:Python @('-m', 'pip', 'install', '-r', (Join-Path $script:AppRoot 'requirements.txt'))
    }
    # Reuse matching installed packages; repair only if dependencies are missing or differ.
    $check = "import sys; from pathlib import Path; from importlib.metadata import version; assert sys.version_info >= (3,10); lines=Path(sys.argv[1]).read_text().splitlines(); assert all(version(n)==v for n,v in (s.strip().split('==',1) for s in lines if s.strip() and not s.lstrip().startswith('#')))"
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $script:Python -c $check (Join-Path $script:AppRoot 'requirements.txt') *> (Join-Path $script:RuntimeDirectory 'dependency-check.log')
        $result = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    if ($result -ne 0) { Invoke-AppPython $script:Python @('-m', 'pip', 'install', '-r', (Join-Path $script:AppRoot 'requirements.txt')) }
}

function Initialize-AppIndexes([switch]$Rebuild) {
    New-Item -ItemType Directory -Force -Path $script:ConfigDirectory | Out-Null
    $shards = Join-Path $script:DataDirectory 'shards'
    $indexes = Join-Path $script:DataDirectory 'indexes\nodes'
    $statistics = Join-Path $script:DataDirectory 'indexes\global_statistics.json'
    $partitionConfig = Join-Path $script:ConfigDirectory 'partition_config.json'
    $indexConfig = Join-Path $script:ConfigDirectory 'distributed_index_config.json'
    Write-AppJson $partitionConfig @{
        documents_file = (Join-Path $script:AppRoot 'data\documents.jsonl'); output_directory = $shards; shard_count = 3; strategy = 'range'
    }
    Write-AppJson $indexConfig @{
        shards_directory = $shards; partition_manifest = (Join-Path $shards 'partition_manifest.json'); indexes_directory = $indexes
        global_statistics_file = $statistics; minimum_token_length = 2; excluded_tokens = @()
    }
    $coordinator = Get-Content -LiteralPath (Join-Path $script:AppRoot 'coordinator\config\coordinator_config.json') -Raw | ConvertFrom-Json
    $coordinator.global_statistics_file = $statistics
    Write-AppJson $script:CoordinatorConfig $coordinator
    $required = @($statistics, (Join-Path $shards 'partition_manifest.json'))
    foreach ($number in 1..3) { $required += (Join-Path $shards "shard_$number.jsonl"); $required += (Join-Path $indexes "node_$($number)_index.json") }
    $missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
    if (-not $Rebuild -and $missing.Count -eq 0) { return }
    $documents = Join-Path $script:AppRoot 'data\documents.jsonl'
    if (-not (Test-Path -LiteralPath $documents -PathType Leaf)) { throw "Parsed corpus is missing: $documents. Run the crawler/parser documented in README.md before starting; the launcher does not crawl automatically." }
    $derived = @(@((Join-Path $script:DataDirectory 'shards'), (Join-Path $script:DataDirectory 'indexes')) | Where-Object { Test-Path -LiteralPath $_ })
    if ($derived.Count -gt 0) {
        $backup = Join-Path $script:RuntimeDirectory ('backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        foreach ($directory in $derived) { Copy-Item -LiteralPath $directory -Destination $backup -Recurse }
        Write-Host "Previous generated files backed up to $backup"
    }
    Write-Host 'Building three shard indexes from the existing parsed corpus ...'
    Invoke-AppPython $script:Python @('-m', 'partitioning.partitioner.cli', '--config', $partitionConfig)
    Invoke-AppPython $script:Python @('-m', 'distributed_indexing.builder.cli', '--config', $indexConfig)
}

function Save-AppNodeRecords($State) {
    # Capture the API's real Python child as well as its Windows venv redirector.
    $processes = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'")
    $apiChildren = @()
    $apiParents = @($State.Api.ProcessId)
    $remaining = @($processes | Where-Object { $_.ProcessId -ne $State.Api.ProcessId -and -not [string]::IsNullOrEmpty($_.CommandLine) -and $_.CommandLine.Contains('-m coordinator.api_server') })
    do {
        $found = $false
        foreach ($details in $remaining) {
            if ($details.ParentProcessId -notin $apiParents -or $details.ProcessId -in $apiParents) { continue }
            $record = Get-ProcessRecord $details.ProcessId '' $details
            if ($null -ne $record -and $null -ne (Get-OwnedProcess $State $record)) {
                $apiChildren += $record
                $apiParents += $details.ProcessId
                $found = $true
            }
        }
    } while ($found)
    $State.ApiChildren = $apiChildren
    # Node records include both redirectors and base-Python children, validated by unique artifact paths.
    $records = @()
    foreach ($details in $processes) {
        if ([string]::IsNullOrEmpty($details.CommandLine) -or -not $details.CommandLine.Contains('-m search_node.server')) { continue }
        foreach ($number in 1..3) {
            $nodeId = "node_$number"
            $indexPath = Join-Path $script:DataDirectory "indexes\nodes\$($nodeId)_index.json"
            if ($details.CommandLine.Contains($indexPath)) {
                $record = Get-ProcessRecord $details.ProcessId $nodeId $details
                if ($null -ne $record -and $null -ne (Get-OwnedProcess $State $record)) { $records += $record }
            }
        }
    }
    $State.Nodes = $records
    Write-AppJson $script:StateFile $State
}

function Stop-OwnedApp($State) {
    # Browser controls may have restarted nodes since the last saved records.
    Save-AppNodeRecords $State
    $api = Get-OwnedProcess $State $State.Api
    if ($null -ne $api) {
        foreach ($number in 1..3) {
            try { Invoke-AppApi "/api/nodes/node_$number/stop" 'Post' | Out-Null }
            catch { Write-Warning "Node $number did not stop through the API; checking its recorded identity." }
        }
    }
    # Kill real children before redirectors so Windows cannot leave a listening orphan.
    foreach ($record in @($State.Nodes | Sort-Object { $_.ExecutablePath -eq $script:Python })) {
        $node = Get-OwnedProcess $State $record
        if ($null -ne $node) { Stop-Process -Id $node.Id -Force; $node.WaitForExit(5000) | Out-Null }
    }
    foreach ($record in @($State.ApiChildren | Sort-Object ProcessId -Descending)) {
        $child = Get-OwnedProcess $State $record
        if ($null -ne $child) { Stop-Process -Id $child.Id -Force; $child.WaitForExit(5000) | Out-Null }
    }
    $api = Get-OwnedProcess $State $State.Api
    if ($null -ne $api) { Stop-Process -Id $api.Id -Force; $api.WaitForExit(5000) | Out-Null }
    Remove-Item -LiteralPath $script:StateFile -ErrorAction SilentlyContinue
}
