$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
& (Join-Path $ProjectRoot "scripts\start.ps1") --only api --current-window @args
exit $LASTEXITCODE
