$ErrorActionPreference = "Stop"

$script:ProjectKeiRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$script:ProjectKeiServerRoot = Join-Path $script:ProjectKeiRoot "server"

function Write-KeiResult {
    param(
        [ValidateSet("ok", "warn", "error")]
        [string]$Level,
        [string]$Component,
        [string]$Message
    )
    Write-Host ("[{0}] {1}: {2}" -f $Level, $Component, $Message)
}

function Import-KeiEnvAllowlist {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$Names
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @()
    }

    $Allowed = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    foreach ($Name in $Names) {
        if ($Name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            [void]$Allowed.Add($Name)
        }
    }

    $Loaded = [Collections.Generic.List[string]]::new()
    foreach ($Line in [IO.File]::ReadLines($Path)) {
        $Candidate = ([string]$Line).Trim()
        if ([string]::IsNullOrWhiteSpace($Candidate) -or $Candidate.StartsWith("#")) {
            continue
        }
        if ($Candidate.StartsWith("export ", [StringComparison]::OrdinalIgnoreCase)) {
            $Candidate = $Candidate.Substring(7).TrimStart()
        }
        $Separator = $Candidate.IndexOf("=")
        if ($Separator -le 0) {
            continue
        }
        $Name = $Candidate.Substring(0, $Separator).Trim()
        if (-not $Allowed.Contains($Name)) {
            continue
        }
        if (-not [string]::IsNullOrWhiteSpace(
            [Environment]::GetEnvironmentVariable($Name, "Process")
        )) {
            continue
        }

        $Value = $Candidate.Substring($Separator + 1).Trim()
        if ($Value.Length -ge 2 -and (
            ($Value.StartsWith('"') -and $Value.EndsWith('"')) -or
            ($Value.StartsWith("'") -and $Value.EndsWith("'"))
        )) {
            $Value = $Value.Substring(1, $Value.Length - 2)
        } else {
            $InlineComment = [regex]::Match($Value, "\s+#")
            if ($InlineComment.Success) {
                $Value = $Value.Substring(0, $InlineComment.Index).TrimEnd()
            }
        }
        if ([string]::IsNullOrWhiteSpace($Value)) {
            continue
        }
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
        $Loaded.Add($Name)
    }
    return $Loaded.ToArray()
}

function Resolve-KeiAsrModelPath {
    if (-not [string]::IsNullOrWhiteSpace($env:ASR_MODEL_PATH)) {
        return "configured"
    }

    $Candidates = @(
        [pscustomobject]@{
            Name = "project-medium"
            Path = Join-Path $script:ProjectKeiServerRoot "models\asr\medium"
        },
        [pscustomobject]@{
            Name = "project-small"
            Path = Join-Path $script:ProjectKeiServerRoot "models\asr\small"
        }
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate.Path -PathType Container) {
            $env:ASR_MODEL_PATH = [IO.Path]::GetFullPath($Candidate.Path)
            return $Candidate.Name
        }
    }
    return ""
}

function Get-KeiCliProfile {
    param(
        [string[]]$Arguments,
        [string]$DefaultProfile,
        [string[]]$AllowedProfiles
    )
    $Profile = $DefaultProfile
    for ($Index = 0; $Index -lt $Arguments.Count; $Index++) {
        $Argument = [string]$Arguments[$Index]
        if ($Argument -eq "--profile" -or $Argument -eq "-Profile") {
            if ($Index + 1 -ge $Arguments.Count) {
                throw "missing_profile_value"
            }
            $Index++
            $Profile = [string]$Arguments[$Index]
            continue
        }
        if ($Argument.StartsWith("--profile=", [StringComparison]::OrdinalIgnoreCase)) {
            $Profile = $Argument.Substring("--profile=".Length)
            continue
        }
        throw "unknown_argument:$Argument"
    }
    $Profile = $Profile.ToLowerInvariant()
    if ($AllowedProfiles -notcontains $Profile) {
        throw "unsupported_profile:$Profile"
    }
    return $Profile
}

