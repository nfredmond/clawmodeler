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
from __future__ import annotations

import os
from pathlib import Path
import sys


_DLL_DIRECTORY_HANDLES = []


def _prepend_env_path(name: str, value: Path) -> None:
    text = str(value)
    existing = os.environ.get(name, "")
    parts = [part for part in existing.split(os.pathsep) if part]
    if text not in parts:
        os.environ[name] = os.pathsep.join([text, *parts])


def _candidate_runtime_dirs() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("CLAWMODELER_WEASYPRINT_RUNTIME")
    if override:
        candidates.append(Path(override))

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_dir / "weasyprint-runtime",
            executable_dir / "binaries" / "weasyprint-runtime",
        ]
    )
    return candidates


def _configure_fontconfig(runtime_dir: Path) -> None:
    fonts_dir = runtime_dir / "etc" / "fonts"
    fonts_conf = fonts_dir / "fonts.conf"
    if fonts_conf.is_file():
        os.environ.setdefault("FONTCONFIG_FILE", str(fonts_conf))
        os.environ.setdefault("FONTCONFIG_PATH", str(fonts_dir))


def _configure_windows_runtime(runtime_dir: Path) -> None:
    _prepend_env_path("PATH", runtime_dir)
    existing = os.environ.get("WEASYPRINT_DLL_DIRECTORIES", "")
    parts = [part for part in existing.split(";") if part]
    runtime_text = str(runtime_dir)
    if runtime_text not in parts:
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = ";".join([runtime_text, *parts])

    if hasattr(os, "add_dll_directory"):
        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(runtime_text))
        except OSError:
            pass


def _install_macos_cffi_runtime_patch(runtime_dir: Path) -> None:
    try:
        import cffi
    except ImportError:
        return

    original_dlopen = cffi.FFI.dlopen
    if getattr(original_dlopen, "_clawmodeler_weasyprint_runtime", False):
        return

    def first_existing(names: tuple[str, ...], pattern: str) -> str | None:
        for name in names:
            path = runtime_dir / name
            if path.is_file():
                return str(path)
        return next((str(path) for path in sorted(runtime_dir.glob(pattern))), None)

    library_groups = (
        (
            first_existing(("libgobject-2.0.0.dylib",), "libgobject-2.0*.dylib"),
            (
                "libgobject-2.0-0",
                "gobject-2.0-0",
                "gobject-2.0",
                "libgobject-2.0.so.0",
                "libgobject-2.0.0.dylib",
                "libgobject-2.0-0.dll",
            ),
        ),
        (
            first_existing(
                ("libpango-1.0.0.dylib", "libpango-1.0.dylib"),
                "libpango-1.0*.dylib",
            ),
            (
                "libpango-1.0-0",
                "pango-1.0-0",
                "pango-1.0",
                "libpango-1.0.so.0",
                "libpango-1.0.dylib",
                "libpango-1.0.0.dylib",
                "libpango-1.0-0.dll",
            ),
        ),
        (
            first_existing(("libharfbuzz.0.dylib",), "libharfbuzz.*.dylib"),
            (
                "libharfbuzz-0",
                "harfbuzz",
                "harfbuzz-0.0",
                "libharfbuzz.so.0",
                "libharfbuzz.0.dylib",
                "libharfbuzz-0.dll",
            ),
        ),
        (
            first_existing(
                ("libharfbuzz-subset.0.dylib",),
                "libharfbuzz-subset*.dylib",
            ),
            (
                "libharfbuzz-subset-0",
                "harfbuzz-subset",
                "harfbuzz-subset-0.0",
                "libharfbuzz-subset.so.0",
                "libharfbuzz-subset.0.dylib",
                "libharfbuzz-subset-0.dll",
            ),
        ),
        (
            first_existing(("libfontconfig.1.dylib",), "libfontconfig*.dylib"),
            (
                "libfontconfig-1",
                "fontconfig-1",
                "fontconfig",
                "libfontconfig.so.1",
                "libfontconfig.1.dylib",
                "libfontconfig-1.dll",
            ),
        ),
        (
            first_existing(
                ("libpangoft2-1.0.0.dylib", "libpangoft2-1.0.dylib"),
                "libpangoft2-1.0*.dylib",
            ),
            (
                "libpangoft2-1.0-0",
                "pangoft2-1.0-0",
                "pangoft2-1.0",
                "libpangoft2-1.0.so.0",
                "libpangoft2-1.0.dylib",
                "libpangoft2-1.0.0.dylib",
                "libpangoft2-1.0-0.dll",
            ),
        ),
    )
    runtime_libraries: dict[str, str] = {}
    for runtime_path, aliases in library_groups:
        if runtime_path:
            for alias in aliases:
                runtime_libraries[alias] = runtime_path

    def patched_dlopen(self, name, flags=0):
        if isinstance(name, str):
            local_path = runtime_libraries.get(name) or runtime_libraries.get(Path(name).name)
            if local_path:
                return original_dlopen(self, local_path, flags)
        return original_dlopen(self, name, flags)

    patched_dlopen._clawmodeler_weasyprint_runtime = True
    cffi.FFI.dlopen = patched_dlopen


def _configure_macos_runtime(runtime_dir: Path) -> None:
    _prepend_env_path("DYLD_LIBRARY_PATH", runtime_dir)
    _prepend_env_path("DYLD_FALLBACK_LIBRARY_PATH", runtime_dir)
    _install_macos_cffi_runtime_patch(runtime_dir)


def _configure_weasyprint_runtime() -> None:
    runtime_dir = next((path for path in _candidate_runtime_dirs() if path.is_dir()), None)
    if runtime_dir is None:
        return

    os.environ.setdefault("CLAWMODELER_WEASYPRINT_RUNTIME", str(runtime_dir))
    _configure_fontconfig(runtime_dir)
    if sys.platform == "win32":
        _configure_windows_runtime(runtime_dir)
    elif sys.platform == "darwin":
        _configure_macos_runtime(runtime_dir)


_configure_weasyprint_runtime()

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
# Run from the repo root so Windows Git Bash does not rewrite an absolute
# editable-extra path such as C:\...\clawmodeler[pdf,docx].
(
  cd "$repo_root"
  "$venv_python" -m pip install -e ".[pdf,docx]"
)
"$venv_python" "$repo_root/scripts/collect-weasyprint-runtime.py" \
  --output "$dist_dir/weasyprint-runtime"

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
