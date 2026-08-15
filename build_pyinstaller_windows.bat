@echo off
setlocal
cd /d "%~dp0"
echo Dieser Kompatibilitaetsstarter verwendet den unterstuetzten Go-Bootstrap-Build.
echo Eine lokale pip-Installation ist nicht erforderlich.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-windows.ps1"
if errorlevel 1 goto :err
echo.
echo Build erfolgreich. Die versionierte EXE liegt im Ordner dist.
pause
exit /b 0
:err
echo Build fehlgeschlagen.
pause
exit /b 1
