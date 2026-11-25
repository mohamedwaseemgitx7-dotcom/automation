# Stops the Local AI WhatsApp Agent on this laptop. The WhatsApp link is KEPT (encrypted session on disk),
# so the next .\start-agent.ps1 reconnects without a new QR. Add -Ollama to also stop the local AI.
param([switch]$Ollama)

function Stop-Port([int]$port, [string]$name) {
    $pids = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { Write-Host "$name not running"; return }
    foreach ($p in $pids) { Stop-Process -Id $p -Force -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "$name stopped" -ForegroundColor Green
}

Stop-Port 8100 'Agent backend + dashboard'
Stop-Port 8200 'WhatsApp bridge'
if ($Ollama) { Stop-Port 11434 'Ollama' } else { Write-Host 'Ollama left running (use -Ollama to stop it too)' }
