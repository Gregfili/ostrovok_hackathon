# Поднять шлюз, агентов и страницу. Остановка: Ctrl+C.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Нет .venv. Из корня: python -m venv .venv"
}
& $Python (Join-Path $Root "run.py")
exit $LASTEXITCODE
