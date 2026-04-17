# Changelog

All notable changes to ClawModeler will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] — 2026-04-16

### Added

- `clawmodeler_engine/planner_pack/lapm.py` — **Planner Pack v2**: Caltrans *Local Assistance Procedures Manual* (LAPM) project programming fact sheets. Reads a finished run's `project_scores.csv`, optionally enriches each project with lat/lon, description, project type, estimated cost, and schedule from the candidate-projects sidecar (resolved from the run manifest, then `inputs/projects.csv`, then `inputs/processed/projects.csv`, then `inputs/raw/projects.csv`), and emits a Chapter 3-style programming exhibit per project. Fields the lead agency has not supplied are labeled explicitly ("to be provided by lead agency"); ClawModeler does not invent administrative content.
- `clawmodeler_engine/templates/planner_pack/lapm_exhibit.md.j2` — Jinja2 template for the LAPM programming packet: scope, methodology citing LAPM Chapter 3 and Chapter 7, a programming summary table across all projects, and per-project fact sheets covering identifiers, location, description, estimated cost, schedule, ClawModeler screening scores, purpose and need, and citations.
- `clawmodeler-engine planner-pack lapm-exhibit` CLI subcommand. Flags: `--workspace`, `--run-id`, `--lead-agency`, `--district`, `--json`. Writes `lapm_exhibit.csv`, `lapm_exhibit.json`, appends `lapm_programming_exhibit` fact_blocks to `fact_blocks.jsonl`, and renders `reports/<run_id>_lapm_exhibit.md`.
- `tests/test_lapm_exhibit.py` — 9 tests covering the arithmetic/enrichment path (default lead-agency placeholders, sidecar enrichment of location/cost/description), input validation (empty rows, missing project_id, all-empty project_ids), fact_block shape, end-to-end on the demo workspace (CSV + JSON + report + fact_block append, `City of Grass Valley` / `District 3` in the rendered output), missing-run error path, and idempotent re-runs.

### Changed

- None. v0.6.1 is strictly additive. Existing exports, chat, AI narrative, CEQA VMT screening, and QA behavior are byte-identical to v0.6.0.

## [0.6.0] — 2026-04-16

### Added

- `clawmodeler_engine/planner_pack/` — **Planner Pack v1**: regulatory deliverables grounded in run fact_blocks. First module is CEQA §15064.3 VMT significance screening.
- `clawmodeler_engine/planner_pack/ceqa.py` — `compute_ceqa_vmt`, `ceqa_vmt_fact_blocks`, `render_ceqa_vmt_markdown`, `write_ceqa_vmt`. Reads a finished run's `vmt_screening.csv`, compares each scenario's VMT per capita to an agency-configurable reference baseline (default `question.daily_vmt_per_capita`, then 22.0), applies the OPR *Technical Advisory on Evaluating Transportation Impacts in CEQA* (December 2018) default of **15 percent below the regional/citywide baseline**, and issues `potentially significant` / `less than significant` determinations. Agencies can override the project type (`residential` / `employment` / `retail`), reference label (`regional` / `citywide` / `custom`), reference VMT per capita, and percent-below value.
- `clawmodeler_engine/templates/planner_pack/ceqa_vmt.md.j2` — Jinja2 template for the CEQA §15064.3 VMT memo: scope, methodology citing OPR Dec 2018, per-scenario determination table, findings split into significant vs. less-than-significant lists, and a citations block.
- `clawmodeler-engine planner-pack ceqa-vmt` CLI subcommand. Flags: `--workspace`, `--run-id`, `--project-type`, `--reference-label`, `--reference-vmt-per-capita`, `--threshold-pct`, `--json`. Writes `ceqa_vmt.csv`, `ceqa_vmt.json`, appends `ceqa_vmt_determination` fact_blocks to `fact_blocks.jsonl`, and renders `reports/<run_id>_ceqa_vmt.md`. The appended fact_blocks remain subject to the same citation contract that gates `export --ai-narrative` and `chat`, so downstream narrative and chat turns can cite CEQA determinations.
- `tests/test_ceqa_vmt.py` — 14 tests covering the arithmetic (below / above / at-threshold), input validation (invalid project type, reference label, threshold_pct, negative reference), empty-row handling, fact_block shape, end-to-end on the demo workspace (CSV + JSON + report + fact_block append), missing-run error path, analysis_plan.json reference fallback, and idempotent re-runs.

