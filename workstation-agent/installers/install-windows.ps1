[CmdletBinding()]
param(
    [string]$BinaryPath
)

$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$AgentRoot = Join-Path $env:LOCALAPPDATA 'FilamentManagerAgent'
New-Item -ItemType Directory -Path $AgentRoot -Force | Out-Null
if ($BinaryPath) {
    $ResolvedBinary = Resolve-Path $BinaryPath
    $Agent = Join-Path $AgentRoot 'filament-manager-agent.exe'
    Copy-Item -LiteralPath $ResolvedBinary -Destination $Agent -Force
    Unblock-File -LiteralPath $Agent -ErrorAction SilentlyContinue
}
else {
    $VirtualEnvironment = Join-Path $AgentRoot 'venv'
    $Python = Join-Path $VirtualEnvironment 'Scripts\python.exe'
    $Agent = Join-Path $VirtualEnvironment 'Scripts\filament-manager-agent.exe'
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $Launcher) {
        throw 'Python 3.12 or newer is required. Install it for the current user first.'
    }
    & $Launcher.Source -3.12 -m venv $VirtualEnvironment
    & $Python -m pip install --upgrade pip
    & $Python -m pip install --upgrade $SourceRoot
}

$TaskName = 'Filament Manager Cura Agent'
$Action = New-ScheduledTaskAction -Execute $Agent -Argument 'run'
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

Write-Host 'Agent installed as a per-user logon task. Pair it before starting the task:'
Write-Host ('  & "{0}" pair --server https://YOUR-SERVER --name "Windows Cura"' -f $Agent)
Write-Host ('Then run: Start-ScheduledTask -TaskName "{0}"' -f $TaskName)
