@echo off
setlocal
title Batch Layouti (DwgLayoutCreator)

REM GUI za batch generiranje AutoCAD layouta (DwgLayoutCreator/batch/batch_gui.py).
REM Alat zivi u zasebnom DwgLayoutCreator repou (treba lokalni AutoCAD + buildani
REM LayoutCreatorCore.dll), pa launcher gadja LOKALNI clone tog repoa.

REM === Prilagodi jednom svojoj instalaciji ===
set "REPO=C:\Users\Korisnik\Documents\SOFTWARE\DwgLayoutCreator"
REM ===========================================

if not exist "%REPO%\batch\batch_gui.py" (
  echo GRESKA: ne postoji "%REPO%\batch\batch_gui.py"
  echo Ispravi REPO putanju na vrhu ove .bat datoteke.
  echo.
  pause
  exit /b 1
)

REM pythonw = GUI bez konzolnog prozora; start "" da se .bat odmah zatvori.
start "" pythonw "%REPO%\batch\batch_gui.py"
