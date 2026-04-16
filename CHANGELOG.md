# Changelog

All notable changes to ClawModeler will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-04-16

### Added

- Automated multi-platform release pipeline (`.github/workflows/release.yml`) that builds desktop bundles for Linux, macOS (Apple Silicon + Intel), and Windows on every tag push.
- macOS `.dmg` and Windows `.msi` + NSIS `-setup.exe` installers.
- Auto-generated platform icons (`icon.icns` for macOS, `icon.ico` for Windows, Square* tiles for Windows Store).
- First-run instructions in the README for unsigned macOS (Gatekeeper) and Windows (SmartScreen) builds.
- `Download` table in README linking directly to the latest release page.

### Changed

- `scripts/build-sidecar-binary.sh` now detects Windows vs Unix venv layout (`Scripts/` vs `bin/`) and PyInstaller `--add-data` separator.
- `desktop/src-tauri/tauri.conf.json` bundle resources switched to a `binaries/clawmodeler-engine*` wildcard so the `.exe` suffix is picked up on Windows.

## [0.1.0] — 2026-04-16

Initial standalone release. Extracted from the `nfredmond/openclaw` fork into its own repo; fresh history.

### Added

- Python `clawmodeler_engine` package with CLI subcommands: `init`, `scaffold`, `intake`, `plan`, `run`, `export`, `doctor`, `tools`, `demo`, `workflow`, `bridge`, `graph`.
- Console script `clawmodeler-engine` registered via `pyproject.toml`.
- Tauri v2 desktop workbench under `desktop/` with vanilla TypeScript front-end, `@tauri-apps/plugin-dialog` file pickers, and a "Create starter `question.json`" flow.
- Bridge adapters for SUMO, MATSim, UrbanSim, DTALite, and TBEST.
- QA-gated report export with fact-block grounding.
- GitHub Actions CI running ruff, engine unittests, and desktop Vitest.
- Apache-2.0 license.

[0.2.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.2.0
[0.1.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.1.0
