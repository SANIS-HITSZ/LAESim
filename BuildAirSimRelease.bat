@echo off
setlocal

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo Could not find vswhere.exe
    echo Please install Visual Studio 2019 or 2022 with C++ build tools.
    exit /b 1
)

set "VSINSTALL="
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%i"

if "%VSINSTALL%"=="" (
    echo Could not find a Visual Studio installation with C++ build tools.
    exit /b 1
)

if not exist "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" (
    echo Could not find VsDevCmd.bat under %VSINSTALL%
    exit /b 1
)

call "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" -arch=x64
if errorlevel 1 exit /b 1

if "%~1"=="" (
    call "%~dp0build.cmd" --Release
) else (
    call "%~dp0build.cmd" %*
)
