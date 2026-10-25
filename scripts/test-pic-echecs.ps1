# Test local : envoie N mauvaises connexions (compte de test) a NOTRE plateforme,
# pour verifier que le detecteur reagit. Usage : .\scripts\test-pic-echecs.ps1 [-Count 30]
param(
    [int]$Count = 30,
    [string]$Url = "http://127.0.0.1:8081/login"
)

# Les \" sont necessaires : PowerShell 5.1 retire les guillemets d'un texte passe a curl.exe
$body = '{\"username\":\"alice\",\"password\":\"mauvais\"}'
$codes = @{}
for ($i = 1; $i -le $Count; $i++) {
    $code = & curl.exe -s -o NUL -w "%{http_code}" -X POST $Url -H "Content-Type: application/json" -d $body
    $codes[$code] = 1 + [int]$codes[$code]
}
Write-Host "Termine : $Count tentatives envoyees. Codes de reponse :"
$codes.GetEnumerator() | ForEach-Object { Write-Host ("  HTTP {0} : {1}" -f $_.Key, $_.Value) }
