@echo off
setlocal

set "UBT="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ResolveUnrealBuildToolPath.ps1" -ProjectDir "%~dp0."`) do set "UBT=%%i"

if "%UBT%"=="" (
    echo Could not locate UnrealBuildTool.exe
    echo Set UNREAL_ENGINE_ROOT, UE_ROOT, or UE4_ROOT, or install UE in a discoverable location.
    exit /b 1
)

for %%i in ("%UBT%") do set "UBT_DIR=%%~dpi"
for %%i in ("%UBT_DIR%..\..\..") do set "ENGINE_ROOT=%%~fi"

if not exist "%ENGINE_ROOT%\Engine\Build\BatchFiles\Build.bat" (
    echo Could not locate Build.bat under %ENGINE_ROOT%
    exit /b 1
)

call "%~dp0GenerateProjectFiles.bat"
if errorlevel 1 exit /b 1

call "%ENGINE_ROOT%\Engine\Build\BatchFiles\Build.bat" BlocksEditor Win64 Development "%~dp0Blocks.uproject" -WaitMutex -FromMsBuild
