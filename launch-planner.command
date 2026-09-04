#!/bin/sh
# Double-clickable macOS bootstrap. Each candidate gets only a version/Tk probe.
cd -- "$(dirname -- "$0")" || exit 1
MIN='import sys,tkinter;raise SystemExit(0 if sys.version_info >= (3,10) else 42)'

try_python() {
  candidate=$1
  [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1 || {
    printf 'Rejected %s: executable not found.\n' "$candidate" >&2; return 1;
  }
  "$candidate" -c "$MIN" >/dev/null 2>&1
  status=$?
  if [ "$status" -eq 0 ]; then
    exec "$candidate" "tools/launcher.py"
  elif [ "$status" -eq 42 ]; then
    printf 'Rejected %s: Python 3.10 or newer is required.\n' "$candidate" >&2
  else
    printf 'Rejected %s: version/Tk probe failed; install tkinter for this interpreter.\n' "$candidate" >&2
  fi
  return 1
}

[ -n "$CONDA_PREFIX" ] && try_python "$CONDA_PREFIX/bin/python"
for candidate in python3 python \
  "$HOME/miniconda3/bin/python" "$HOME/anaconda3/bin/python" \
  /opt/homebrew/bin/python3 /usr/local/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  try_python "$candidate"
done
for candidate in "$HOME"/miniconda3/envs/*/bin/python "$HOME"/anaconda3/envs/*/bin/python; do
  [ -e "$candidate" ] && try_python "$candidate"
done
printf '\nNo compatible Python was found. Install Python 3.10+ with tkinter or choose an interpreter from a terminal.\n' >&2
printf 'Press Return to close.' >&2
read answer
exit 1
