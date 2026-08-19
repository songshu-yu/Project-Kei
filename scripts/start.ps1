$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "project-kei.common.ps1")

$Profile = "core"
$Only = ""
$CurrentWindow = $false
$NoBrowser = $false
for ($Index = 0; $Index -lt $args.Count; $Index++) {
    $Argument = [string]$args[$Index]
    if ($Argument -eq "--profile" -or $Argument -eq "-Profile") {
        if ($Index + 1 -ge $args.Count) {
            Write-KeiResult "error" "arguments" "missing_profile_value"
            exit 2
        }
        $Index++
        $Profile = ([string]$args[$Index]).ToLowerInvariant()
        continue
    }
    if ($Argument.StartsWith("--profile=", [StringComparison]::OrdinalIgnoreCase)) {
        $Profile = $Argument.Substring("--profile=".Length).ToLowerInvariant()
        continue
    }
    if ($Argument -eq "--only" -or $Argument -eq "-Only") {
        if ($Index + 1 -ge $args.Count) {
            Write-KeiResult "error" "arguments" "missing_only_value"
            exit 2
        }
        $Index++
        $Only = ([string]$args[$Index]).ToLowerInvariant()
        continue
    }
    if ($Argument -eq "--current-window" -or $Argument -eq "-CurrentWindow") {
        $CurrentWindow = $true
        continue
    }
    if ($Argument -eq "--no-browser" -or $Argument -eq "-NoBrowser") {
        $NoBrowser = $true
        continue
    }
    Write-KeiResult "error" "arguments" ("unknown_argument:{0}" -f $Argument)
    exit 2
}
if (@("core", "voice", "qq", "all") -notcontains $Profile) {
    Write-KeiResult "error" "arguments" "use --profile core|voice|qq|all"
    exit 2
}
if (-not [string]::IsNullOrWhiteSpace($Only) -and @("api", "asr", "gptsovits") -notcontains $Only) {
    Write-KeiResult "error" "arguments" "internal --only must be api|asr|gptsovits"
    exit 2
}

$AsrModelSource = ""
if ($Only -eq "asr" -or $Profile -eq "voice" -or $Profile -eq "all") {
    [void](Import-KeiEnvAllowlist `
        -Path (Join-Path $script:ProjectKeiServerRoot ".env") `
        -Names @("ASR_MODEL_PATH", "ASR_DEVICE", "ASR_COMPUTE_TYPE"))
    $AsrModelSource = Resolve-KeiAsrModelPath
}

$Runtime = Resolve-KeiPython
if ($Only -ne "gptsovits" -and $null -eq $Runtime) {
    Write-KeiResult "error" "python" "no supported runtime found; run setup.bat first."
    exit 20
}

function Test-CorePreflight {
    param(
        [string]$SetupProfile = "core"
    )
    if (-not (Test-KeiPythonImports -Runtime $Runtime -ImportStatement "import fastapi,uvicorn")) {
        Write-KeiResult "error" "core" ("dependencies are incomplete in the selected .venv; rerun setup.bat --profile {0}, then doctor.bat --profile {0}. start never installs dependencies." -f $SetupProfile)
        return 21
    }
    if (Test-KeiPortInUse -Port 8000) {
        Write-KeiResult "error" "core" "port 8000 is already in use; no process was replaced or stopped."
        return 22
    }
    return 0
}

