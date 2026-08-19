$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerRoot = Split-Path -Parent $ScriptRoot
$ProjectRoot = Split-Path -Parent $ServerRoot
$DescriptorPath = Join-Path $ServerRoot "features\voice\providers\gpt_sovits\engine.json"
$LocalConfigPath = $env:GPT_SOVITS_LOCAL_CONFIG
if ([string]::IsNullOrWhiteSpace($LocalConfigPath)) {
    $LocalConfigPath = Join-Path $ServerRoot "data\gpt_sovits_engine.local.json"
}

function Stop-EngineLaunch([string]$Code, [string]$Message) {
    Write-Host "[GPT-SoVITS] status: failed ($Code)"
    Write-Host "[GPT-SoVITS] $Message"
    exit 1
}

function Resolve-FixedChild([string]$Root, [string]$Relative, [string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) {
        Stop-EngineLaunch "descriptor_invalid" "$Name must be a fixed relative path."
    }
    $Segments = $Relative -split '[\\/]'
    if ($Segments -contains "..") {
        Stop-EngineLaunch "descriptor_invalid" "$Name cannot escape the engine root."
    }
    $Candidate = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    $RootPrefix = $Root.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $Candidate.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-EngineLaunch "descriptor_invalid" "$Name cannot escape the engine root."
    }
    return $Candidate
}

if (-not (Test-Path -LiteralPath $DescriptorPath -PathType Leaf)) {
    Stop-EngineLaunch "descriptor_missing" "Project-owned engine descriptor is missing."
}
if (-not (Test-Path -LiteralPath $LocalConfigPath -PathType Leaf)) {
    Stop-EngineLaunch "local_config_missing" "Register an existing install or run the explicit acquisition command first."
}

try {
    $Descriptor = Get-Content -LiteralPath $DescriptorPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $LocalConfig = Get-Content -LiteralPath $LocalConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Stop-EngineLaunch "config_invalid" "Engine descriptor or local configuration is invalid."
}

if ($Descriptor.engine_id -ne "gpt-sovits-v2pro-nvidia50" -or $LocalConfig.engine_id -ne $Descriptor.engine_id) {
    Stop-EngineLaunch "engine_id_mismatch" "The local registration does not match the approved engine descriptor."
}
if ([string]::IsNullOrWhiteSpace([string]$LocalConfig.install_root)) {
    Stop-EngineLaunch "local_config_invalid" "The local registration has no install root."
}

$Root = [IO.Path]::GetFullPath([string]$LocalConfig.install_root)
$ProjectRootFull = [IO.Path]::GetFullPath($ProjectRoot)
$ProjectPrefix = $ProjectRootFull.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if ($Root.StartsWith($ProjectPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    Stop-EngineLaunch "install_root_invalid" "GPT-SoVITS must be installed outside the Project Kei repository."
}

$Python = Resolve-FixedChild $Root ([string]$Descriptor.launcher.python_relative) "Python entry"
$Api = Resolve-FixedChild $Root ([string]$Descriptor.launcher.api_relative) "API entry"
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    Stop-EngineLaunch "install_missing" "The registered engine root does not exist."
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf) -or -not (Test-Path -LiteralPath $Api -PathType Leaf)) {
    Stop-EngineLaunch "install_not_ready" "The registered engine is missing a fixed entry file."
}

$HostAddress = [string]$Descriptor.launcher.host
$Port = [int]$Descriptor.launcher.port
if ($HostAddress -ne "127.0.0.1" -or $Port -ne 9880) {
    Stop-EngineLaunch "descriptor_invalid" "The engine launcher is restricted to 127.0.0.1:9880."
}

chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
Write-Host "[GPT-SoVITS] install status: $($LocalConfig.install_status)"
Write-Host "[GPT-SoVITS] integrity status: $($LocalConfig.integrity_status)"
Write-Host "[GPT-SoVITS] API style: $($LocalConfig.api_style)"
Write-Host "[GPT-SoVITS] port: 9880"
Write-Host "[GPT-SoVITS] No download, dependency installation, model discovery, or remote script will run."

Set-Location -LiteralPath $Root
& $Python $Api -a "127.0.0.1" -p 9880
