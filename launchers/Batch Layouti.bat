@echo off
setlocal
title Batch Layouti (DwgLayoutCreator)

REM Batch generiranje AutoCAD layouta preko vise DWG projekata (headless).
REM Za razliku od ostalih launchera koristi 'python' (ne pythonw) jer alat ima
REM konzolni live-progress ispis i sazetak; alat zivi u zasebnom DwgLayoutCreator
REM repou, ne na network shareu.

REM === Prilagodi jednom svojoj instalaciji ===
REM Lokalni clone DwgLayoutCreator repoa (gdje je batch\batch_layouts.py):
set "REPO=C:\Users\Korisnik\Documents\SOFTWARE\DwgLayoutCreator"
REM Config s putanjama alata (accoreconsole, DLL, sastavnica) i popisom projekata:
set "CONFIG=%REPO%\batch\config.json"
REM ===========================================

if not exist "%REPO%\batch\batch_layouts.py" (
  echo GRESKA: ne postoji "%REPO%\batch\batch_layouts.py"
  echo Ispravi REPO putanju na vrhu ove .bat datoteke.
  echo.
  pause
  exit /b 1
)

REM %* prosljedjuje dodatne argumente (npr. --dry-run ili --jobs 3).
python "%REPO%\batch\batch_layouts.py" --config "%CONFIG%" %*

echo.
echo (zavrseno - pritisni tipku za izlaz)
pause >nul
