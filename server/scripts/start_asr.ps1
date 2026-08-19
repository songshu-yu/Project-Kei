$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
& (Join-Path $ProjectRoot "scripts\start.ps1") --only asr --current-window @args
exit $LASTEXITCODE
