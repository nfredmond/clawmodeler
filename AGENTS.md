# Repository Guidelines

ClawModeler is a standalone, local-first transportation scenario modeling stack: Python engine + Tauri v2 desktop UI + `clawmodeler-engine` console script.

## Project Structure

- `clawmodeler_engine/` — Python package (engine, CLI, bridges, QA, reports).
- `desktop/` — Tauri v2 desktop workbench (Vite + vanilla TS front, Rust sidecar).
- `tests/` — Python unit tests for the engine.
- `scripts/` — install/build/check helpers.
- `docs/` — roadmap, stack overview, CLI reference.
- `requirements/` — Python profile requirements (`light`, `standard`, `full`, `gpu`).
- `pyproject.toml` — Python package metadata; `clawmodeler-engine` console script points at `clawmodeler_engine.cli:main`.

## Build & Test Commands

- Install editable Python package: `python3 -m pip install -e .`
- Install a dependency profile: `bash scripts/install-profile.sh standard`
- Engine tests: `pnpm engine:test`
- Desktop tests: `pnpm ui:test`
- Desktop dev: `pnpm ui:dev` (full sidecar loop: `pnpm tauri:dev`)
- Packaging check: `pnpm engine:check`

## Conventions

- Python >=3.10, ruff-checked, 100-col.
- Desktop UI is vanilla TypeScript, no React; tests via Vitest.
- Keep screening-level outputs clearly labeled per the QA rules in `README.md`.
- Do not invent data, bypass QA, or present screening-level outputs as detailed engineering forecasts.
