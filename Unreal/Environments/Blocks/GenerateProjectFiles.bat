@echo off
setlocal

set "UBT="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ResolveUnrealBuildToolPath.ps1" -ProjectDir "%cd%"`) do set "UBT=%%i"

if not "%UBT%"=="" (
    for %%f in (*.uproject) do (
        echo Generating files for %%f with %UBT%
        "%UBT%" -projectfiles -project="%cd%\%%f" -game -rocket -progress
        if errorlevel 1 exit /b 1
    )
    exit /b 0
)

del /q gen_temp.txt 2>nul
del /q gen_temp.tmp 2>nul
powershell -command "& { (Get-ItemProperty 'Registry::HKEY_CLASSES_ROOT\Unreal.ProjectFile\shell\rungenproj' -Name 'Icon' ).'Icon' } > gen_temp.tmp"
type gen_temp.tmp > gen_temp.txt
set /p gen_bin=<gen_temp.txt
del /q gen_temp.tmp
del /q gen_temp.txt

for %%f in (*.uproject) do (
    echo Generating files for %%f with %gen_bin%
    %gen_bin% /projectfiles "%cd%\%%f"
    if errorlevel 1 exit /b 1
)
