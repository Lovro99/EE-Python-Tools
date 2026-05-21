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

$flags = "/MIR /XD __pycache__ .git bin obj .vs /XF *.pyc *.pyo /NFL /NDL"
if ($WhatIf) { $flags += " /L" }

Write-Host "Deploying: $src -> $dest" -ForegroundColor Cyan
if ($WhatIf) { Write-Host "(WhatIf - nema stvarnih promjena)" -ForegroundColor Yellow }

robocopy $src $dest /MIR /XD __pycache__ .git bin obj .vs /XF *.pyc *.pyo /NFL /NDL

if ($WhatIf) {
    Write-Host "WhatIf gotov – nista kopirano." -ForegroundColor Yellow
} else {
    Write-Host "Deploy gotov -> $dest" -ForegroundColor Green
}
