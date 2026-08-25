[CmdletBinding()]
param(
    [switch]$SkipPathCleanup
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Filament Manager Cura Agent'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'FilamentManagerAgent'
$PrivateRoot = Join-Path $env:LOCALAPPDATA 'Filament Manager Agent'

Write-Host 'Filament Manager Agent uninstall started for the current user.'
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    if ($ExistingTask.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $TaskName
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

if (-not $SkipPathCleanup) {
    $ManagedCommandRoots = @($InstallRoot, (Join-Path $InstallRoot 'venv\Scripts'))
    $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $RetainedPathEntries = @($UserPath -split ';' | Where-Object {
        $Entry = $_.TrimEnd('\')
        $_ -and -not ($ManagedCommandRoots | Where-Object { $_.TrimEnd('\') -ieq $Entry })
    })
    $UpdatedUserPath = $RetainedPathEntries -join ';'
    if ($UpdatedUserPath -ne $UserPath) {
        [Environment]::SetEnvironmentVariable('Path', $UpdatedUserPath, 'User')
    }
}

foreach ($Target in @($InstallRoot, $PrivateRoot)) {
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

Write-Host 'Filament Manager Agent uninstall complete. The task, PATH entry, executable, pairing credential, local state, and agent backups were removed.'
Write-Host 'Managed Cura materials and plugins were left in place. Revoke the workstation in Filament Manager if it still exists there.'
