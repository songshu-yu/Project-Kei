$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "project-kei.common.ps1")

try {
    $Profile = Get-KeiCliProfile -Arguments $args -DefaultProfile "core" -AllowedProfiles @("core", "voice", "qq", "full", "dev")
} catch {
    Write-KeiResult "error" "arguments" ("{0}; use --profile core|voice|qq|full|dev" -f $_.Exception.Message)
    exit 2
}

$Errors = 0
Write-Host "[Project Kei doctor] profile=$Profile"
Write-Host "[Project Kei doctor] read-only: no install, download, configuration write, service start, or business-network probe"

$Platform = Test-KeiWindowsPlatform
if ($Platform.Ok) {
    Write-KeiResult "ok" "platform" "Windows x64"
} else {
    Write-KeiResult "error" "platform" "Windows 10/11 x64 is required."
    $Errors++
}
$PowerShell = Test-KeiPowerShellVersion
if ($PowerShell.Ok) {
    Write-KeiResult "ok" "powershell" $PowerShell.Version
} else {
    Write-KeiResult "error" "powershell" ("unsupported {0}; use Windows PowerShell 5.1 or PowerShell 7.4+" -f $PowerShell.Version)
    $Errors++
}
$GitCommand = Get-Command "git.exe" -ErrorAction SilentlyContinue
if ($null -eq $GitCommand) {
    $GitCommand = Get-Command "git" -ErrorAction SilentlyContinue
}
if ($null -eq $GitCommand) {
    Write-KeiResult "warn" "git" "not on PATH; an existing checkout can still be diagnosed."
} else {
    $GitVersion = (& $GitCommand.Source --version 2>$null).Trim()
    Write-KeiResult "ok" "git" $GitVersion
}

$Runtime = Resolve-KeiPython
if ($null -eq $Runtime) {
    Write-KeiResult "error" "python" "no supported Python found; install Python 3.10, 3.11, 3.12, or 3.13 x64 from python.org (3.11 recommended), or run setup.bat."
    $Errors++
} else {
    Write-KeiResult "ok" "python" ("{0}; Python {1} x64" -f $Runtime.Name, $Runtime.Version)
}

$Locks = @("core-win.lock.txt")
if ($Profile -eq "voice" -or $Profile -eq "full") {
    $Locks += "asr-win.lock.txt"
    $Locks += "voice-media-win.lock.txt"
}
if ($Profile -eq "dev") {
    $Locks += "dev-win.lock.txt"
}
foreach ($LockName in $Locks) {
    $Integrity = Test-KeiLockIntegrity -LockName $LockName
    if ($Integrity.Ok) {
        Write-KeiResult "ok" "lock" ("{0} sha256={1}" -f $LockName, $Integrity.Message)
    } else {
        Write-KeiResult "error" "lock" ("{0}: {1}" -f $LockName, $Integrity.Message)
        $Errors++
    }
}

if ($null -ne $Runtime) {
    $Imports = switch ($Profile) {
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
        $ImportExit = Invoke-KeiPython -Runtime $Runtime -Arguments @("-B", "-c", $Imports)
    } finally {
        $env:PYTHONPATH = $OldPythonPath
    }
    if ($ImportExit -eq 0) {
        Write-KeiResult "ok" "imports" ("profile {0}" -f $Profile)
    } else {
        Write-KeiResult "error" "imports" "selected profile is not installed in the resolved runtime; run setup.bat for this profile."
        $Errors++
    }
}

if (($Profile -eq "voice" -or $Profile -eq "full") -and $null -ne $Runtime) {
    $VoiceMedia = Get-KeiVoiceMediaReadiness -Runtime $Runtime
    if ($VoiceMedia.Ok) {
        Write-KeiResult "ok" "voice-media" "silk-python 0.2.8 version, import, and encoder capability are available; no audio was encoded."
    } else {
        Write-KeiResult "error" "voice-media" ("voice media unavailable ({0}); run setup.bat --profile voice. Core remains available." -f $VoiceMedia.Code)
        $Errors++
    }
}

if (Test-KeiPortInUse -Port 8000) {
    Write-KeiResult "warn" "port-8000" "already in use; start will not replace or stop the owner."
} else {
    Write-KeiResult "ok" "port-8000" "available"
}