function Start-CoreDashboardBrowser {
    $DashboardUrl = "http://127.0.0.1:8000/dashboard"
    Write-KeiResult "ok" "dashboard" ("local browser address: {0}" -f $DashboardUrl)
    if ($NoBrowser -or $env:PROJECT_KEI_NO_BROWSER -eq "1") {
        Write-KeiResult "warn" "dashboard" "automatic browser launch is disabled; open the local browser address manually."
        return
    }
    $BrowserWaitScript = @'
$ErrorActionPreference = "SilentlyContinue"
$dashboardUrl = "http://127.0.0.1:8000/dashboard"
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ([DateTime]::UtcNow -lt $deadline) {
    $response = $null
    try {
        $request = [Net.HttpWebRequest]::Create($dashboardUrl)
        $request.Proxy = $null
        $request.Timeout = 1000
        $request.ReadWriteTimeout = 1000
        $response = $request.GetResponse()
        if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500) {
            $response.Close()
            Start-Process -FilePath $dashboardUrl
            exit 0
        }
    } catch {
    } finally {
        if ($null -ne $response) { $response.Close() }
    }
    Start-Sleep -Milliseconds 250
}
exit 1
'@
    try {
        $EncodedBrowserWait = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($BrowserWaitScript))
        Start-Process `
            -FilePath (Get-KeiPowerShellExecutable) `
            -ArgumentList @("-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", $EncodedBrowserWait) `
            -WindowStyle Hidden | Out-Null
        Write-KeiResult "ok" "dashboard" "the default browser will open after Core passes its local readiness check."
    } catch {
        Write-KeiResult "warn" "dashboard" ("could not schedule the browser; open {0} manually." -f $DashboardUrl)
    }
}

function Invoke-CoreApi {
    param(
        [switch]$PreflightCompleted,
        [string]$SetupProfile = "core"
    )
    if (-not $PreflightCompleted) {
        $PreflightExit = Test-CorePreflight -SetupProfile $SetupProfile
        if ($PreflightExit -ne 0) {
            return $PreflightExit
        }
    }
    $DashboardUrl = "http://127.0.0.1:8000/dashboard"
    Write-KeiResult "ok" "dashboard" ("local browser address: {0}" -f $DashboardUrl)
    if ($NoBrowser -or $env:PROJECT_KEI_NO_BROWSER -eq "1") {
        Write-KeiResult "warn" "dashboard" "automatic browser launch is disabled; open the local browser address manually."
    } else {
        $BrowserWaitScript = @'
$ErrorActionPreference = "SilentlyContinue"
$dashboardUrl = "http://127.0.0.1:8000/dashboard"
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ([DateTime]::UtcNow -lt $deadline) {
    $response = $null
    try {
        $request = [Net.HttpWebRequest]::Create($dashboardUrl)
        $request.Proxy = $null
        $request.Timeout = 1000
        $request.ReadWriteTimeout = 1000
        $response = $request.GetResponse()
        if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500) {
            $response.Close()
            Start-Process -FilePath $dashboardUrl
            exit 0
        }
    } catch {
    } finally {
        if ($null -ne $response) {
            $response.Close()
        }
    }
    Start-Sleep -Milliseconds 250
}
exit 1
'@
        try {
            $EncodedBrowserWait = [Convert]::ToBase64String(
                [Text.Encoding]::Unicode.GetBytes($BrowserWaitScript)
            )
            Start-Process `
                -FilePath (Get-KeiPowerShellExecutable) `
                -ArgumentList @(
                    "-NoProfile",
                    "-WindowStyle", "Hidden",
                    "-EncodedCommand", $EncodedBrowserWait
                ) `
                -WindowStyle Hidden | Out-Null
            Write-KeiResult "ok" "dashboard" "the default browser will open after Core passes its local readiness check."
        } catch {
            Write-KeiResult "warn" "dashboard" ("could not schedule the browser; open {0} manually." -f $DashboardUrl)
        }
    }
    Write-KeiResult "ok" "core" ("starting API listener on 127.0.0.1:8000 with {0}; press Ctrl+C in this window to stop" -f $Runtime.FilePath)
    $OldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($OldPythonPath)) {
        $script:ProjectKeiServerRoot
    } else {
        $script:ProjectKeiServerRoot + [IO.Path]::PathSeparator + $OldPythonPath
    }
    $env:PYTHONIOENCODING = "utf-8"
    try {
        Push-Location -LiteralPath $script:ProjectKeiServerRoot
        try {
            return (Invoke-KeiPython -Runtime $Runtime -Arguments @("-B", "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"))
        } finally {
            Pop-Location
        }
    } finally {
        $env:PYTHONPATH = $OldPythonPath
    }
}

function Invoke-CoreSupervisor {
    $SupervisorScript = Join-Path $script:ProjectKeiRoot "scripts\supervise_core.py"
    Start-CoreDashboardBrowser
    Write-KeiResult "ok" "core" ("starting supervised API listener on 127.0.0.1:8000 with {0}; dashboard restart requests affect Core only" -f $Runtime.FilePath)
    $OldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($OldPythonPath)) {
        $script:ProjectKeiServerRoot
    } else {
        $script:ProjectKeiServerRoot + [IO.Path]::PathSeparator + $OldPythonPath
    }
    $env:PYTHONIOENCODING = "utf-8"
    try {
        return (Invoke-KeiPython -Runtime $Runtime -Arguments @("-B", $SupervisorScript))
    } finally {
        $env:PYTHONPATH = $OldPythonPath
    }
}