function Test-KeiWindowsPlatform {
    $IsWindowsHost = $env:OS -eq "Windows_NT"
    $IsX64Host = [Environment]::Is64BitOperatingSystem
    return [pscustomobject]@{
        Ok = ($IsWindowsHost -and $IsX64Host)
        IsWindows = $IsWindowsHost
        IsX64 = $IsX64Host
    }
}

function Test-KeiPowerShellVersion {
    $Version = $PSVersionTable.PSVersion
    $Supported = ($Version.Major -eq 5 -and $Version.Minor -ge 1) -or
        ($Version.Major -ge 7 -and $Version -ge [Version]"7.4")
    return [pscustomobject]@{
        Ok = $Supported
        Version = $Version.ToString()
    }
}

function Invoke-KeiPythonProbe {
    param(
        [string]$FilePath,
        [string[]]$PrefixArguments = @()
    )
    try {
        $Probe = "import platform,struct,sys; print('{0}.{1}|{2}|{3}' .format(sys.version_info[0],sys.version_info[1],struct.calcsize('P')*8,platform.python_implementation()))"
        $Output = & $FilePath @PrefixArguments -I -B -c $Probe 2>$null
        if ($LASTEXITCODE -ne 0 -or @($Output).Count -eq 0) {
            return $null
        }
        $Parts = ([string]@($Output)[-1]).Trim().Split("|")
        if ($Parts.Count -ne 3) {
            return $null
        }
        $Version = [Version]$Parts[0]
        return [pscustomobject]@{
            Ok = ($Version -ge [Version]"3.10" -and $Version -lt [Version]"3.14" -and $Parts[1] -eq "64")
            Version = $Version.ToString(2)
            Bits = [int]$Parts[1]
            Implementation = $Parts[2]
        }
    } catch {
        return $null
    }
}

function New-KeiPythonCandidate {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$PrefixArguments = @()
    )
    if ([string]::IsNullOrWhiteSpace($FilePath)) {
        return $null
    }
    if ([IO.Path]::IsPathRooted($FilePath) -and -not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        return $null
    }
    $Probe = Invoke-KeiPythonProbe -FilePath $FilePath -PrefixArguments $PrefixArguments
    if ($null -eq $Probe -or -not $Probe.Ok) {
        return $null
    }
    return [pscustomobject]@{
        Name = $Name
        FilePath = $FilePath
        PrefixArguments = @($PrefixArguments)
        Version = $Probe.Version
        Bits = $Probe.Bits
        Implementation = $Probe.Implementation
    }
}

function Resolve-KeiPython {
    param([switch]$ExcludeProjectVenv)

    $Candidates = New-Object System.Collections.Generic.List[object]
    if (-not $ExcludeProjectVenv) {
        $RootPython = Join-Path $script:ProjectKeiRoot ".venv\Scripts\python.exe"
        $Candidate = New-KeiPythonCandidate -Name "project .venv" -FilePath $RootPython
        if ($null -ne $Candidate) {
            $Candidates.Add($Candidate)
        }
    }

    $MigrationPython = Join-Path $script:ProjectKeiServerRoot ".venv-asr\Scripts\python.exe"
    $Candidate = New-KeiPythonCandidate -Name "migration server/.venv-asr" -FilePath $MigrationPython
    if ($null -ne $Candidate) {
        $Candidates.Add($Candidate)
    }

    $PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $PyLauncher) {
        foreach ($Selector in @("-3.11-64", "-3.13-64", "-3.12-64", "-3.10-64")) {
            $Candidate = New-KeiPythonCandidate -Name "py launcher $Selector" -FilePath $PyLauncher.Source -PrefixArguments @($Selector)
            if ($null -ne $Candidate) {
                $Candidates.Add($Candidate)
                break
            }
        }
    }

    $PathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $PathPython) {
        $Candidate = New-KeiPythonCandidate -Name "PATH python" -FilePath $PathPython.Source
        if ($null -ne $Candidate) {
            $Duplicate = $false
            foreach ($Existing in $Candidates) {
                if ($Existing.FilePath -eq $Candidate.FilePath -and
                    (@($Existing.PrefixArguments) -join " ") -eq (@($Candidate.PrefixArguments) -join " ")) {
                    $Duplicate = $true
                }
            }
            if (-not $Duplicate) {
                $Candidates.Add($Candidate)
            }
        }
    }

    if ($Candidates.Count -eq 0) {
        return $null
    }
    return $Candidates[0]
}

