. (Join-Path $PSScriptRoot 'app_common.ps1')
try {
    $state = Read-AppState
    if ($null -eq $state) { Write-Host 'There is no tracked app to stop.'; exit 0 }
    Stop-OwnedApp $state
    Write-Host 'The tracked Distributed Search app has been stopped.'
} catch {
    Write-Host "Stop failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace
    Write-Host "Runtime state: $script:StateFile"
    exit 1
}
