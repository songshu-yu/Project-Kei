$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "project-kei.common.ps1")

if ($args.Count -lt 1) {
    Write-KeiResult "error" "arguments" "tool name is required."
    exit 2
}
$ToolName = [string]$args[0]
$ToolArguments = @()
if ($args.Count -gt 1) {
    $ToolArguments = @($args[1..($args.Count - 1)])
}
$Tools = @{
    "prebuild-daily-briefing" = "scripts\prebuild_daily_briefing.py"
}
if (-not $Tools.ContainsKey($ToolName)) {
    Write-KeiResult "error" "arguments" "unsupported server tool."
    exit 2
}
$Runtime = Resolve-KeiPython
if ($null -eq $Runtime) {
    Write-KeiResult "error" "python" "no supported runtime found; run setup.bat first."
    exit 20
}
$ToolPath = Join-Path $script:ProjectKeiServerRoot $Tools[$ToolName]
Push-Location -LiteralPath $script:ProjectKeiServerRoot
try {
    exit (Invoke-KeiPython -Runtime $Runtime -Arguments (@("-B", $ToolPath) + $ToolArguments))
} finally {
    Pop-Location
}
