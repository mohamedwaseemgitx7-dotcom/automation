# Local AI WhatsApp Agent - starts the backend + built dashboard on http://127.0.0.1:8100 (this PC only)
Set-Location -LiteralPath "$PSScriptRoot\backend"
& "$PSScriptRoot\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8100
