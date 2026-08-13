@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto :err
py -m PyInstaller --noconfirm --clean --onefile --windowed --add-data "cty.dat;." --name "DA6IT.de-Wavelog-Offline-Logger" app.py
if errorlevel 1 goto :err
echo.
echo Fertig: dist\DA6IT.de-Wavelog-Offline-Logger.exe
pause
exit /b 0
:err
echo Build fehlgeschlagen.
pause
exit /b 1