### Changed

- None. v0.6.0 is strictly additive. Existing exports, chat, AI narrative, and QA behavior are byte-identical to v0.5.1.

## [0.5.1] — 2026-04-16

### Added

- Desktop chat panel: a new `Chat` section in the workbench that interrogates the loaded run's `fact_blocks.jsonl` against the v0.5.0 grounding contract. Citation chips render inline for every `[fact:<id>]` token; replies are badged `grounded` / `partial` / `unknown-ids` based on the engine's `ChatTurn` payload. Ctrl/Cmd-Enter sends the message.
- Tauri command `clawmodeler_chat(workspace, runId, message, noHistory)` that shells the bundled sidecar (or `python3 -m clawmodeler_engine` in dev) with `chat --json` and returns the engine `EngineResult` envelope. Input validation rejects empty workspace / run id / message at the Rust boundary.
- `parseChatTurn`, `segmentChatText`, and `chatTurnBadge` helpers in `desktop/src/workbench.ts` plus three new Vitest cases covering payload parsing, citation-chip segmentation, and grounding badges.

### Changed

- Engine behavior unchanged from v0.5.0. v0.5.1 is a desktop-shell follow-up: the `chat` CLI subcommand, grounding validator, and `chat_history.jsonl` persistence all continue to be the source of truth.

## [0.5.0] — 2026-04-16

### Added

- `clawmodeler_engine/chat.py` — **Chat With the Run**. Read-only grounded Q&A against a finished run's `fact_blocks.jsonl`. Every sentence in the model reply must cite `[fact:<fact_id>]` against a known fact_id or it is dropped (STRICT mode). When nothing survives grounding, the reply collapses to the canonical `"I do not have evidence for that in this run's fact_blocks."` sentence. Each turn is appended to `runs/<run_id>/chat_history.jsonl` for reproducibility, and the prior 5 turns feed the next prompt by default.
- `clawmodeler-engine chat --workspace <ws> --run-id <id> --message <msg>` CLI subcommand. Flags: `--no-history` to skip the chat_history replay, `--json` for machine-readable `ChatTurn` payload. Reuses the same provider + `cloud_confirmed` gate as `export --ai-narrative`, so cloud BYOK providers still require explicit confirmation before any fact_blocks leave the machine.
- `tests/test_chat.py` — 12 tests covering prompt composition, grounded persistence, turn_id increment across calls, history feeding into subsequent prompts, ungrounded → NOT_IN_CONTEXT fallback, unknown fact_id recording, missing/empty `fact_blocks.jsonl` raising `InsufficientDataError`, and the cloud-confirmation gate.

### Changed

- None. v0.5.0 is strictly additive. `export`, `--ai-narrative`, and the grounding contract are byte-identical to v0.4.1.

## [0.4.1] — 2026-04-16

### Added

- `clawmodeler_engine/pdf.py` — `render_pdf(manifest, report_type, reports_dir, *, ai_narrative=None) -> bytes`. Pipeline: `render_report` → Markdown → HTML via `markdown-it-py` (CommonMark + tables) → PDF via `weasyprint.HTML(...).write_pdf()`. Figures resolve via `base_url`; maps appear as styled links (interactive content belongs in the HTML report, not a static PDF).
- `--format pdf` on `clawmodeler-engine export` is now end-to-end (CLI already accepted the choice; `write_export` now branches on format). `--format pdf --ai-narrative` composes cleanly with grounded narrative.
- `pyproject.toml` optional extra: `pdf = ["markdown-it-py>=3.0", "weasyprint>=62"]`.
- `tests/test_pdf.py` — per-report-type PDF rendering (`%PDF-` magic bytes + size checks), a grounded-narrative + PDF composition case, and a dependency-missing sanity check.

### Changed

- `write_export` in `orchestration.py` now accepts `export_format in {"md", "pdf"}`; the previous `md`-only guard is replaced with a format branch that dispatches to Markdown or PDF rendering.
- `.github/workflows/ci.yml` installs `libpango-1.0-0` + `libpangoft2-1.0-0` (WeasyPrint system deps) and `[visuals,pdf]` extras.

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

[0.6.1]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.1
[0.6.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.0
[0.5.1]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.5.1
[0.5.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.5.0
[0.4.1]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.4.1
[0.4.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.4.0
[0.3.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.3.0
[0.2.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.2.0
[0.1.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.1.0