function Start-AsrOptional {
    if (Test-KeiPortInUse -Port 8010) {
        Write-KeiResult "warn" "asr" "port 8010 is occupied; ASR was not started."
        return
    }
    if ([string]::IsNullOrWhiteSpace($AsrModelSource)) {
        Write-KeiResult "warn" "asr" "no configured or project-local ASR model was found; no disk scan or download was attempted."
        return
    }
    if ($AsrModelSource.StartsWith("project-", [StringComparison]::Ordinal)) {
        Write-KeiResult "ok" "asr-model" ("using {0}; its path is not displayed" -f $AsrModelSource)
    }
    $AsrScript = Join-Path $script:ProjectKeiServerRoot "scripts\start_asr.ps1"
    Start-KeiPowerShellWindow -ScriptPath $AsrScript -Arguments @() -WorkingDirectory $script:ProjectKeiServerRoot
    Write-KeiResult "ok" "asr" ("starting 127.0.0.1:8010 with {0}; close its window or press Ctrl+C there to stop" -f $Runtime.FilePath)
}

function Start-GptSoVitsOptional {
    if (Test-KeiPortInUse -Port 9880) {
        Write-KeiResult "warn" "gpt-sovits" "port 9880 is occupied; GPT-SoVITS was not started."
        return
    }
    $EngineConfig = if ([string]::IsNullOrWhiteSpace($env:GPT_SOVITS_LOCAL_CONFIG)) {
        Join-Path $script:ProjectKeiServerRoot "data\gpt_sovits_engine.local.json"
    } else {
        $env:GPT_SOVITS_LOCAL_CONFIG
    }
    if (-not (Test-Path -LiteralPath $EngineConfig -PathType Leaf)) {
        Write-KeiResult "warn" "gpt-sovits" "not registered; use the explicit PK-211 workflow. No acquisition was attempted."
        return
    }
    $GptScript = Join-Path $script:ProjectKeiServerRoot "scripts\start_gptsovits.ps1"
    Start-KeiPowerShellWindow -ScriptPath $GptScript -Arguments @() -WorkingDirectory $script:ProjectKeiServerRoot
    Write-KeiResult "ok" "gpt-sovits" "starting registered 127.0.0.1:9880 engine; close its window or press Ctrl+C there to stop."
}

if ($Only -eq "api") {
    exit (Invoke-CoreApi)
}
if ($Only -eq "asr") {
    if (-not (Test-KeiPythonImports -Runtime $Runtime -ImportStatement "import fastapi,uvicorn,faster_whisper")) {
        Write-KeiResult "error" "asr" "dependencies are incomplete; rerun setup.bat --profile voice, then doctor.bat --profile voice. start never installs dependencies."
        exit 21
    }
    if ([string]::IsNullOrWhiteSpace($AsrModelSource)) {
        Write-KeiResult "error" "asr" "no configured or project-local ASR model was found; no disk scan or download was attempted."
        exit 21
    }
    if ($AsrModelSource.StartsWith("project-", [StringComparison]::Ordinal)) {
        Write-KeiResult "ok" "asr-model" ("using {0}; its path is not displayed" -f $AsrModelSource)
    }
    if (Test-KeiPortInUse -Port 8010) {
        Write-KeiResult "error" "asr" "port 8010 is already in use."
        exit 22
    }
    $env:ASR_LOCAL_FILES_ONLY = "true"
    if ([string]::IsNullOrWhiteSpace($env:ASR_DEVICE)) { $env:ASR_DEVICE = "cpu" }
    if ([string]::IsNullOrWhiteSpace($env:ASR_COMPUTE_TYPE)) { $env:ASR_COMPUTE_TYPE = "int8" }
    Write-KeiResult "ok" "asr" ("starting 127.0.0.1:8010 with {0}; model value is not displayed" -f $Runtime.FilePath)
    Push-Location -LiteralPath $script:ProjectKeiServerRoot
    try {
        exit (Invoke-KeiPython -Runtime $Runtime -Arguments @("-B", "-m", "uvicorn", "services.asr_server:app", "--host", "127.0.0.1", "--port", "8010"))
    } finally {
        Pop-Location
    }
}
if ($Only -eq "gptsovits") {
    & (Join-Path $script:ProjectKeiServerRoot "scripts\start_gptsovits.ps1")
    exit $LASTEXITCODE
}
$CoreSetupProfile = switch ($Profile) {
    "voice" { "voice" }
    "qq" { "qq" }
    "all" { "full" }
    default { "core" }
}
$CorePreflightExit = Test-CorePreflight -SetupProfile $CoreSetupProfile
if ($CorePreflightExit -ne 0) {
    exit $CorePreflightExit
}

if ($Profile -eq "voice" -or $Profile -eq "all") {
    Start-GptSoVitsOptional
    Start-AsrOptional
}
if ($Profile -eq "qq" -or $Profile -eq "all") {
    Write-KeiResult "ok" "qq" "QQ module is enabled but waits for an explicit dashboard avatar or Start QQ Bridge click."
}

exit (Invoke-CoreSupervisor)
