# setup.ps1 - instalacija EE Alati (pokrece se preko "Instaliraj EE Alati.bat")
#
# Sam prepozna gdje je pokrenut:
#   - iz git repoa (tvoje racunalo)   -> RAZVOJ:   .venv u repou, precac na launcher u repou
#   - s network sharea (kolege)       -> STABILNO: venv u %LOCALAPPDATA%\EE-Alati,
#                                                  precac na launcher na shareu
# Napravi JEDAN precac "EE Alati" (Desktop + Start meni) i ponudi brisanje
# starih precaca na pojedinacne alate.
#
# Pokretanje: dvoklik na "Instaliraj EE Alati.bat"
#   ili:      powershell -ExecutionPolicy Bypass -File setup.ps1 [-Kolega]
# Sigurno ga je pokrenuti vise puta (npr. za popravak precaca ili venva).
#
# NAPOMENA: datoteka je namjerno samo ASCII (Windows PowerShell 5.1 bez BOM-a
# krivo cita UTF-8 znakove).

param(
    [switch]$Kolega   # prisili STABILNO (kolege) i kad je pokrenuto iz repoa
)

# "Continue": u PS 5.1 "Stop" + git na stderr baca gresku; provjeravamo $LASTEXITCODE
$ErrorActionPreference = "Continue"
$dir = $PSScriptRoot

function Greska($poruka) {
    Write-Host ""
    Write-Host "GRESKA: $poruka" -ForegroundColor Red
    exit 1
}

function Nadji-Python {
    # py launcher prvi (standardna python.org instalacija), pa python s PATH-a.
    # Microsoftov "python" iz WindowsApps je samo precac na Store - ne vrijedi.
    $kandidati = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $kandidati += ,@("py", "-3") }
    if (Get-Command python -ErrorAction SilentlyContinue) { $kandidati += ,@("python") }
    foreach ($k in $kandidati) {
        try {
            $argumenti = @()
            if ($k.Count -gt 1) { $argumenti = $k[1..($k.Count - 1)] }
            $exe = & $k[0] @argumenti -c "import sys, tkinter; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe -and $exe -notmatch "WindowsApps") { return $exe.Trim() }
        } catch { }
    }
    return $null
}

$razvoj = (-not $Kolega) -and (Test-Path (Join-Path $dir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)

Write-Host "=== EE Alati - instalacija ===" -ForegroundColor Cyan
if ($razvoj) {
    Write-Host "Nacin: RAZVOJ (git repo: $dir)"
} else {
    Write-Host "Nacin: STABILNO (alati s: $dir)"
}
Write-Host ""

# -- 1. Python ------------------------------------------------------------------
$python = Nadji-Python
if (-not $python) {
    Greska ("Python nije pronaden (ili nema tkinter).`n" +
            "Instaliraj Python 3 s https://www.python.org/downloads/ " +
            "(oznaci 'Add python.exe to PATH' i 'tcl/tk and IDLE') pa ponovno pokreni.")
}
Write-Host "Python: $python"

# -- 2. git (samo RAZVOJ) --------------------------------------------------------
if (Test-Path (Join-Path $dir ".git")) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Greska ("Git nije instaliran. Instaliraj ga (npr. 'winget install Git.Git' " +
                "ili https://git-scm.com/download/win) pa ponovno pokreni.")
    }
}
if ($razvoj) {
    $up = git -C $dir rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "UPOZORENJE: trenutna grana nije povezana s GitHubom - launcher nece moci azurirati." -ForegroundColor Yellow
    } else {
        Write-Host "Provjeravam vezu s GitHubom (moze traziti prijavu samo prvi put)..."
        git -C $dir fetch origin
        if ($LASTEXITCODE -ne 0) {
            Write-Host "UPOZORENJE: git fetch nije uspio - provjeri mrezu i prijavu na GitHub." -ForegroundColor Yellow
        } else {
            Write-Host "GitHub OK (grana prati $up)." -ForegroundColor Green
        }
    }
}

