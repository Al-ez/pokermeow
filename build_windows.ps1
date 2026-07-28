[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$distRoot = Join-Path $projectRoot "dist"
$workRoot = Join-Path $projectRoot "build"
$releaseRoot = Join-Path $distRoot "PokerMeow-Windows"
$archivePath = Join-Path $distRoot "PokerMeow-Windows.zip"

$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    $pythonExecutable = $launcher.Source
    $pythonPrefix = @("-3")
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python 3 was not found. Install it from https://www.python.org/downloads/windows/ and enable 'Add Python to PATH'."
    }
    $pythonExecutable = $python.Source
    $pythonPrefix = @()
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $script:pythonExecutable @script:pythonPrefix @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
}

Set-Location $projectRoot

if (-not $SkipInstall) {
    Invoke-Python -m pip install -r requirements-gui.txt -r requirements-build.txt
}

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
if (Test-Path $releaseRoot) { Remove-Item -LiteralPath $releaseRoot -Recurse -Force }
if (Test-Path $archivePath) { Remove-Item -LiteralPath $archivePath -Force }

$commonArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--distpath", $releaseRoot,
    "--workpath", $workRoot
)

Invoke-Python -m PyInstaller @commonArgs --windowed --name PokerMeow gui.py
Invoke-Python -m PyInstaller @commonArgs --console --name PokerMeowServer server.py

Copy-Item -LiteralPath (Join-Path $projectRoot "release\HOW_TO_PLAY.txt") -Destination $releaseRoot
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $archivePath -CompressionLevel Optimal

Write-Host ""
Write-Host "Build complete: $archivePath" -ForegroundColor Green
