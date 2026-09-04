@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PROBE=import sys,tkinter;raise SystemExit(0 if sys.version_info ^>= (3,10) else 42)"
if defined CONDA_PREFIX call :try "%CONDA_PREFIX%\python.exe" && exit /b 0
call :try py -3 && exit /b 0
call :try python3 && exit /b 0
call :try python && exit /b 0
call :try "%USERPROFILE%\Miniconda3\python.exe" && exit /b 0
call :try "%USERPROFILE%\Anaconda3\python.exe" && exit /b 0
call :try "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" && exit /b 0
call :try "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" && exit /b 0
call :try "%ProgramFiles%\Python313\python.exe" && exit /b 0
call :try "%ProgramFiles%\Python312\python.exe" && exit /b 0
for /d %%E in ("%USERPROFILE%\Miniconda3\envs\*" "%USERPROFILE%\Anaconda3\envs\*") do call :try "%%~fE\python.exe" && exit /b 0
echo No compatible Python was found. Install Python 3.10 or newer with tkinter. 1>&2
pause
exit /b 1

:try
set "LABEL=%*"
%* -c "%PROBE%" >nul 2>&1
if errorlevel 1 (
  echo Rejected %LABEL%: missing, older than Python 3.10, or tkinter is unavailable. 1>&2
  exit /b 1
)
%* "tools\launcher.py"
exit /b 0
