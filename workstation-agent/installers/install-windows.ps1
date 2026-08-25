[CmdletBinding()]
param(
    [string]$BinaryPath,
    [string]$ServerUrl,
    [string]$WorkstationName,
    [string]$PairingCode,
    [switch]$SkipPairing,
    [switch]$SkipPathUpdate
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
$PairingConfig = Join-Path $env:LOCALAPPDATA 'Filament Manager Agent\config.json'

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
    $AgentCommandRoot = Split-Path -Parent $Agent
    if (-not $SkipPathUpdate) {
        $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        $UserPathEntries = @($UserPath -split ';' | Where-Object { $_ })
        if (-not ($UserPathEntries | Where-Object { $_.TrimEnd('\') -ieq $AgentCommandRoot.TrimEnd('\') })) {
            $UpdatedUserPath = (@($UserPathEntries) + $AgentCommandRoot) -join ';'
            [Environment]::SetEnvironmentVariable('Path', $UpdatedUserPath, 'User')
        }
        if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $AgentCommandRoot.TrimEnd('\') })) {
            $env:Path = "$AgentCommandRoot;$env:Path"
        }
    }

    $Action = New-ScheduledTaskAction -Execute $Agent -Argument 'run'
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

    $IsPaired = Test-Path -LiteralPath $PairingConfig
    if (-not $IsPaired -and -not $SkipPairing) {
        if (-not $ServerUrl) {
            $ServerUrl = Read-Host 'Filament Manager server URL (https://...)'
        }
        if (-not $WorkstationName) {
            $DefaultName = if ($env:COMPUTERNAME) { "$($env:COMPUTERNAME) Cura" } else { 'Windows Cura' }
            $EnteredName = Read-Host "Workstation name [$DefaultName]"
            $WorkstationName = if ($EnteredName) { $EnteredName } else { $DefaultName }
        }
        if (-not $ServerUrl) {
            throw 'A Filament Manager server URL is required to pair the workstation.'
        }
        $PairArguments = @('pair', '--server', $ServerUrl, '--name', $WorkstationName)
        if ($PairingCode) {
            $PairArguments += @('--code', $PairingCode)
        }
        & $Agent @PairArguments
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PairingConfig)) {
            throw 'The workstation agent could not be paired. The startup task was installed but was not started.'
        }
        $IsPaired = $true
    }

    if ($TaskWasRunning -or $IsPaired) {
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

if ($ExistingInstallation -and ($TaskWasRunning -or (Test-Path -LiteralPath $PairingConfig))) {
    Write-Host 'Agent upgraded and the existing per-user task was restarted. Pairing and private configuration were preserved.'
}
elseif ($ExistingInstallation) {
    Write-Host 'Filament Manager Agent upgrade complete. The task was not running before the upgrade, so it remains stopped.'
}
else {
    Write-Host 'Filament Manager Agent fresh installation complete. The paired per-user agent is running and will start automatically at logon.'
    Write-Host 'Open a new terminal to use filament-manager-agent from PATH.'
}
