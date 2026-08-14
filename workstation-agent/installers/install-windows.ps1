[CmdletBinding()]
param(
    [string]$BinaryPath
)

$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$AgentRoot = Join-Path $env:LOCALAPPDATA 'FilamentManagerAgent'
$TaskName = 'Filament Manager Cura Agent'
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$ExistingInstallation = $ExistingTask -or (Test-Path -LiteralPath $AgentRoot)
if ($ExistingInstallation) {
    Write-Host 'Filament Manager Agent upgrade started. Existing pairing, state, and backups will be preserved.'
}
else {
    Write-Host 'Filament Manager Agent fresh installation started.'
}
New-Item -ItemType Directory -Path $AgentRoot -Force | Out-Null
$TaskWasRunning = $ExistingTask -and $ExistingTask.State -eq 'Running'
$StagedPath = $null
$BackupPath = $null
$InstalledPath = $null

try {
    if ($BinaryPath) {
        $ResolvedBinary = (Resolve-Path $BinaryPath).Path
        $InstalledPath = Join-Path $AgentRoot 'filament-manager-agent.exe'
        $StagedPath = Join-Path $AgentRoot ('.filament-manager-agent.{0}.new.exe' -f [guid]::NewGuid())
        Copy-Item -LiteralPath $ResolvedBinary -Destination $StagedPath
        Unblock-File -LiteralPath $StagedPath -ErrorAction SilentlyContinue
    }
    else {
        $VirtualEnvironment = Join-Path $AgentRoot 'venv'
        $InstalledPath = Join-Path $VirtualEnvironment 'Scripts\filament-manager-agent.exe'
        $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $Launcher) {
            throw 'Python 3.12 or newer is required. Install it for the current user first.'
        }
    }

    if ($TaskWasRunning) {
        Stop-ScheduledTask -TaskName $TaskName
        $Deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            Start-Sleep -Milliseconds 250
            $TaskState = (Get-ScheduledTask -TaskName $TaskName).State
        } while ($TaskState -eq 'Running' -and [DateTime]::UtcNow -lt $Deadline)
        if ($TaskState -eq 'Running') {
            throw 'The existing workstation agent did not stop within 30 seconds.'
        }
    }

    if ($BinaryPath) {
        if (Test-Path -LiteralPath $InstalledPath) {
            $BackupPath = Join-Path $AgentRoot '.filament-manager-agent.backup.exe'
            Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $InstalledPath -Destination $BackupPath
        }
        Move-Item -LiteralPath $StagedPath -Destination $InstalledPath
    }
    else {
        $VirtualEnvironment = Join-Path $AgentRoot 'venv'
        $Python = Join-Path $VirtualEnvironment 'Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $Python)) {
            & $Launcher.Source -3.12 -m venv $VirtualEnvironment
            if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Python environment.' }
        }
        & $Python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'Unable to prepare pip in the agent environment.' }
        & $Python -m pip install --upgrade $SourceRoot
        if ($LASTEXITCODE -ne 0) { throw 'Unable to upgrade the agent environment.' }
    }
    $StagedPath = $null

    $Agent = $InstalledPath
    $Action = New-ScheduledTaskAction -Execute $Agent -Argument 'run'
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

    if ($TaskWasRunning) {
        Start-ScheduledTask -TaskName $TaskName
    }
    if ($BackupPath -and (Test-Path -LiteralPath $BackupPath)) {
        Remove-Item -LiteralPath $BackupPath -Recurse -Force
        $BackupPath = $null
    }
}
catch {
    if ($BackupPath -and (Test-Path -LiteralPath $BackupPath)) {
        if (Test-Path -LiteralPath $InstalledPath) {
            Remove-Item -LiteralPath $InstalledPath -Recurse -Force
        }
        Move-Item -LiteralPath $BackupPath -Destination $InstalledPath
    }
    if ($TaskWasRunning) {
        Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    }
    throw
}
finally {
    if ($StagedPath -and (Test-Path -LiteralPath $StagedPath)) {
        Remove-Item -LiteralPath $StagedPath -Recurse -Force
    }
}

if ($ExistingInstallation -and $TaskWasRunning) {
    Write-Host 'Agent upgraded and the existing per-user task was restarted. Pairing and private configuration were preserved.'
}
elseif ($ExistingInstallation) {
    Write-Host 'Filament Manager Agent upgrade complete. The task was not running before the upgrade, so it remains stopped.'
}
else {
    Write-Host 'Filament Manager Agent fresh installation complete as a per-user logon task.'
    Write-Host 'Pair this new installation:'
    Write-Host ('  & "{0}" pair --server https://YOUR-SERVER --name "Windows Cura"' -f $Agent)
    Write-Host ('Then run: Start-ScheduledTask -TaskName "{0}"' -f $TaskName)
}
