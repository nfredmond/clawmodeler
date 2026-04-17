# Changelog

All notable changes to ClawModeler will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] — 2026-04-16

### Added

- `clawmodeler_engine/llm/` subpackage — local-first AI narrative support with a deterministic citation-grounding contract. Every generated sentence must cite `[fact:<fact_id>]` against a real fact_block or it is dropped (STRICT) or flagged (ANNOTATED). Grounding is regex + set-membership, never LLM-as-judge.
  - `grounding.py` — `validate_and_ground()`, `GroundingMode.{STRICT,ANNOTATED}`, markdown-aware sentence splitter that leaves headings, bullets, code fences, and blockquotes alone.
  - `provider.py` — `LLMProvider` ABC, `GenerationResult`, `ProviderProbe`, and a `FakeProvider` for deterministic tests.
  - `ollama.py` — default local provider against `http://localhost:11434`; lazy-imports `httpx`.
  - `anthropic.py` + `openai.py` — BYOK cloud providers. Gated behind `cloud_confirmed=true` in `llm_config.json`; `llm doctor` prints a loud confidentiality warning before any cloud call.
  - `config.py` — `<workspace>/llm_config.json` seeded by `clawmodeler-engine init`. Schema: `{provider, model, endpoint, temperature, grounding_mode, cloud_confirmed}`.
  - `narrative.py` — orchestrator that builds the prompt, calls the provider, and runs the result through `validate_and_ground()` against the run's `fact_blocks.jsonl`.
- `clawmodeler-engine llm doctor` — probes provider reachability, prints resolved model, and warns on cloud providers.
- `clawmodeler-engine llm configure <key>=<value>` — validated writer for `llm_config.json`.
- `--ai-narrative` flag on `clawmodeler-engine export` — opt-in grounded-narrative injection into `technical`, `layperson`, `brief`, and `all` report types. The `_base.md.j2` AI-disclosure banner slot (reserved in v0.3.0) is now wired.
- `ai_narrative_grounded` + `ai_narrative_unknown_fact_ids` checks on `qa_report.json`. When narrative generation runs, zero ungrounded sentences and zero unknown fact_ids are required; otherwise the export is blocked at the QA gate and a `<run_id>_export_blocked.md` report is written with the raw model output for review.
- `pyproject.toml` optional extras: `llm = ["httpx>=0.27"]`, `llm-cloud = ["anthropic>=0.34", "openai>=1.50"]`.
- Tests: `test_grounding.py`, `test_llm_provider.py`, `test_llm_byok.py`, `test_llm_config.py`, `test_ai_narrative.py` — cover the grounding contract, provider surface, BYOK gating, config round-trip, and end-to-end grounded + ungrounded narrative flows.

### Changed

- `build_qa_report` gained a `narrative=` kwarg; when supplied it records the grounded-narrative verdict in `checks` and adds `ai_narrative_ungrounded` to `blockers` if any sentence failed grounding.
- `render_report` and `_write_single_report` accept an `ai_narrative` template context. Without `--ai-narrative`, behavior is byte-identical to v0.3.0.

## [0.3.0] — 2026-04-16

### Added

- `clawmodeler_engine/charts.py` — matplotlib chart module producing scenario-comparison bars, VMT/CO2e dual-axis trends, project-score horizontal bars, and accessibility histograms as PNGs under `runs/<id>/outputs/figures/`.
- `clawmodeler_engine/maps.py` — folium interactive HTML choropleth module for zone population/VMT/accessibility overlays, plus an optional project-score marker map, written under `runs/<id>/outputs/maps/`.
- `clawmodeler_engine/templates/` — Jinja2 report templates (`_base.md.j2`, `technical.md.j2`, `layperson.md.j2`, `stakeholder_brief.md.j2`) with an AI-disclosure banner slot reserved for v0.4.0.
- `--report-type {technical,layperson,brief,all}` flag on `clawmodeler-engine export` (default `technical`, back-compat-safe).
- Optional `figure_ref` and `map_ref` fields on fact-block records so every figure and map is evidence-grounded.
- Unit coverage for chart rendering, map rendering, and template golden-path snapshots.

### Changed

- `clawmodeler_engine/report.py` rewritten as a Jinja2-backed renderer with `render_report`, `render_technical_report`, `render_layperson_report`, and `render_stakeholder_brief`; the legacy `render_markdown_report` entry point still works as a technical-report shim.
- `run_full_stack` now emits standard figures and maps and appends their fact-blocks to `fact_blocks.jsonl`. Optional visualization deps (matplotlib/folium) fail gracefully and add a recorded assumption if missing.

## [0.2.0] — 2026-04-16

### Added

- Automated multi-platform release pipeline (`.github/workflows/release.yml`) that builds desktop bundles for Linux, macOS Apple Silicon, and Windows on every tag push.
- macOS `.dmg` and Windows `.msi` + NSIS `-setup.exe` installers.
- Auto-generated platform icons (`icon.icns` for macOS, `icon.ico` for Windows, Square* tiles for Windows Store).
- First-run instructions in the README for unsigned macOS (Gatekeeper) and Windows (SmartScreen) builds.
- `Download` table in README linking directly to the latest release page.

### Changed

- `scripts/build-sidecar-binary.sh` now detects Windows vs Unix venv layout (`Scripts/` vs `bin/`) and PyInstaller `--add-data` separator, and disables MSYS path conversion on Windows runners so `cygpath`-rewritten paths reach PyInstaller intact.
- `desktop/src-tauri/tauri.conf.json` bundle resources switched to a `binaries/clawmodeler-engine*` wildcard so the `.exe` suffix is picked up on Windows.

### Known Limitations

- **No native macOS Intel (x86_64) installer.** GitHub's `macos-13` hosted-runner pool is exhausted and deprecating, so the `macos-13` matrix entry was dropped. Intel Mac users should build from source. A self-hosted Intel Mac runner or community Intel build is a candidate for a future release.

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

[0.4.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.4.0
[0.3.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.3.0
[0.2.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.2.0
[0.1.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.1.0
