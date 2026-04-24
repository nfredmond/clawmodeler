#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


MAC_ROOT_DYLIBS = {
    "libgobject-2.0.0.dylib": ("glib", "gobject-2.0"),
    "libpango-1.0.dylib": ("pango", "pango-1.0"),
    "libharfbuzz.0.dylib": ("harfbuzz", "harfbuzz"),
    "libharfbuzz-subset.0.dylib": ("harfbuzz", "harfbuzz-subset"),
    "libfontconfig.1.dylib": ("fontconfig", "fontconfig"),
    "libpangoft2-1.0.dylib": ("pango", "pangoft2-1.0"),
}

WINDOWS_ROOT_DLLS = [
    "libgobject-2.0-0.dll",
    "libpango-1.0-0.dll",
    "libharfbuzz-0.dll",
    "libharfbuzz-subset-0.dll",
    "libfontconfig-1.dll",
    "libpangoft2-1.0-0.dll",
]

WINDOWS_SYSTEM_DLL_NAMES = {
    "advapi32.dll",
    "bcrypt.dll",
    "cfgmgr32.dll",
    "comctl32.dll",
    "comdlg32.dll",
    "crypt32.dll",
    "dwmapi.dll",
    "gdi32.dll",
    "imm32.dll",
    "iphlpapi.dll",
    "kernel32.dll",
    "msvcrt.dll",
    "ole32.dll",
    "oleaut32.dll",
    "rpcrt4.dll",
    "secur32.dll",
    "setupapi.dll",
    "shell32.dll",
    "shlwapi.dll",
    "user32.dll",
    "userenv.dll",
    "usp10.dll",
    "version.dll",
    "winmm.dll",
    "ws2_32.dll",
}


def run(command: list[str | Path], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(part) for part in command],
        check=False,
        encoding="utf8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(str(part) for part in command)} failed with exit "
            f"{result.returncode}\n{result.stderr}"
        )
    return result


