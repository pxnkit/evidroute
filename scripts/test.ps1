$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=evidroute --cov-report=term-missing
Push-Location apps\web
try {
    pnpm lint
    pnpm typecheck
    pnpm test
    pnpm build
}
finally {
    Pop-Location
}
