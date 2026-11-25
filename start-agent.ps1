# One command to start the Local AI WhatsApp Agent on this laptop:
#   1. Ollama (local AI) on 127.0.0.1:11434, models from D:\tools\ollama\models
#   2. Backend + dashboard on http://127.0.0.1:8100 (it reconnects WhatsApp from the saved session by itself)
#   3. Loads the AI models so the first WhatsApp reply is fast, then opens the dashboard.
# Stop everything with .\stop-agent.ps1
param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Test-Port([int]$port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
function Wait-Url([string]$url, [int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try { Invoke-RestMethod $url -TimeoutSec 3 | Out-Null; return $true } catch { Start-Sleep 1 }
    }
    return $false
}

# --- 1. Ollama ---
if (Test-Port 11434) {
    Write-Host "[1/3] Ollama already running" -ForegroundColor Green
} else {
    Write-Host "[1/3] Starting Ollama..."
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (-not (Test-Path $ollama)) { throw "Ollama not found at $ollama" }
    $env:OLLAMA_MODELS = 'D:\tools\ollama\models'
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_KEEP_ALIVE = '60m'
    $env:OLLAMA_MAX_LOADED_MODELS = '2'
    Start-Process $ollama -ArgumentList 'serve' -WindowStyle Hidden `
        -RedirectStandardError 'D:\tools\ollama\serve.log' -RedirectStandardOutput 'D:\tools\ollama\serve.out.log'
    if (-not (Wait-Url 'http://127.0.0.1:11434/api/version' 60)) { throw "Ollama did not start - see D:\tools\ollama\serve.log" }
    Write-Host "      Ollama ready" -ForegroundColor Green
}

# --- 2. Backend + dashboard (+ WhatsApp bridge restored automatically) ---
if (Test-Port 8100) {
    Write-Host "[2/3] Agent already running on port 8100" -ForegroundColor Green
} else {
    Write-Host "[2/3] Starting agent backend..."
    $py = Join-Path $root 'backend\.venv\Scripts\python.exe'
    $log = Join-Path $root 'storage\backend.log'
    Start-Process $py -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8100' `
        -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden `
        -RedirectStandardError $log -RedirectStandardOutput (Join-Path $root 'storage\backend.out.log')
    if (-not (Wait-Url 'http://127.0.0.1:8100/api/live' 90)) { throw "Backend did not start - see $log" }
    Write-Host "      Agent ready" -ForegroundColor Green
}

# --- 3. Warm up the models (first load takes 15-60 s; after this replies take a few seconds) ---
Write-Host "[3/3] Loading AI models into memory (up to 1 minute)..."
$chat = 'qwen3:4b-instruct'
try {
    Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -TimeoutSec 180 -ContentType 'application/json' `
        -Body (@{ model = $chat; prompt = 'hi'; stream = $false; keep_alive = '60m'; options = @{ num_predict = 1 } } | ConvertTo-Json) | Out-Null
    Invoke-RestMethod 'http://127.0.0.1:11434/api/embed' -Method Post -TimeoutSec 180 -ContentType 'application/json' `
        -Body (@{ model = 'bge-m3'; input = 'hi'; keep_alive = '60m'; options = @{ num_gpu = 0 } } | ConvertTo-Json) | Out-Null
    Write-Host "      Models loaded" -ForegroundColor Green
} catch { Write-Host "      Warm-up skipped: $($_.Exception.Message)" -ForegroundColor Yellow }

# --- Status ---
Start-Sleep 5   # give WhatsApp a moment to reconnect
try { $h = Invoke-RestMethod 'http://127.0.0.1:8100/api/health' -TimeoutSec 10 } catch { $h = $_.ErrorDetails.Message | ConvertFrom-Json }
Write-Host ""
Write-Host "Status: $($h.status) | database: $($h.database) | AI: $($h.llm) | WhatsApp: $($h.whatsapp) | disk: $($h.disk)"
if ($h.whatsapp -eq 'down') { Write-Host "WhatsApp is still connecting - check the WhatsApp page in a minute." -ForegroundColor Yellow }
Write-Host "Dashboard: http://127.0.0.1:8100   (stop with .\stop-agent.ps1)" -ForegroundColor Cyan
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8100' }
