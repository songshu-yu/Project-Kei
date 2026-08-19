$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "project-kei.common.ps1")

try {
    $Profile = Get-KeiCliProfile -Arguments $args -DefaultProfile "core" -AllowedProfiles @("core", "voice", "qq", "full", "dev")
} catch {
    Write-KeiResult "error" "arguments" ("{0}; use --profile core|voice|qq|full|dev" -f $_.Exception.Message)
    exit 2
}

Write-Host "[Project Kei setup] profile=$Profile root=$script:ProjectKeiRoot"

$Platform = Test-KeiWindowsPlatform
if (-not $Platform.Ok) {
    Write-KeiResult "error" "platform" "Windows 10/11 x64 is required."
    exit 10
}
$PowerShell = Test-KeiPowerShellVersion
if (-not $PowerShell.Ok) {
    Write-KeiResult "error" "powershell" ("unsupported version {0}; use Windows PowerShell 5.1 or PowerShell 7.4+" -f $PowerShell.Version)
    exit 10
}
$GitCommand = Get-Command "git.exe" -ErrorAction SilentlyContinue
if ($null -eq $GitCommand) {
    $GitCommand = Get-Command "git" -ErrorAction SilentlyContinue
}
if ($null -eq $GitCommand) {
    Write-KeiResult "warn" "git" "Git is not on PATH; setup can continue from an existing checkout."
} else {
    $GitVersion = (& $GitCommand.Source --version 2>$null).Trim()
    Write-KeiResult "ok" "git" $GitVersion
}

$RootVenv = Join-Path $script:ProjectKeiRoot ".venv"
$RootPython = Join-Path $RootVenv "Scripts\python.exe"
$Runtime = $null
if (Test-Path -LiteralPath $RootVenv) {
    $Runtime = New-KeiPythonCandidate -Name "project .venv" -FilePath $RootPython
    if ($null -eq $Runtime) {
        Write-KeiResult "error" "python" "existing .venv is incomplete or unsupported; it was not changed. Move it aside manually, then rerun setup."
        exit 11
    }
    Write-KeiResult "ok" "python" ("reusing .venv (Python {0} x64)" -f $Runtime.Version)
} else {
    $Bootstrap = Resolve-KeiPython -ExcludeProjectVenv
    if ($null -eq $Bootstrap) {
        Write-KeiResult "error" "python" "install Python 3.10, 3.11, 3.12, or 3.13 x64 from python.org (3.11 recommended), enable the py launcher or PATH, then rerun setup.bat."
        exit 11
    }
    Write-KeiResult "ok" "python" ("bootstrap {0}, Python {1} x64" -f $Bootstrap.Name, $Bootstrap.Version)
    $VenvExit = Invoke-KeiPython -Runtime $Bootstrap -Arguments @("-m", "venv", $RootVenv)
    if ($VenvExit -ne 0) {
        Write-KeiResult "error" "python" "venv_create_failed; verify the Python venv component and write access, then rerun setup."
        exit 11
    }
    $Runtime = New-KeiPythonCandidate -Name "project .venv" -FilePath $RootPython
    if ($null -eq $Runtime) {
        Write-KeiResult "error" "python" "venv_validation_failed; setup did not delete or replace the created directory."
        exit 11
    }
    Write-KeiResult "ok" "python" ("created .venv with Python {0} x64" -f $Runtime.Version)
}

$PythonLocks = @(
    [pscustomobject]@{ Name = "core-win.lock.txt"; HashLockedWheels = $false }
)
if ($Profile -eq "voice" -or $Profile -eq "full") {
    if ($Runtime.Implementation -ne "CPython") {
        Write-KeiResult "error" "voice-media" "voice media requires Windows CPython x64 3.10, 3.11, 3.12, or 3.13; no source or unlocked fallback is allowed. Core remains available."
        exit 11
    }
    $PythonLocks += [pscustomobject]@{ Name = "asr-win.lock.txt"; HashLockedWheels = $false }
    $PythonLocks += [pscustomobject]@{ Name = "voice-media-win.lock.txt"; HashLockedWheels = $true }
}
if ($Profile -eq "dev") {
    $PythonLocks += [pscustomobject]@{ Name = "dev-win.lock.txt"; HashLockedWheels = $false }
}
foreach ($Lock in $PythonLocks) {
    $LockName = $Lock.Name
    $Integrity = Test-KeiLockIntegrity -LockName $LockName
    if (-not $Integrity.Ok) {
        Write-KeiResult "error" "lock" ("{0}: {1}; restore the tracked requirements files before retrying" -f $LockName, $Integrity.Message)
        exit 12
    }
    Write-KeiResult "ok" "lock" ("{0} sha256={1}" -f $LockName, $Integrity.Message)
    $PipArguments = @(
        "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
        "--requirement", $Integrity.Path
    )
    if ($Lock.HashLockedWheels) {
        $PipArguments += @("--require-hashes", "--only-binary=:all:")
    }
    $PipExit = Invoke-KeiPython -Runtime $Runtime -Arguments $PipArguments
    if ($PipExit -ne 0) {
        if ($Lock.HashLockedWheels) {
            Write-KeiResult "error" "pip" "voice_media_install_failed; public-index/network access failed, the wheel hash did not match, or no locked Windows CPython x64 wheel matched. No source or unlocked version was used. Core remains available."
        } else {
            Write-KeiResult "error" "pip" ("dependency_install_failed for {0}; check public-index/network access and rerun the same profile" -f $LockName)
        }
        exit 13
    }
}

