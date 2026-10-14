# deploy.ps1
# Kopira Python alate na server (network share) koristeci robocopy.
# Pokretanje: .\deploy.ps1
# Opcionalno: .\deploy.ps1 -WhatIf  (prikazuje sto bi kopiralo, bez promjena)

param(
    [switch]$WhatIf
)

$src  = $PSScriptRoot
$dest = "\\192.168.30.150\Projekti\LUKA SOFTWARE\Aplikacije\AutoLisp\python"

if (-not (Test-Path $dest)) {
    Write-Host "GRESKA: Server nije dostupan: $dest" -ForegroundColor Red
    exit 1
}

# Argumenti kao NIZ - robocopy ih tada dobiva kao zasebne argumente.
# /L = samo popis (nista se ne kopira ni BRISE); bez njega /MIR brise na
# serveru sve sto nema u lokalnoj mapi.
$flags = @("/MIR", "/XD", "__pycache__", ".git", "bin", "obj", ".vs",
           "/XF", "*.pyc", "*.pyo")
if ($WhatIf) {
    $flags += "/L"               # pregled: ispisi svaku datoteku (i "*EXTRA" = brisalo bi se)
} else {
    $flags += @("/NFL", "/NDL")  # pravi deploy: samo sazetak
}

Write-Host "Deploying: $src -> $dest" -ForegroundColor Cyan
if ($WhatIf) { Write-Host "(WhatIf - nema stvarnih promjena)" -ForegroundColor Yellow }

robocopy $src $dest @flags
# robocopy: 0-7 = uspjeh (razne kombinacije kopirano/visak), >= 8 = greska
if ($LASTEXITCODE -ge 8) {
    Write-Host "GRESKA: robocopy exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

if ($WhatIf) {
    Write-Host "WhatIf gotov – nista kopirano." -ForegroundColor Yellow
} else {
    Write-Host "Deploy gotov -> $dest" -ForegroundColor Green
}
