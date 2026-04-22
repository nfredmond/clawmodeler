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
# Install with [pdf,docx] extras so PyInstaller bundles weasyprint,
# markdown-it-py, and python-docx into the sidecar binary. Without these,
# `clawmodeler-engine export --format pdf|docx` crashes at runtime even
# though the desktop UI offers those formats.
"$venv_python" -m pip install -e "$repo_root[pdf,docx]"

rm -f "$dist_dir/clawmodeler-engine$exe_suffix"

# MSYS/Git Bash (Windows) rewrites posix-looking args before passing to .exe.
# Disable that conversion for pyinstaller so --add-data SRC;DEST stays intact.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

if [ -n "$exe_suffix" ] && command -v cygpath >/dev/null 2>&1; then
  repo_root_native="$(cygpath -w "$repo_root")"
  data_src="${repo_root_native}\\clawmodeler_engine\\toolbox.default.json"
  templates_src="${repo_root_native}\\clawmodeler_engine\\templates"
  paths_arg="$repo_root_native"
  distpath_arg="$(cygpath -w "$dist_dir")"
  workpath_arg="$(cygpath -w "$work_dir/build")"
  specpath_arg="$(cygpath -w "$work_dir")"
  launcher_arg="$(cygpath -w "$launcher")"
else
  data_src="$repo_root/clawmodeler_engine/toolbox.default.json"
  templates_src="$repo_root/clawmodeler_engine/templates"
  paths_arg="$repo_root"
  distpath_arg="$dist_dir"
  workpath_arg="$work_dir/build"
  specpath_arg="$work_dir"
  launcher_arg="$launcher"
fi

"$venv_bin/pyinstaller" \
  --clean \
  --noconfirm \
  --onefile \
  --name clawmodeler-engine \
  --distpath "$distpath_arg" \
  --workpath "$workpath_arg" \
  --specpath "$specpath_arg" \
  --paths "$paths_arg" \
  --add-data "${data_src}${data_sep}clawmodeler_engine" \
  --add-data "${templates_src}${data_sep}clawmodeler_engine/templates" \
  "$launcher_arg"

"$dist_dir/clawmodeler-engine$exe_suffix" --version >/dev/null

echo "Built $dist_dir/clawmodeler-engine$exe_suffix"