if ($Profile -eq "qq" -or $Profile -eq "full") {
    $Node = Get-KeiNodeRuntime
    $Npm = Get-KeiNpmRuntime
    if ($null -eq $Node -or $null -eq $Npm) {
        Write-KeiResult "error" "node" "install Node.js 24 LTS x64 (supported: 20, 22, 24, 26) with npm 9, 10, or 11, then rerun setup."
        exit 14
    }
    Write-KeiResult "ok" "node" (
        "Node {0} {1}; npm {2}" -f $Node.Version, $Node.Arch, $Npm.Version
    )
    $QqPreparation = Invoke-KeiQqDependencyDeployment `
        -Runtime $Runtime `
        -Action "prepare"
    if ($QqPreparation.Status -eq "error") {
        Write-KeiResult "error" "npm" (
            "installed_qq_module_invalid:{0}; repair or reinstall the current QQ module, then rerun setup." -f
            $QqPreparation.Code
        )
        exit 14
    }
    if ($QqPreparation.Status -eq "ready") {
        Write-KeiResult "ok" "npm" (
            "installed QQ module dependency deployment already matches the current package and lock."
        )
    } elseif ($QqPreparation.Status -eq "prepared") {
        Push-Location -LiteralPath $QqPreparation.Path
        try {
            & $Npm.FilePath ci --ignore-scripts
            $NpmExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($NpmExit -ne 0) {
            Invoke-KeiQqDependencyDeployment `
                -Runtime $Runtime `
                -Action "abort" `
                -Locator $QqPreparation.Locator | Out-Null
            Write-KeiResult "error" "npm" (
                "npm_ci_failed for installed QQ module deployment; the previous deployment and installed package were not changed."
            )
            exit 14
        }
        $Commit = Invoke-KeiQqDependencyDeployment `
            -Runtime $Runtime `
            -Action "commit" `
            -Locator $QqPreparation.Locator `
            -NodeVersion $Node.Version `
            -NpmVersion $Npm.Version
        if ($Commit.Status -ne "ready") {
            Invoke-KeiQqDependencyDeployment `
                -Runtime $Runtime `
                -Action "abort" `
                -Locator $QqPreparation.Locator | Out-Null
            Write-KeiResult "error" "npm" (
                "qq_module_deployment_commit_failed:{0}; the installed package, registry, configuration, and QQ data were not changed." -f
                $Commit.Code
            )
            exit 14
        }
        Write-KeiResult "ok" "npm" (
            "installed QQ module dependency deployment now matches the current immutable package and lock."
        )
    } elseif ($QqPreparation.Status -eq "absent") {
        $QqRoot = Join-Path $script:ProjectKeiServerRoot "qq_bridge"
        $QqTarget = "source-tree QQ compatibility bridge"
        Push-Location -LiteralPath $QqRoot
        try {
            & $Npm.FilePath ci --ignore-scripts
            $NpmExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($NpmExit -ne 0) {
            Write-KeiResult "error" "npm" (
                "npm_ci_failed for {0}; verify its package-lock.json and public registry access, then rerun the same profile." -f
                $QqTarget
            )
            exit 14
        }
        Write-KeiResult "ok" "npm" (
            "{0} dependencies match package-lock.json; no configuration or QQ data was read or created." -f
            $QqTarget
        )
    } else {
        Write-KeiResult "error" "npm" (
            "qq_module_deployment_failed:{0}; no installed package, registry, configuration, or QQ data was changed." -f
            $QqPreparation.Status
        )
        exit 14
    }
}

$ImportNames = switch ($Profile) {
    "voice" { "import fastapi,httpx,pydantic,uvicorn; import faster_whisper" }
    "full" { "import fastapi,httpx,pydantic,uvicorn; import faster_whisper" }
    "dev" { "import fastapi,httpx,pydantic,uvicorn; import pytest,pytest_asyncio,piptools" }
    default { "import fastapi,httpx,pydantic,uvicorn" }
}
$OldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($OldPythonPath)) {
    $script:ProjectKeiServerRoot
} else {
    $script:ProjectKeiServerRoot + [IO.Path]::PathSeparator + $OldPythonPath
}
$env:PYTHONDONTWRITEBYTECODE = "1"
try {
    $ImportExit = Invoke-KeiPython -Runtime $Runtime -Arguments @("-B", "-c", $ImportNames)
} finally {
    $env:PYTHONPATH = $OldPythonPath
}
if ($ImportExit -ne 0) {
    Write-KeiResult "error" "health" "core_import_failed; rerun setup after resolving the reported locked dependency failure."
    exit 15
}

if ($Profile -eq "voice" -or $Profile -eq "full") {
    $VoiceMedia = Get-KeiVoiceMediaReadiness -Runtime $Runtime
    if (-not $VoiceMedia.Ok) {
        Write-KeiResult "error" "voice-media" ("voice_media_health_failed:{0}; the locked wheel did not provide silk-python 0.2.8 with encoder capability. Core remains available." -f $VoiceMedia.Code)
        exit 15
    }
    Write-KeiResult "ok" "voice-media" "silk-python 0.2.8 import and encoder capability are available; setup did not encode audio."
}

Write-KeiResult "ok" "setup" ("profile {0} is installed; no .env, service, engine, model, or Voice Pack was created or started" -f $Profile)
Write-Host "Next: doctor.bat --profile $Profile"
Write-Host "Start Core: start.bat"
exit 0
