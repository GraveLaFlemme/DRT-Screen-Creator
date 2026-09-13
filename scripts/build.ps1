param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$builder = Join-Path $projectRoot "scripts\build.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Environnement virtuel absent. Exécutez d’abord : python -m venv .venv"
}

& $python $builder --mode $Mode
$buildExitCode = $LASTEXITCODE

if ($buildExitCode -ne 0) {
    throw "La génération PyInstaller a échoué avec le code $buildExitCode."
}

Write-Host "Build $Mode terminé dans : $(Join-Path $projectRoot 'dist')"