function Invoke-KeiPython {
    param(
        [Parameter(Mandatory = $true)]$Runtime,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Runtime.FilePath @($Runtime.PrefixArguments) @Arguments | ForEach-Object {
        Write-Host $_
    }
    $ProcessExitCode = $LASTEXITCODE
    return $ProcessExitCode
}

function Test-KeiPythonImports {
    param(
        [Parameter(Mandatory = $true)]$Runtime,
        [Parameter(Mandatory = $true)][string]$ImportStatement
    )
    try {
        & $Runtime.FilePath @($Runtime.PrefixArguments) -B -c $ImportStatement 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-KeiVoiceMediaReadiness {
    param([Parameter(Mandatory = $true)]$Runtime)

    if ($Runtime.Implementation -ne "CPython" -or
        $Runtime.Bits -ne 64 -or
        [Version]$Runtime.Version -lt [Version]"3.10" -or
        [Version]$Runtime.Version -ge [Version]"3.14") {
        return [pscustomobject]@{ Ok = $false; Code = "runtime_unsupported" }
    }

    $Probe = @"
import sys
from importlib import metadata
try:
    version = metadata.version("silk-python")
except metadata.PackageNotFoundError:
    raise SystemExit(31)
except Exception:
    raise SystemExit(32)
if version != "0.2.8":
    raise SystemExit(33)
try:
    import pysilk
except Exception:
    raise SystemExit(34)
if not callable(getattr(pysilk, "encode", None)):
    raise SystemExit(35)
"@
    $ProbeBytes = [Text.Encoding]::UTF8.GetBytes($Probe)
    $ProbeCommand = "exec(bytes(({0})).decode())" -f ($ProbeBytes -join ",")
    try {
        & $Runtime.FilePath @($Runtime.PrefixArguments) -I -B -c $ProbeCommand 2>$null | Out-Null
        $ProbeExit = $LASTEXITCODE
    } catch {
        $ProbeExit = 32
    }
    $Code = switch ($ProbeExit) {
        0 { "ready" }
        31 { "dependency_missing" }
        33 { "dependency_version_mismatch" }
        34 { "import_unavailable" }
        35 { "encoder_capability_missing" }
        default { "dependency_unavailable" }
    }
    return [pscustomobject]@{ Ok = ($ProbeExit -eq 0); Code = $Code }
}

function Invoke-KeiQqDependencyDeployment {
    param(
        [Parameter(Mandatory = $true)]$Runtime,
        [Parameter(Mandatory = $true)][ValidateSet("inspect", "prepare", "commit", "abort")][string]$Action,
        [string]$Locator,
        [string]$NodeVersion,
        [string]$NpmVersion
    )
    $ResolverPath = Join-Path $script:ProjectKeiRoot "scripts\resolve_qq_module_runtime.py"
    if (-not (Test-Path -LiteralPath $ResolverPath -PathType Leaf)) {
        return [pscustomobject]@{
            Status = "error"
            Code = "qq_module_resolver_missing"
            Path = $null
        }
    }
    $OldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($OldPythonPath)) {
        $script:ProjectKeiServerRoot
    } else {
        $script:ProjectKeiServerRoot + [IO.Path]::PathSeparator + $OldPythonPath
    }
    $env:PYTHONDONTWRITEBYTECODE = "1"
    try {
        $ResolverArguments = @("-B", $ResolverPath, $Action)
        if (-not [string]::IsNullOrWhiteSpace($Locator)) {
            $ResolverArguments += @("--locator", $Locator)
        }
        if (-not [string]::IsNullOrWhiteSpace($NodeVersion)) {
            $ResolverArguments += @("--node-version", $NodeVersion)
        }
        if (-not [string]::IsNullOrWhiteSpace($NpmVersion)) {
            $ResolverArguments += @("--npm-version", $NpmVersion)
        }
        $RawResult = @(
            & $Runtime.FilePath @($Runtime.PrefixArguments) @ResolverArguments 2>$null
        )
        $ResolverExit = $LASTEXITCODE
    } catch {
        $RawResult = @()
        $ResolverExit = 3
    } finally {
        $env:PYTHONPATH = $OldPythonPath
    }
    try {
        if ($RawResult.Count -ne 1) {
            throw "unexpected resolver output"
        }
        $Result = $RawResult[0] | ConvertFrom-Json
        $Status = [string]$Result.status
        if ($Status -in @("absent", "ready", "missing", "aborted") -and
            $ResolverExit -eq 0) {
            return [pscustomobject]@{
                Status = $Status
                Code = [string]$Result.code
                Path = $null
                Locator = $null
            }
        }
        $Locator = [string]$Result.locator
        if ($Status -eq "prepared" -and $ResolverExit -eq 0 -and
            $Locator -match '^qq_bridge/\.[0-9]+\.[0-9]+\.[0-9]+\.staging-[0-9a-f]{32}$') {
            $RuntimeRoot = Join-Path $script:ProjectKeiServerRoot "runtime\module-dependencies"
            $Current = $RuntimeRoot
            $Safe = $true
            try {
                $RuntimeItem = Get-Item -LiteralPath $RuntimeRoot -Force -ErrorAction Stop
                if (-not $RuntimeItem.PSIsContainer -or
                    (($RuntimeItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
                    $Safe = $false
                }
            } catch {
                $Safe = $false
            }
            foreach ($Part in $Locator.Split("/")) {
                if (-not $Safe) {
                    break
                }
                $Current = Join-Path $Current $Part
                try {
                    $Item = Get-Item -LiteralPath $Current -Force -ErrorAction Stop
                    if (-not $Item.PSIsContainer -or
                        (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
                        $Safe = $false
                        break
                    }
                } catch {
                    $Safe = $false
                    break
                }
            }
            foreach ($MetadataName in @("package.json", "package-lock.json")) {
                if (-not $Safe) {
                    break
                }
                try {
                    $MetadataItem = Get-Item -LiteralPath (
                        Join-Path $Current $MetadataName
                    ) -Force -ErrorAction Stop
                    if ($MetadataItem.PSIsContainer -or
                        (($MetadataItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
                        $Safe = $false
                    }
                } catch {
                    $Safe = $false
                }
            }
            if (-not $Safe) {
                return [pscustomobject]@{
                    Status = "error"
                    Code = "qq_module_link_rejected"
                    Path = $null
                }
            }
            return [pscustomobject]@{
                Status = "prepared"
                Code = $null
                Path = $Current
                Locator = $Locator
            }
        }
        $Code = [string]$Result.code
        if ([string]::IsNullOrWhiteSpace($Code)) {
            $Code = "qq_module_resolution_failed"
        }
        return [pscustomobject]@{ Status = "error"; Code = $Code; Path = $null }
    } catch {
        return [pscustomobject]@{
            Status = "error"
            Code = "qq_module_resolution_failed"
            Path = $null
        }
    }
}

function Get-KeiNodeRuntime {
    $NodeCommand = Get-Command "node.exe" -ErrorAction SilentlyContinue
    if ($null -eq $NodeCommand) {
        $NodeCommand = Get-Command "node" -ErrorAction SilentlyContinue
    }
    if ($null -eq $NodeCommand) {
        return $null
    }
    try {
        $RawVersion = (& $NodeCommand.Source --version 2>$null).TrimStart("v")
        $Version = [Version]$RawVersion
        $Arch = (& $NodeCommand.Source -p "process.arch" 2>$null).Trim()
        $SupportedMajor = @(20, 22, 24, 26) -contains $Version.Major
        if ($LASTEXITCODE -ne 0 -or -not $SupportedMajor -or $Arch -ne "x64") {
            return $null
        }
        return [pscustomobject]@{
            FilePath = $NodeCommand.Source
            Version = $Version.ToString()
            Arch = $Arch
        }
    } catch {
        return $null
    }
}

function Get-KeiNpmCommand {
    $Npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $Npm) {
        $Npm = Get-Command "npm" -ErrorAction SilentlyContinue
    }
    if ($null -eq $Npm) {
        return $null
    }
    return $Npm.Source
}

function Get-KeiNpmRuntime {
    $Npm = Get-KeiNpmCommand
    if ($null -eq $Npm) {
        return $null
    }
    try {
        $RawVersion = (& $Npm --version 2>$null).Trim()
        if ($LASTEXITCODE -ne 0 -or
            $RawVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$') {
            return $null
        }
        $Major = [int]($RawVersion.Split(".")[0])
        if (@(9, 10, 11) -notcontains $Major) {
            return $null
        }
        return [pscustomobject]@{
            FilePath = $Npm
            Version = $RawVersion
        }
    } catch {
        return $null
    }
}

function Get-KeiFileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $Stream = $null
    $Hasher = $null
    try {
        $Stream = [IO.File]::OpenRead($Path)
        $Hasher = [Security.Cryptography.SHA256]::Create()
        $Hash = $Hasher.ComputeHash($Stream)
        return (-join @($Hash | ForEach-Object { $_.ToString("x2") }))
    } finally {
        if ($null -ne $Hasher) {
            $Hasher.Dispose()
        }
        if ($null -ne $Stream) {
            $Stream.Dispose()
        }
    }
}

function Test-KeiLockIntegrity {
    param([string]$LockName)
    $ManifestPath = Join-Path $script:ProjectKeiRoot "requirements\lock-manifest.json"
    $LockPath = Join-Path $script:ProjectKeiRoot ("requirements\" + $LockName)
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
        return [pscustomobject]@{ Ok = $false; Message = "lock_or_manifest_missing"; Path = $LockPath }
    }
    try {
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $LockProperty = $Manifest.files.PSObject.Properties.Item($LockName)
        $Expected = if ($null -eq $LockProperty) { "" } else { [string]$LockProperty.Value }
        $Actual = Get-KeiFileSha256 -Path $LockPath
        if ([string]::IsNullOrWhiteSpace($Expected) -or $Expected.ToLowerInvariant() -ne $Actual) {
            return [pscustomobject]@{ Ok = $false; Message = "lock_checksum_mismatch"; Path = $LockPath }
        }
        return [pscustomobject]@{ Ok = $true; Message = $Actual; Path = $LockPath }
    } catch {
        return [pscustomobject]@{ Ok = $false; Message = "lock_manifest_invalid"; Path = $LockPath }
    }
}

function Test-KeiPortInUse {
    param([int]$Port)
    try {
        $Listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
        return @($Listeners | Where-Object { $_.Port -eq $Port }).Count -gt 0
    } catch {
        try {
            $Listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
            return $null -ne $Listener
        } catch {
            return $false
        }
    }
}

function Get-KeiPowerShellExecutable {
    $Current = (Get-Process -Id $PID).Path
    if (-not [string]::IsNullOrWhiteSpace($Current)) {
        return $Current
    }
    return "powershell.exe"
}

function Start-KeiPowerShellWindow {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $Executable = Get-KeiPowerShellExecutable
    $ArgumentList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$ScriptPath`"")
    foreach ($Argument in $Arguments) {
        $ArgumentList += "`"$Argument`""
    }
    Start-Process -FilePath $Executable -ArgumentList ($ArgumentList -join " ") -WorkingDirectory $WorkingDirectory
}
