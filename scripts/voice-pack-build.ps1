$ErrorActionPreference = "Stop"
$PythonRunner = Join-Path $PSScriptRoot "python.ps1"
& $PythonRunner -m features.voice.voice_packs.distribution.build_cli @args
exit $LASTEXITCODE
