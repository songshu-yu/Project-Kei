$ErrorActionPreference = "Stop"
$PythonRunner = Join-Path $PSScriptRoot "python.ps1"
& $PythonRunner -m features.voice.voice_packs.distribution.cli @args
exit $LASTEXITCODE
