@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Required discovery order: CONDA_EXE, PATH, standard installs, user selection.
if defined CONDA_EXE call :consider "%CONDA_EXE%"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
set "PATH_CONDA="
for /f "delims=" %%C in ('where conda 2^>nul') do if not defined PATH_CONDA set "PATH_CONDA=%%C"
if defined PATH_CONDA call :consider "%PATH_CONDA%"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
call :consider "%USERPROFILE%\Miniconda3\Scripts\conda.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
call :consider "%USERPROFILE%\Anaconda3\Scripts\conda.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
call :consider "%ProgramData%\Miniconda3\Scripts\conda.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%
call :consider "%ProgramData%\Anaconda3\Scripts\conda.exe"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%

set "SELECTED_CONDA="
for /f "usebackq delims=" %%C in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select the conda executable'; $d.Filter='Conda executable (conda.exe;conda.bat)|conda.exe;conda.bat|All files (*.*)|*.*'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "SELECTED_CONDA=%%C"
if defined SELECTED_CONDA call :consider "%SELECTED_CONDA%"
if defined CONDA_HANDLED exit /b %CONDA_RESULT%

echo Conda not found. Install Anaconda or Miniconda, add conda to PATH, set CONDA_EXE, or run this launcher again and select the conda executable. 1>&2
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
for /f "usebackq delims=" %%B in (`"%CONDA_CANDIDATE%" info --base 2^>nul`) do set "CONDA_BASE=%%B"
if not defined CONDA_BASE exit /b 1
if not exist "%CONDA_BASE%\python.exe" (
  echo Conda was found at %CONDA_CANDIDATE%, but its base environment has no Python. 1>&2
  echo Install it into that environment with: "%CONDA_CANDIDATE%" install -n base python 1>&2
  pause
  exit /b 2
)
"%CONDA_BASE%\python.exe" -c "import sys,tkinter;raise SystemExit(0 if sys.version_info ^>= (3,10) else 42)" >nul 2>&1
if errorlevel 42 (
  echo Conda was found at %CONDA_CANDIDATE%, but its base environment uses Python older than 3.10. 1>&2
  echo Update that environment with: "%CONDA_CANDIDATE%" install -n base "python^>=3.10" tk 1>&2
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
