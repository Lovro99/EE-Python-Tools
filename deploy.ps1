# deploy.ps1 - objavi STABILNU verziju alata kolegama (network share)
#
# Objavljuje se uvijek ono sto je na GitHubu u glavnoj grani (origin/master),
# a NE trenutno stanje mape - testne grane i lokalne izmjene nikad ne idu
# kolegama. Uz alate se zapise VERSION.json (commit + verzije alata) koji
# launcher kod kolega prikazuje.
#
# Pokretanje: gumb "Objavi kolegama" u EE Alati launcheru, ili
#   .\deploy.ps1            objavi
#   .\deploy.ps1 -WhatIf    samo prikazi sto bi se kopiralo/obrisalo
#
# NAPOMENA: datoteka je namjerno samo ASCII (Windows PowerShell 5.1).

param(
    [switch]$WhatIf,
    [string]$Grana = "master"
)

# "Continue": u PS 5.1 "Stop" + git na stderr baca gresku; provjeravamo $LASTEXITCODE
$ErrorActionPreference = "Continue"
$repo = $PSScriptRoot
$dest = "\\192.168.30.150\Projekti\LUKA SOFTWARE\Aplikacije\AutoLisp\python"

if (-not (Test-Path $dest)) {
    Write-Host "GRESKA: Server nije dostupan: $dest" -ForegroundColor Red
    exit 1
}

Write-Host "Dohvacam najnovije s GitHuba..." -ForegroundColor Cyan
git -C $repo fetch --prune origin
if ($LASTEXITCODE -ne 0) { Write-Host "GRESKA: git fetch nije uspio." -ForegroundColor Red; exit 1 }

$rev = "origin/$Grana"
$info = git -C $repo log -1 --format="%h  %ci  %s" $rev
if ($LASTEXITCODE -ne 0) { Write-Host "GRESKA: ne postoji $rev" -ForegroundColor Red; exit 1 }
Write-Host "Objavljujem: $rev  ->  $info"

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# cista kopija glavne grane u privremenoj mapi
$tmp = Join-Path $env:TEMP ("ee-alati-deploy-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
git -C $repo worktree add --quiet --detach $tmp $rev
if ($LASTEXITCODE -ne 0) { Write-Host "GRESKA: git worktree add nije uspio." -ForegroundColor Red; exit 1 }

try {
    & $python (Join-Path $repo "launcher_git.py") verzija-json --repo $repo --rev $rev --izlaz (Join-Path $tmp "VERSION.json")
    if ($LASTEXITCODE -ne 0) { throw "Ne mogu napraviti VERSION.json" }

    # /MIR: share = tocna kopija glavne grane. Iskljucene datoteke se na shareu
    # ne diraju (npr. sklopke_config.json koji alati uce kod kolega).
    $flags = @("/MIR", "/XD", "__pycache__", ".git", ".grane", ".venv", "bin", "obj", ".vs",
               "/XF", ".git", "*.pyc", "*.pyo", "sklopke_config.json",
               "/NFL", "/NDL", "/NP")
    if ($WhatIf) {
        $flags += "/L"
        Write-Host "(WhatIf - nema stvarnih promjena)" -ForegroundColor Yellow
    }
    robocopy $tmp $dest @flags
    if ($LASTEXITCODE -ge 8) { throw "robocopy nije uspio (kod $LASTEXITCODE)" }

    if ($WhatIf) {
        Write-Host "WhatIf gotov - nista kopirano." -ForegroundColor Yellow
    } else {
        Write-Host "Objavljeno kolegama -> $dest" -ForegroundColor Green
    }
}
catch {
    Write-Host "GRESKA: $_" -ForegroundColor Red
    exit 1
}
finally {
    git -C $repo worktree remove --force $tmp
}