def reset_output(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def write_manifest(output: Path, *, mode: str, copied_files: list[Path]) -> None:
    relative_files = sorted(
        str(path.relative_to(output)).replace(os.sep, "/")
        for path in copied_files
        if path.is_file()
    )
    manifest = {
        "schema": 1,
        "mode": mode,
        "platform": sys.platform,
        "machine": platform.machine(),
        "file_count": len(relative_files),
        "files": relative_files,
    }
    (output / "weasyprint-runtime.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf8",
    )


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def unique_existing(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if not path.exists():
            continue
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def brew_prefix(formula: str | None = None) -> Path | None:
    brew = shutil.which("brew")
    if not brew:
        return None
    command = [brew, "--prefix"]
    if formula:
        command.append(formula)
    result = run(command, check=False)
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return Path(text) if text else None


def mac_prefixes() -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("HOMEBREW_PREFIX"):
        candidates.append(Path(os.environ["HOMEBREW_PREFIX"]))
    root_prefix = brew_prefix()
    if root_prefix:
        candidates.append(root_prefix)
    for formula in ("glib", "pango", "harfbuzz", "fontconfig"):
        prefix = brew_prefix(formula)
        if prefix:
            candidates.append(prefix)
    candidates.extend([Path("/opt/homebrew"), Path("/usr/local")])
    return unique_existing(candidates)


def find_macos_library(name: str, prefixes: list[Path]) -> Path | None:
    candidates: list[Path] = []
    for prefix in prefixes:
        candidates.append(prefix / "lib" / name)
        candidates.extend(prefix.glob(f"opt/*/lib/{name}"))
        candidates.extend(prefix.glob(f"Cellar/*/*/lib/{name}"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def parse_otool_dependencies(path: Path) -> list[str]:
    result = run(["otool", "-L", path])
    dependencies: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        token = line.strip().split(" ", 1)[0]
        if token:
            dependencies.append(token)
    return dependencies


def resolve_macos_dependency(dep: str, source: Path, prefixes: list[Path]) -> Path | None:
    dep_path = Path(dep)
    if dep_path.is_absolute() and dep_path.exists():
        if any(is_relative_to(dep_path, prefix) for prefix in prefixes):
            return dep_path
        return None
    dep_name = Path(dep.replace("@loader_path/", "").replace("@rpath/", "")).name
    candidates = [source.parent / dep_name]
    for prefix in prefixes:
        candidates.append(prefix / "lib" / dep_name)
        candidates.extend(prefix.glob(f"opt/*/lib/{dep_name}"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def rewrite_macos_install_names(dependency_map: dict[Path, list[str]]) -> None:
    copied_names = {path.name for path in dependency_map}
    for copied_path, dependencies in dependency_map.items():
        run(["install_name_tool", "-id", f"@rpath/{copied_path.name}", copied_path])
        for dep in dependencies:
            dep_name = Path(dep.replace("@loader_path/", "").replace("@rpath/", "")).name
            if dep_name in copied_names:
                run(
                    [
                        "install_name_tool",
                        "-change",
                        dep,
                        f"@loader_path/{dep_name}",
                        copied_path,
                    ]
                )
    for copied_path in dependency_map:
        run(["codesign", "--force", "--sign", "-", copied_path])


def copy_fontconfig_data(output: Path, prefixes: list[Path]) -> list[Path]:
    copied: list[Path] = []
    for relative in (Path("etc") / "fonts", Path("share") / "fontconfig"):
        for prefix in prefixes:
            source = prefix / relative
            if source.is_dir():
                destination = output / relative
                shutil.copytree(source, destination, dirs_exist_ok=True)
                copied.extend(path for path in destination.rglob("*") if path.is_file())
                break
    return copied


def collect_macos(output: Path) -> list[Path]:
    prefixes = mac_prefixes()
    roots: list[tuple[Path, str]] = []
    missing: list[str] = []
    for library_name in MAC_ROOT_DYLIBS:
        path = find_macos_library(library_name, prefixes)
        if path is None:
            missing.append(library_name)
        else:
            roots.append((path, library_name))
    if missing:
        raise RuntimeError(
            "Missing Homebrew WeasyPrint libraries: "
            f"{', '.join(missing)}. Install the release runtime deps with "
            "`brew install pango fontconfig harfbuzz glib`."
        )

    copied: dict[str, Path] = {}
    dependency_map: dict[Path, list[str]] = {}
    queue = roots[:]
    while queue:
        source, destination_name = queue.pop(0)
        destination = output / destination_name
        if destination_name in copied:
            continue
        shutil.copy2(source.resolve(), destination)
        copied[destination_name] = destination
        dependencies = parse_otool_dependencies(source.resolve())
        dependency_map[destination] = dependencies
        for dep in dependencies:
            dep_source = resolve_macos_dependency(dep, source.resolve(), prefixes)
            if dep_source is not None and dep_source.name not in copied:
                queue.append((dep_source, dep_source.name))

    rewrite_macos_install_names(dependency_map)
    copied_files = list(dependency_map) + copy_fontconfig_data(output, prefixes)
    return [path for path in copied_files if path.exists()]


def windows_search_dirs() -> list[Path]:
    candidates = [Path(part) for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    msys_root = Path(os.environ.get("MSYS2_ROOT", "C:/msys64"))
    mingw_prefix = os.environ.get("MINGW_PREFIX", "")
    if mingw_prefix:
        if Path(mingw_prefix).is_absolute() and not mingw_prefix.startswith("/"):
            candidates.append(Path(mingw_prefix) / "bin")
        elif mingw_prefix.startswith("/"):
            candidates.append(msys_root / mingw_prefix.lstrip("/") / "bin")
    candidates.extend([msys_root / "mingw64" / "bin", msys_root / "ucrt64" / "bin"])
    return unique_existing(candidates)


def find_windows_file(name: str, directories: list[Path]) -> Path | None:
    lower_name = name.lower()
    for directory in directories:
        direct = directory / name
        if direct.exists():
            return direct
        for candidate in directory.glob("*.dll"):
            if candidate.name.lower() == lower_name:
                return candidate
    return None


def parse_windows_dependencies(path: Path, objdump: str | None) -> list[str]:
    if not objdump:
        return []
    result = run([objdump, "-p", path], check=False)
    if result.returncode != 0:
        return []
    dependencies: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("DLL Name:"):
            dependencies.append(line.split(":", 1)[1].strip())
    return dependencies


def collect_windows(output: Path) -> list[Path]:
    search_dirs = windows_search_dirs()
    roots: list[Path] = []
    missing: list[str] = []
    for dll_name in WINDOWS_ROOT_DLLS:
        path = find_windows_file(dll_name, search_dirs)
        if path is None:
            missing.append(dll_name)
        else:
            roots.append(path)
    if missing:
        raise RuntimeError(
            "Missing MSYS2 WeasyPrint DLLs: "
            f"{', '.join(missing)}. Install mingw-w64-x86_64-pango with "
            "msys2/setup-msys2 before building the sidecar."
        )

    objdump = shutil.which("objdump")
    copied: dict[str, Path] = {}
    queue = roots[:]
    while queue:
        source = queue.pop(0)
        destination_name = source.name
        key = destination_name.lower()
        if key in copied:
            continue
        destination = output / destination_name
        shutil.copy2(source, destination)
        copied[key] = destination
        for dep in parse_windows_dependencies(source, objdump):
            dep_key = dep.lower()
            if dep_key in copied or dep_key in WINDOWS_SYSTEM_DLL_NAMES:
                continue
            dep_source = find_windows_file(dep, search_dirs)
            if dep_source is not None:
                queue.append(dep_source)

    if not objdump:
        root_dir = roots[0].parent
        for source in root_dir.glob("*.dll"):
            key = source.name.lower()
            if key not in copied:
                destination = output / source.name
                shutil.copy2(source, destination)
                copied[key] = destination

    data_prefixes = unique_existing([root.parent for root in search_dirs])
    copied_files = list(copied.values()) + copy_fontconfig_data(output, data_prefixes)
    return [path for path in copied_files if path.exists()]


def collect_runtime(output: Path) -> tuple[str, list[Path]]:
    reset_output(output)
    if sys.platform == "darwin":
        return "bundled-macos", collect_macos(output)
    if sys.platform == "win32":
        return "bundled-windows", collect_windows(output)
    return "system-linux", []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect WeasyPrint native runtime files beside the desktop sidecar."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    mode, copied_files = collect_runtime(args.output)
    write_manifest(args.output, mode=mode, copied_files=copied_files)
    print(
        f"Prepared WeasyPrint runtime at {args.output} "
        f"({mode}, {len(copied_files)} file(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
