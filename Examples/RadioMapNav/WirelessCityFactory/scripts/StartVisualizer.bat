@echo off
setlocal
set "WCF_ROOT=%~dp0.."
set "PYTHONPATH=%WCF_ROOT%\src"

if exist "%WCF_ROOT%\.venv-sionna310\Scripts\python.exe" (
  set "WCF_PYTHON=%WCF_ROOT%\.venv-sionna310\Scripts\python.exe"
) else if exist "%WCF_ROOT%\.venv\Scripts\python.exe" (
  set "WCF_PYTHON=%WCF_ROOT%\.venv\Scripts\python.exe"
) else (
  set "WCF_PYTHON=py"
)

echo Starting Wireless City Factory visualizer...
"%WCF_PYTHON%" -m wireless_city_factory.web_app
if errorlevel 1 (
  echo.
  echo Visualizer failed to start. Verify Python 3.10+, Sionna RT, and the project environment.
  pause
)
endlocal
