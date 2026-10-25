# Lance l'assistant operateur sur le reseau du groupe.
# A lancer sur le Wi-Fi RESILIENCE-G15, PC branche, Ollama demarre.
#   powershell -ExecutionPolicy Bypass -File .\lancer-assistant.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ip     = "192.168.137.149"     # adresse de ce PC sur RESILIENCE-G15 (a changer si ipconfig en donne une autre)
$port   = 8100
$ollama = "http://${ip}:11434"

Write-Host "1/3 Verification de l'adresse du PC..."
$current = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty IPAddress
if ($current -ne $ip) {
    Write-Host "ERREUR : l'adresse Wi-Fi est '$current', pas '$ip'." -ForegroundColor Red
    Write-Host "  - Si elle commence par 10.60 : tu es sur le Wi-Fi du campus. Connecte-toi a RESILIENCE-G15."
    Write-Host "  - Si elle commence par 192.168.137 mais differente : modifie la ligne `$ip en haut de ce script, et OLLAMA_HOST (voir le guide)."
    exit 1
}

Write-Host "2/3 Verification d'Ollama sur $ollama ..."
try {
    $names = (Invoke-RestMethod "$ollama/api/tags" -TimeoutSec 5).models | ForEach-Object { $_.name }
} catch {
    Write-Host "ERREUR : Ollama ne repond pas. Quitte-le (icone du lama, Quit Ollama), puis relance-le depuis le menu Demarrer." -ForegroundColor Red
    exit 1
}
foreach ($needed in @("qwen2.5:3b", "nomic-embed-text")) {
    if (-not ($names | Where-Object { $_ -like "$needed*" })) {
        Write-Host "ERREUR : le modele '$needed' est absent. Modeles presents : $($names -join ', ')" -ForegroundColor Red
        exit 1
    }
}
Write-Host "   Ollama OK : $($names -join ', ')" -ForegroundColor Green

Write-Host "3/3 Demarrage de l'assistant sur http://${ip}:${port}  (Ctrl+C pour arreter)"
Write-Host "   L'indexation des documents prend 10 a 30 s : attends 'Uvicorn running' avant d'ouvrir la page."
$env:OLLAMA_URL = $ollama
& .\.venv\Scripts\python.exe -m uvicorn app:app --host $ip --port $port