if ($Profile -eq "voice" -or $Profile -eq "full") {
    foreach ($Port in @(8010, 9880)) {
        if (Test-KeiPortInUse -Port $Port) {
            Write-KeiResult "warn" ("port-{0}" -f $Port) "already in use; start will not replace or stop the owner."
        } else {
            Write-KeiResult "ok" ("port-{0}" -f $Port) "available"
        }
    }
    $AsrModelSource = Resolve-KeiAsrModelPath
    if ([string]::IsNullOrWhiteSpace($AsrModelSource)) {
        Write-KeiResult "warn" "asr-model" "no configured or project-local model was found; doctor did not scan the disk or download anything."
    } elseif ($AsrModelSource.StartsWith("project-", [StringComparison]::Ordinal)) {
        Write-KeiResult "ok" "asr-model" ("{0} is available; its path and contents were not displayed" -f $AsrModelSource)
    } else {
        Write-KeiResult "ok" "asr-model" "ASR_MODEL_PATH is set; its value and target were not read."
    }
    $EngineConfig = Join-Path $script:ProjectKeiServerRoot "data\gpt_sovits_engine.local.json"
    if (Test-Path -LiteralPath $EngineConfig -PathType Leaf) {
        Write-KeiResult "ok" "gpt-sovits" "local registration file exists; content and engine directories were not read."
    } else {
        Write-KeiResult "warn" "gpt-sovits" "not registered; use the explicit PK-211 workflow. Core is unaffected."
    }
    $VoiceRegistry = Join-Path $script:ProjectKeiServerRoot "data\voice_pack_registry.local.json"
    if (Test-Path -LiteralPath $VoiceRegistry -PathType Leaf) {
        Write-KeiResult "ok" "voice-pack" "local registry exists; content and model assets were not read."
    } else {
        Write-KeiResult "warn" "voice-pack" "not registered; use the PK-212 import workflow. Core is unaffected."
    }
}

if ($Profile -eq "qq" -or $Profile -eq "full") {
    $Node = Get-KeiNodeRuntime
    $Npm = Get-KeiNpmRuntime
    if ($null -eq $Node -or $null -eq $Npm) {
        Write-KeiResult "error" "node" "Node.js 20, 22, 24, or 26 x64 with npm 9, 10, or 11 is required for this profile; Node 24 LTS is recommended."
        $Errors++
    } else {
        Write-KeiResult "ok" "node" (
            "Node {0} {1}; npm {2}" -f $Node.Version, $Node.Arch, $Npm.Version
        )
    }
    $QqResolution = if ($null -ne $Runtime) {
        Invoke-KeiQqDependencyDeployment -Runtime $Runtime -Action "inspect"
    } else {
        [pscustomobject]@{ Status = "error"; Code = "python_runtime_missing"; Path = $null }
    }
    if ($QqResolution.Status -eq "error") {
        Write-KeiResult "error" "qq-dependencies" (
            "installed module dependency state is invalid ({0}); repair or reinstall the current QQ module." -f
            $QqResolution.Code
        )
        $Errors++
        $QqRoot = $null
        $QqTarget = "installed QQ module"
    } elseif ($QqResolution.Status -eq "ready") {
        $QqRoot = $null
        $QqTarget = "installed QQ module"
        Write-KeiResult "ok" "qq-dependencies" (
            "installed QQ module deployment marker, package digests, lock, Node/npm contract, and dependencies are ready."
        )
    } elseif ($QqResolution.Status -eq "missing") {
        $QqRoot = $null
        $QqTarget = "installed QQ module"
        Write-KeiResult "error" "qq-dependencies" (
            "installed QQ module dependencies are missing; run setup.bat --profile qq."
        )
        $Errors++
    } else {
        $QqRoot = Join-Path $script:ProjectKeiServerRoot "qq_bridge"
        $QqTarget = "source-tree QQ compatibility bridge"
    }
    if ($null -ne $QqRoot -and
        (Test-Path -LiteralPath (Join-Path $QqRoot "node_modules\ws") -PathType Container)) {
        $NodeImportExit = 1
        if ($null -ne $Node) {
            Push-Location -LiteralPath $QqRoot
            try {
                $PreviousErrorPreference = $ErrorActionPreference
                $ErrorActionPreference = "SilentlyContinue"
                & $Node.FilePath --input-type=module -e "import('ws')" 2>$null | Out-Null
                $NodeImportExit = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $PreviousErrorPreference
                Pop-Location
            }
        }
        if ($NodeImportExit -eq 0) {
            Write-KeiResult "ok" "qq-dependencies" (
                "{0} ws import succeeded; package-lock.json was not modified." -f $QqTarget
            )
        } else {
            Write-KeiResult "error" "qq-dependencies" (
                "{0} ws import failed; run setup.bat --profile qq." -f $QqTarget
            )
            $Errors++
        }
    } elseif ($null -ne $QqRoot) {
        Write-KeiResult "error" "qq-dependencies" (
            "{0} dependencies are missing; run setup.bat --profile qq." -f $QqTarget
        )
        $Errors++
    }
    $QqConfigRoot = Join-Path $script:ProjectKeiServerRoot "qq_bridge"
    if (Test-Path -LiteralPath (Join-Path $QqConfigRoot ".env") -PathType Leaf) {
        Write-KeiResult "ok" "qq-config" ".env exists; it was not read."
    } else {
        Write-KeiResult "warn" "qq-config" "missing; copy server\qq_bridge\.env.example manually and fill required fields. Core is unaffected."
    }
}

if ($Errors -gt 0) {
    Write-KeiResult "error" "doctor" ("{0} blocking check(s) failed for profile {1}" -f $Errors, $Profile)
    exit 1
}
Write-KeiResult "ok" "doctor" ("profile {0}; warnings are optional or operational and Core remains available" -f $Profile)
exit 0
