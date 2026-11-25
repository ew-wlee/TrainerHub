#Requires -Version 5.1
$ErrorActionPreference = "Stop"

Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> Installing dependencies (uv)" -ForegroundColor Cyan
uv sync --extra dev

Write-Host "==> Running tests" -ForegroundColor Cyan
uv run pytest -q

Write-Host "==> Building TrainerHub.exe" -ForegroundColor Cyan
uv run pyinstaller packaging/trainerhub.spec --noconfirm --distpath dist --workpath build

if (-not (Test-Path "dist/TrainerHub.exe")) {
    throw "Build failed: dist/TrainerHub.exe not found"
}

$size = [math]::Round((Get-Item "dist/TrainerHub.exe").Length / 1MB, 1)
Write-Host "==> Done: dist\TrainerHub.exe ($size MB)" -ForegroundColor Green
