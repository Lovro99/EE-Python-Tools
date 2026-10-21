@echo off
REM Instalacija EE Alati: Python paketi + JEDAN precac "EE Alati" (Desktop i Start meni).
REM Iz git repoa = razvojna verzija; s network sharea = stabilna verzija (kolege).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
