@echo off
setlocal
set "LAESIM_ROOT=%~dp0..\.."
set "PYTHONPATH=%LAESIM_ROOT%\SceneGen\python;%LAESIM_ROOT%\RadioSim\python;%LAESIM_ROOT%\Examples\RadioMapNav\python"

if exist "%LAESIM_ROOT%\.venv-radio\Scripts\python.exe" (
  set "WCF_PYTHON=%LAESIM_ROOT%\.venv-radio\Scripts\python.exe"
) else if exist "%LAESIM_ROOT%\.venv\Scripts\python.exe" (
  set "WCF_PYTHON=%LAESIM_ROOT%\.venv\Scripts\python.exe"
) else (
  set "WCF_PYTHON=py"
)

cd /d "%LAESIM_ROOT%"
echo Starting LAESim scene and radio tools...
"%WCF_PYTHON%" -m laesim_scene.web_app
if errorlevel 1 (
  echo.
  echo Visualizer failed to start. Verify Python 3.10+, Sionna RT, and the project environment.
  pause
)
endlocal
