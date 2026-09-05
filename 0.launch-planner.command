#!/bin/sh
# Double-clickable macOS bootstrap. Conda is resolved before Python is launched.
cd -- "$(dirname -- "$0")" || exit 1

show_error() {
  printf '\n%s\n' "$1" >&2
  printf 'Press Return to close.' >&2
  read answer
  exit 1
}

launch_conda() {
  conda_exe=$1
  [ -x "$conda_exe" ] || command -v "$conda_exe" >/dev/null 2>&1 || return 1

  base=$("$conda_exe" info --base 2>/dev/null) || return 1
  python="$base/bin/python"
  [ -x "$python" ] || show_error "Conda was found at $conda_exe, but its base environment has no Python. Install it into that environment with: $conda_exe install -n base python"

  probe=$($python -c 'import sys,tkinter;raise SystemExit(0 if sys.version_info >= (3,10) else 42)' 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    exec "$python" tools/launcher.py
  elif [ "$status" -eq 42 ]; then
    show_error "Conda was found at $conda_exe, but its base environment uses Python older than 3.10. Update that environment with: $conda_exe install -n base 'python>=3.10' tk"
  else
    show_error "Conda was found at $conda_exe, but the base environment ($base) is missing a required dependency. Install tkinter into that environment with: $conda_exe install -n base tk\n\nProbe error: $probe"
  fi
}

# Required discovery order: CONDA_EXE, PATH, standard installs, user selection.
[ -n "$CONDA_EXE" ] && launch_conda "$CONDA_EXE"
command -v conda >/dev/null 2>&1 && launch_conda "$(command -v conda)"
for candidate in "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" \
  /opt/miniconda3/bin/conda /opt/anaconda3/bin/conda \
  /opt/homebrew/Caskroom/miniconda/base/bin/conda; do
  launch_conda "$candidate"
done

if command -v osascript >/dev/null 2>&1; then
  selected=$(osascript -e 'POSIX path of (choose file with prompt "Select the conda executable")' 2>/dev/null)
  [ -n "$selected" ] && launch_conda "$selected"
fi

show_error "Conda not found. Install Anaconda or Miniconda, add conda to PATH, set CONDA_EXE, or run this launcher again and select the conda executable."
