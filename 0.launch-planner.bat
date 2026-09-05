@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem Prefer the already-active environment. This avoids guessing an installation
rem directory and also works when "where conda" returns a Library\bin shim first.
if defined CONDA_PREFIX call :try_python "%CONDA_PREFIX%\python.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%

rem Try the normal per-user install locations directly. A working Anaconda
rem Python does not need conda.exe to be on PATH in order to start the launcher.
call :try_python "%USERPROFILE%\miniconda3\python.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
call :try_python "%USERPROFILE%\anaconda3\python.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%

rem Remaining discovery order: CONDA_EXE, every PATH result, standard conda
rem executable locations, then user selection.
if defined CONDA_EXE call :consider "%CONDA_EXE%"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
for /f "delims=" %%C in ('where conda 2^>nul') do if not defined CONDA_HANDLED call :consider "%%C"
call :consider "%USERPROFILE%\miniconda3\Scripts\conda.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
call :consider "%USERPROFILE%\anaconda3\Scripts\conda.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%

set "SELECTED_CONDA="
for /f "usebackq delims=" %%C in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select the conda executable'; $d.Filter='Conda executable (conda.exe;conda.bat)|conda.exe;conda.bat|All files (*.*)|*.*'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "SELECTED_CONDA=%%C"
if defined SELECTED_CONDA call :consider "%SELECTED_CONDA%"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%

echo No compatible Python was found, and no usable conda executable was detected. 1>&2
echo Review each Rejected line above for the exact missing-file, version, or tkinter result. 1>&2
echo You can also run this launcher again and select the conda executable. 1>&2
pause
exit /b 1

:consider
call :try_conda "%~1"
set "CONDA_RESULT=%ERRORLEVEL%"
if not "%CONDA_RESULT%"=="1" set "CONDA_HANDLED=1"
exit /b 0

:try_conda
if not exist "%~1" exit /b 1
set "CONDA_CANDIDATE=%~1"
set "CONDA_BASE="
rem CALL is required for conda.bat; without it control may not return to us.
for /f "usebackq delims=" %%B in (`call "%CONDA_CANDIDATE%" info --base 2^>nul`) do set "CONDA_BASE=%%B"
if not defined CONDA_BASE exit /b 1
if not exist "%CONDA_BASE%\python.exe" (
  echo Conda was found at %CONDA_CANDIDATE%, but its base environment has no Python. 1>&2
  echo Install it into that environment with: "%CONDA_CANDIDATE%" install -n base python 1>&2
  pause
  exit /b 2
)
"%CONDA_BASE%\python.exe" -c "import sys,tkinter;too_old=sys.version_info.major in range(3) or (sys.version_info.major == 3 and sys.version_info.minor in range(10));raise SystemExit(42 if too_old else 0)" >nul 2>&1
if errorlevel 42 (
  echo Conda was found at %CONDA_CANDIDATE%, but its base environment uses Python older than 3.10. 1>&2
  echo Update that environment with: "%CONDA_CANDIDATE%" install -n base "python>=3.10" tk 1>&2
  pause
  exit /b 2
)
if errorlevel 1 (
  echo Conda was found at %CONDA_CANDIDATE%, but the base environment (%CONDA_BASE%) is missing tkinter. 1>&2
  echo Install it into that environment with: "%CONDA_CANDIDATE%" install -n base tk 1>&2
  pause
  exit /b 2
)
"%CONDA_BASE%\python.exe" "tools\launcher.py"
exit /b 0

:try_python
if not exist "%~1" (
  echo Rejected "%~1": file does not exist. 1>&2
  exit /b 1
)
"%~1" -c "import sys;too_old=sys.version_info.major in range(3) or (sys.version_info.major == 3 and sys.version_info.minor in range(10));raise SystemExit(42 if too_old else 0)" >nul 2>&1
set "PYTHON_PROBE_RESULT=%ERRORLEVEL%"
if "%PYTHON_PROBE_RESULT%"=="42" (
  set "PYTHON_VERSION="
  for /f "delims=" %%V in ('"%~1" --version 2^>^&1') do set "PYTHON_VERSION=%%V"
  echo Rejected "%~1": !PYTHON_VERSION! is older than Python 3.10. 1>&2
  exit /b 1
)
if not "%PYTHON_PROBE_RESULT%"=="0" (
  echo Rejected "%~1": Python could not run the version check ^(exit code %PYTHON_PROBE_RESULT%^). 1>&2
  echo Exact version-probe error: 1>&2
  "%~1" -c "import sys;too_old=sys.version_info.major in range(3) or (sys.version_info.major == 3 and sys.version_info.minor in range(10));raise SystemExit(42 if too_old else 0)"
  exit /b 1
)
"%~1" -c "import tkinter;print('tkinter', tkinter.TkVersion)" >nul 2>&1
set "TK_PROBE_RESULT=%ERRORLEVEL%"
if not "%TK_PROBE_RESULT%"=="0" (
  echo Rejected "%~1": Python is new enough, but tkinter could not be imported ^(exit code %TK_PROBE_RESULT%^). 1>&2
  echo Run this command to see the exact import error: 1>&2
  echo   "%~1" -c "import tkinter; print(tkinter.__file__)" 1>&2
  exit /b 1
)
set "PYTHON_VERSION="
for /f "delims=" %%V in ('"%~1" --version 2^>^&1') do set "PYTHON_VERSION=%%V"
echo Using "%~1" ^(!PYTHON_VERSION!, tkinter available^).
"%~1" "tools\launcher.py"
set "CONDA_RESULT=%ERRORLEVEL%"
set "CONDA_HANDLED=1"
exit /b 0
