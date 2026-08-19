param(
    [string]$TaskName = "Project Kei Daily Briefing Cache",
    [string]$At = "08:00"
)

$ErrorActionPreference = "Stop"
$ServerRoot = Split-Path -Parent $PSScriptRoot
$BatPath = Join-Path $ServerRoot "prebuild_daily_briefing.bat"

if (-not (Test-Path $BatPath)) {
    throw "Cannot find $BatPath"
}

$ActionArguments = '/d /s /c "set PROJECT_KEI_NO_PAUSE=1&&call ""{0}"""' -f $BatPath
$Action = New-ScheduledTaskAction `
    -Execute $env:ComSpec `
    -Argument $ActionArguments `
    -WorkingDirectory $ServerRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Prebuild Project Kei daily briefing cache." `
    -Force

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Daily time: $At"
Write-Host "Command: $env:ComSpec $ActionArguments"
