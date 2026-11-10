[CmdletBinding()]
param(
    [string]$Version = '0.3.1',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'MultisimNativeMCP'),
    [string]$Source,
    [ValidateSet('codex','dsh','none')][string]$Client = 'codex',
    [string]$Profile = 'desktop',
    [string]$ConfigPath,
    [string]$MultisimPath,
    [switch]$Force,
    [switch]$SkipDoctor
)
$ErrorActionPreference = 'Stop'
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$toolsDirectory = Join-Path $InstallRoot 'tools'
$binDirectory = Join-Path $InstallRoot 'bin'
$launcher = Join-Path $binDirectory 'multisim-native-mcp.exe'
$pathArguments = @()
if ($MultisimPath) { $pathArguments = @('--multisim-path',$MultisimPath) }
$reuseInstallation = $false
if (-not $Force -and -not $Source -and -not ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'src\multisim_native_mcp\__init__.py'))) -and (Test-Path -LiteralPath $launcher)) {
    try {
        $existingVersion = & $launcher --version 2>$null
        $format = if ($Client -eq 'dsh') { 'dsh' } else { 'json' }
        if ($LASTEXITCODE -eq 0 -and $existingVersion.Trim() -eq $Version) {
            $preview = & $launcher config --format $format @pathArguments 2>$null
            if ($LASTEXITCODE -eq 0) {
                $health = & $launcher doctor @pathArguments 2>$null
                if ($LASTEXITCODE -eq 0) { $reuseInstallation = ($health | ConvertFrom-Json).ready -eq $true }
            }
        }
    } catch { $reuseInstallation = $false }
}
New-Item -ItemType Directory -Path $toolsDirectory,$binDirectory -Force | Out-Null
$previousToolDir = $env:UV_TOOL_DIR
$previousBinDir = $env:UV_TOOL_BIN_DIR
$previousInstallDir = $env:UV_INSTALL_DIR
$previousModifyPath = $env:UV_NO_MODIFY_PATH
try {
    if (-not $reuseInstallation) {
        $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
        if ($uvCommand) { $uvExecutable = $uvCommand.Source }
        else {
            $env:UV_INSTALL_DIR = $toolsDirectory
            $env:UV_NO_MODIFY_PATH = '1'
            $bootstrapFile = Join-Path $toolsDirectory 'install-uv.ps1'
            Invoke-WebRequest 'https://astral.sh/uv/install.ps1' -OutFile $bootstrapFile -UseBasicParsing
            & (Get-Command powershell.exe -ErrorAction Stop).Source -NoProfile -ExecutionPolicy Bypass -File $bootstrapFile
            if ($LASTEXITCODE -ne 0) { throw 'uv installation failed.' }
            $uvExecutable = Join-Path $toolsDirectory 'uv.exe'
        }
        $environmentRoot = Join-Path (Join-Path $toolsDirectory 'environments') ('install-' + [guid]::NewGuid().ToString('N'))
        $env:UV_TOOL_DIR = $environmentRoot
        $env:UV_TOOL_BIN_DIR = $binDirectory
        if (-not $Source) {
            if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'src\multisim_native_mcp\__init__.py'))) { $Source = $PSScriptRoot }
            else { $Source = "https://github.com/y-wi/multisim-native-mcp/releases/download/v$Version/multisim_native_mcp-$Version-py3-none-any.whl" }
        }
        & $uvExecutable tool install --force --python cpython-3.12-windows-x86-none $Source
        if ($LASTEXITCODE -ne 0) { throw 'MCP package installation failed.' }
        if (-not (Test-Path -LiteralPath $launcher)) { throw 'MCP launcher was not created.' }
    }
    if (-not $SkipDoctor) {
        $doctorArguments = @('doctor') + $pathArguments
        if ($Client -eq 'dsh') { $doctorArguments += '--connect' }
        & $launcher @doctorArguments
        if ($LASTEXITCODE -ne 0) { throw 'MCP runtime check failed. See the doctor report above.' }
    }
    if ($Client -ne 'none') {
        $configArguments = @('configure','--client',$Client) + $pathArguments
        if ($Client -eq 'dsh') { $configArguments += @('--profile',$Profile) }
        if ($ConfigPath) { $configArguments += @('--config-path',$ConfigPath) }
        & $launcher @configArguments
        if ($LASTEXITCODE -ne 0) { throw "$Client configuration failed." }
    }
    Write-Host "Installed: $launcher"
    if ($Client -eq 'codex') { Write-Host 'Restart Codex to load Multisim Native MCP.' }
    elseif ($Client -eq 'dsh') { Write-Host "DSH profile '$Profile' reloads the MCP connection automatically." }
    else { & $launcher config @pathArguments }
}
finally {
    $env:UV_TOOL_DIR = $previousToolDir
    $env:UV_TOOL_BIN_DIR = $previousBinDir
    $env:UV_INSTALL_DIR = $previousInstallDir
    $env:UV_NO_MODIFY_PATH = $previousModifyPath
}