# -- 3. venv + paketi -------------------------------------------------------------
if ($razvoj) {
    $venv = Join-Path $dir ".venv"
} else {
    $venv = Join-Path $env:LOCALAPPDATA "EE-Alati\venv"
}
$venvPython = Join-Path $venv "Scripts\python.exe"
$venvPythonw = Join-Path $venv "Scripts\pythonw.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Radim virtualno okruzenje: $venv"
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { Greska "Ne mogu napraviti venv u $venv" }
}

$req = Join-Path $dir "requirements.txt"
Write-Host "Instaliram Python pakete (prvi put moze potrajati nekoliko minuta)..."
& $venvPython -m pip install --disable-pip-version-check -q --upgrade pip
& $venvPython -m pip install --disable-pip-version-check -r $req
if ($LASTEXITCODE -ne 0) { Greska "pip install nije uspio - pogledaj poruke iznad." }
# isti hash koji launcher provjerava (launcher_git.REQ_HASH_FILE) - da ne instalira ponovno
$hash = (Get-FileHash -Algorithm SHA256 $req).Hash.ToLower()
Set-Content -Path (Join-Path $venv "ee_requirements.sha256") -Value $hash -NoNewline -Encoding ASCII
Write-Host "Paketi OK." -ForegroundColor Green

# -- 4. jedan precac ------------------------------------------------------------------
$launcher = Join-Path $dir "launcher.py"
$ikona = Join-Path $dir "ee_alati.ico"
$ws = New-Object -ComObject WScript.Shell
$mape = @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))
foreach ($mapa in $mape) {
    $lnk = $ws.CreateShortcut((Join-Path $mapa "EE Alati.lnk"))
    $lnk.TargetPath = $venvPythonw
    $lnk.Arguments = "`"$launcher`""
    $lnk.WorkingDirectory = $dir
    if (Test-Path $ikona) { $lnk.IconLocation = "$ikona,0" }
    $lnk.Description = "EE Alati - svi Python alati na jednom mjestu"
    $lnk.Save()
}
Write-Host "Precac 'EE Alati' napravljen na Desktopu i u Start meniju." -ForegroundColor Green

# -- 5. stari precaci na pojedinacne alate ------------------------------------------------
$stara = @(
    "Excel u Word", "Excel u PDF", "Crtanje Kabela", "Print", "Excel Terminal",
    "Pretraga", "Scrape Excel Podaci", "Scrape Word", "PDF Pozicija", "Excel PDF Placer",
    "Scrape Excel", "Duzina Kabela", "PDF Form Filler", "PrintOrganizer", "hepaFormFiller",
    "PVSOL u Excel", "Sync Properties", "Sync DWG Fast", "Razvodne Ploce", "Batch Layouti"
)
$desktop = [Environment]::GetFolderPath("Desktop")
$zaBrisanje = @()
foreach ($ime in $stara) {
    $p = Join-Path $desktop "$ime.lnk"
    if (Test-Path $p) {
        $s = $ws.CreateShortcut($p)
        $cilj = "$($s.TargetPath) $($s.Arguments) $($s.WorkingDirectory)"
        # brisi samo precace koji stvarno gadjaju ove alate
        if ($cilj -match "python|launchers|AutoLisp") { $zaBrisanje += $p }
    }
}
if ($zaBrisanje.Count -gt 0) {
    Write-Host ""
    Write-Host "Pronadeni stari precaci na pojedinacne alate:"
    $zaBrisanje | ForEach-Object { Write-Host "  $(Split-Path $_ -Leaf)" }
    $odg = Read-Host "Obrisati ih? Svi alati su sada u 'EE Alati'. (D/N)"
    if ($odg -match "^[DdYy]") {
        $zaBrisanje | ForEach-Object { Remove-Item $_ -Force }
        Write-Host "Stari precaci obrisani." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Gotovo! Pokreni 'EE Alati' s Desktopa (ili ga pinnaj na taskbar)." -ForegroundColor Cyan
