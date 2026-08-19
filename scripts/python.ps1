$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "project-kei.common.ps1")

if ($args.Count -eq 0) {
    Write-KeiResult "error" "arguments" "pass Python module or script arguments, for example: .\scripts\python.ps1 tests\test_feature_catalog.py"
    exit 2
}
$Runtime = Resolve-KeiPython
if ($null -eq $Runtime) {
    Write-KeiResult "error" "python" "no supported runtime found; run setup.bat first."
    exit 20
}
$OldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($OldPythonPath)) {
    $script:ProjectKeiServerRoot
} else {
    $script:ProjectKeiServerRoot + [IO.Path]::PathSeparator + $OldPythonPath
}
$env:PYTHONDONTWRITEBYTECODE = "1"
Push-Location -LiteralPath $script:ProjectKeiServerRoot
try {
    exit (Invoke-KeiPython -Runtime $Runtime -Arguments @($args))
} finally {
    Pop-Location
    $env:PYTHONPATH = $OldPythonPath
}
