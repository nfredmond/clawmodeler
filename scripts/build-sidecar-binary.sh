#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
  python_bin="python"
fi
venv_dir="${CLAWMODELER_SIDECAR_VENV:-$repo_root/.tmp/clawmodeler-sidecar-venv}"
dist_dir="$repo_root/desktop/src-tauri/binaries"
work_dir="$repo_root/.tmp/clawmodeler-sidecar-pyinstaller"

mkdir -p "$dist_dir" "$work_dir" "$repo_root/.tmp"
launcher="$work_dir/clawmodeler-engine-launcher.py"

cat >"$launcher" <<'PY'
from clawmodeler_engine.cli import main

raise SystemExit(main())
PY

if [ -f "$venv_dir/Scripts/python.exe" ]; then
  venv_python="$venv_dir/Scripts/python.exe"
  venv_bin="$venv_dir/Scripts"
  exe_suffix=".exe"
  data_sep=";"
else
  venv_python="$venv_dir/bin/python"
  venv_bin="$venv_dir/bin"
  exe_suffix=""
  data_sep=":"
fi

if [ ! -x "$venv_python" ] && [ ! -f "$venv_python" ]; then
  "$python_bin" -m venv "$venv_dir"
  if [ -f "$venv_dir/Scripts/python.exe" ]; then
    venv_python="$venv_dir/Scripts/python.exe"
    venv_bin="$venv_dir/Scripts"
    exe_suffix=".exe"
    data_sep=";"
  else
    venv_python="$venv_dir/bin/python"
    venv_bin="$venv_dir/bin"
    exe_suffix=""
    data_sep=":"
  fi
fi

"$venv_python" -m pip install --upgrade pip setuptools wheel pyinstaller
"$venv_python" -m pip install -e "$repo_root"

rm -f "$dist_dir/clawmodeler-engine$exe_suffix"

"$venv_bin/pyinstaller" \
  --clean \
  --noconfirm \
  --onefile \
  --name clawmodeler-engine \
  --distpath "$dist_dir" \
  --workpath "$work_dir/build" \
  --specpath "$work_dir" \
  --paths "$repo_root" \
  --add-data "$repo_root/clawmodeler_engine/toolbox.default.json${data_sep}clawmodeler_engine" \
  "$launcher"

"$dist_dir/clawmodeler-engine$exe_suffix" --version >/dev/null

echo "Built $dist_dir/clawmodeler-engine$exe_suffix"
