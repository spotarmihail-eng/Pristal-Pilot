@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install Python 3.10+ from python.org and tick "Add to PATH".
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
python -m PyInstaller --noconfirm --clean --windowed --name Pristal-Pilot --add-data "assets;assets" main.py
if errorlevel 1 goto fail
echo.
echo EXE ready: dist\Pristal-Pilot\Pristal-Pilot.exe
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto noinno
"%ISCC%" installer.iss
if errorlevel 1 goto fail
echo Installer ready: dist\Pristal-Pilot-Setup.exe
goto end
:noinno
echo Inno Setup 6 not found - installer skipped. EXE above is ready to use.
goto end
:fail
echo BUILD FAILED
:end
pause
