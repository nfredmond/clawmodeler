# Changelog

All notable changes to ClawModeler will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.3] — 2026-04-20

### Added

- **Desktop artifact preview.** The Tauri/Vite workbench can now preview text artifacts (`.md`, `.csv`, `.json`, `.jsonl`, `.xml`, `.sh`, and similar) directly from the artifact list. Reads are local, read-only, and truncated at 128 KB for large files.
- **Desktop workflow acceptance gate.** New `pnpm desktop:acceptance` script runs a full fixture-backed workflow: intake, scenario run, bridge preparation/validation, report export, Planner Pack CEQA VMT generation, what-if, diff, and portfolio.
- **Tiny public integration fixture.** New `tests/fixtures/tiny_region/` fixture gives CI a small non-demo path for workflow, bridge, Planner Pack, what-if, diff, and portfolio coverage.

### Changed

- **Bridge reports are easier to inspect.** Bridge preparation and validation results now include generated-file links for prepared bridges, plus structured `required_inputs` / `missing_inputs` fields for skipped bridge packages.
- **Version advanced to 0.9.3** across the Python engine, root package metadata, and Tauri desktop metadata.

## [0.9.2] — 2026-04-19

### Added

- **Planner Pack: STIP cycle packet.** New `clawmodeler_engine/planner_pack/stip.py` + `templates/planner_pack/stip.md.j2` + `clawmodeler-engine planner-pack stip --run-id <id> [--cycle "2026 STIP"] [--region north|south] [--json]` CLI subparser. Programs a finished run's candidate projects into a California State Transportation Improvement Program (STIP) packet per Streets & Highways Code §§14525-14529.11 and the current CTC STIP Guidelines. Reads `runs/<id>/outputs/tables/project_scores.csv` plus an optional long-format `inputs/stip_overlay.csv` sidecar (one row per project × phase × fiscal_year; columns: `project_id`, `phase` ∈ {`PA&ED`, `PS&E`, `R/W`, `CON`, `other`} with aliases like `paed`/`row`/`construction` normalized, `fiscal_year` (e.g. `"2026-27"`), `cost_thousands`, `funding_source` (e.g. `RIP`/`IIP`/`SB1`), `ppno`, `region` ∈ {`north`, `south`}, `data_source_ref`). Negative costs are filtered. Writes `stip.csv` + `stip.json` + `reports/<run_id>_stip.md` + appends `stip_programming_row` + `stip_portfolio_summary` fact_blocks with `method_ref="planner_pack.stip"` — v0.7.1 QA-gate compliant. Portfolio summary aggregates totals by fiscal year and funding source, plus an **N/S split table scored against the 40% north / 60% south S&HC §188 target** (±5% tolerance for cycle-level reporting).
- **Portfolio dashboard + run diff now cover STIP.** `clawmodeler_engine/portfolio.py` adds `stip` to its Planner Pack artifact-coverage tuple. `clawmodeler_engine/diff.py` gains a `stip` artifact entry with a **triple composite key** `(project_id, phase, fiscal_year)` — STIP rows are three-dimensional, so single- or double-column keys would collapse programming entries. Tracked fields: `cost_thousands`, `funding_source`, `ppno`, `region`, `overlay_supplied`. The v0.9.1 `_row_key` helper generalized over n-tuples, so no engine change was required beyond the artifact spec. `tests/test_portfolio.py` gains `test_stip_surfaces_in_planner_pack_artifacts` regression.
- `tests/test_planner_pack_stip.py` — 14-case regression suite: empty rows raise `InsufficientDataError`, blank `cycle_label` raises `ValueError`, unknown phases raise, phase aliases normalize (`row` → `R/W`, `paed` → `PA&ED`, etc.), unknown regions raise, missing overlay produces no programming rows, negative `cost_thousands` filtered, portfolio totals aggregate by fiscal year and funding source, 40/60 N/S split produces `meets_target=True`, fact_blocks pass `qa.is_valid_fact_block` with `method_ref="planner_pack.stip"`, end-to-end with and without overlay, idempotent re-run, and missing run raises. `tests/test_qa_gate_planner_pack.py` gains `test_stip_passes_qa_gate` and folds STIP into the full-stack export-ready test.
- **Desktop Planner Pack workflow.** The Tauri/Vite workbench now includes a Planner Pack panel for CEQA VMT, LAPM, RTP, equity, ATP, HSIP, CMAQ, and STIP generation from the active run, plus a normalized run summary that surfaces manifest path, report path, scenarios, QA export readiness, bridge readiness, generated artifact counts, Planner Pack coverage, warnings, and missing manifest sidecars.

### Fixed

- **Wheel installs now include Markdown templates.** The packaging manifest now ships `clawmodeler_engine/templates/**/*.j2`, and `scripts/check-packaging.sh` asserts the core report and Planner Pack templates are present in the built wheel so installed console scripts can render reports outside an editable checkout.
- **Planner Pack manifest sidecars resolve from the actual run manifest.** Optional `*_overlay_csv` and `candidate_projects_csv` artifact references are now read from `runs/<id>/manifest.json` (while preserving the legacy `outputs/run_manifest.json` fallback), and a single string path is no longer accidentally iterated character-by-character.
- **The repository test script now runs the full engine suite.** `pnpm engine:test` and the packaging check both discover `*test*.py`, covering `test_*.py` regression files in addition to the sidecar smoke test.
- **Desktop/API parity fixes.** Browser dev middleware now covers chat, what-if, portfolio, and diff routes; workspace artifact discovery also includes run reports, matching the Tauri path more closely. The portfolio diff UI now reads the engine's `report_path` while preserving the legacy `diff_report_path` fallback.
- **CLI/provider contract fixes.** `export --format` now advertises only implemented formats (`md`, `pdf`), and `provider=fake` in `llm_config.json` now builds the in-process `FakeProvider` instead of validating but failing at construction time.
- **Docs now match the standalone app.** README, stack, CLI, roadmap, and narrative docs now describe the current Python engine + vanilla TypeScript Tauri workbench, current Planner Pack coverage, and the 0.9.2 release-plus-planner-workflow priority.

## [0.9.1] — 2026-04-18

### Added

- **Planner Pack: CMAQ emissions screen.** New `clawmodeler_engine/planner_pack/cmaq.py` + `templates/planner_pack/cmaq.md.j2` + `clawmodeler-engine planner-pack cmaq --run-id <id> --analysis-year <y> [--pollutants pm2_5,nox,...] [--json]` CLI subparser. Screens a finished run's candidate projects against FHWA Congestion Mitigation and Air Quality Improvement Program (CMAQ) eligibility (23 USC 149; FHWA CMAQ Reference Guide). Reads `runs/<id>/outputs/tables/project_scores.csv` plus an optional long-format `inputs/cmaq_overlay.csv` sidecar (one row per project × pollutant; columns: `project_id`, `pollutant` ∈ {pm2_5, pm10, nox, voc, co} with aliases like `PM2.5` / `pm-2.5` normalized, `kg_per_day_reduced`, `cost_effectiveness_usd_per_kg`, `eligibility_category`, `nonattainment_area`, `data_source_ref`). Negative emission reductions are filtered. Writes `cmaq.csv` + `cmaq.json` + `reports/<run_id>_cmaq.md` + appends `cmaq_emissions_estimate` + `cmaq_portfolio_summary` fact_blocks with `method_ref="planner_pack.cmaq"` — v0.7.1 QA-gate compliant. Portfolio summary aggregates `total_kg_per_day_by_pollutant` and `mean_cost_effectiveness_usd_per_kg_by_pollutant`.
- **Portfolio dashboard + run diff now cover CMAQ.** `clawmodeler_engine/portfolio.py` adds `cmaq` to its Planner Pack artifact-coverage tuple. `clawmodeler_engine/diff.py` gains a `cmaq` artifact entry with a **composite key** `(project_id, pollutant)` — CMAQ emits one row per project × pollutant, so a single-column key would collapse rows. Tracked fields: `kg_per_day_reduced`, `cost_effectiveness_usd_per_kg`, `eligibility_category`, `nonattainment_area`, `overlay_supplied`. `tests/test_portfolio.py` gains `test_cmaq_surfaces_in_planner_pack_artifacts` regression.
- `tests/test_planner_pack_cmaq.py` — 11-case regression suite: empty rows raise `InsufficientDataError`, invalid `analysis_year` raises `ValueError`, unknown pollutants raise, pollutant aliases normalize (`PM2.5` → `pm2_5`), pollutant filter excludes unselected entries, missing overlay produces no estimates, negative `kg_per_day_reduced` ignored, portfolio totals aggregate by pollutant, fact_blocks pass `qa.is_valid_fact_block` with `method_ref="planner_pack.cmaq"`, end-to-end with and without overlay, idempotent re-run, and missing run raises. `tests/test_qa_gate_planner_pack.py` gains `test_cmaq_passes_qa_gate` and folds CMAQ into the full-stack export-ready test.

### Changed

- **Diff engine gains composite-key support (internal refactor, backward compatible).** `clawmodeler_engine/diff._diff_single_artifact` previously keyed rows by a single column string (`"project_id"`, `"scenario_id"`, etc.); it now also accepts a tuple of columns so artifacts with multi-dimensional rows (CMAQ's project × pollutant; future STIP project × phase × fiscal-year) can be diffed without overwriting duplicate primary-key entries. A new `_row_key` helper joins normalized column values with `|`, and the artifact's `key_column` label is `"+".join(columns)` when the key is composite. All eight existing artifact specs continue to use single-string keys and behave byte-identically; only CMAQ exercises the new path today.

## [0.9.0] — 2026-04-18

### Added

- **Planner Pack: HSIP cycle screen.** New `clawmodeler_engine/planner_pack/hsip.py` + `templates/planner_pack/hsip.md.j2` + `clawmodeler-engine planner-pack hsip --run-id <id> --cycle-year <y> [--cycle-label ...] [--min-bc-ratio 1.0] [--json]` CLI subparser. Screens a finished run's candidate projects against FHWA Highway Safety Improvement Program (HSIP) cycle eligibility (23 USC 148; FHWA HSIP Manual Chapter 3). Reads `runs/<id>/outputs/tables/project_scores.csv` plus an optional `inputs/hsip_overlay.csv` sidecar (per-project `crash_history_5yr`, `fatal_serious_5yr`, `systemic_risk_score`, `benefit_cost_ratio`, `proven_countermeasure`, `proven_countermeasure_citation`, `data_source_ref`); writes `hsip.csv` + `hsip.json` + `reports/<run_id>_hsip.md` + appends `hsip_project_screen` + `hsip_portfolio_summary` fact_blocks with `method_ref="planner_pack.hsip"` — v0.7.1 QA-gate compliant. Projects missing overlay rows are reported as `not yet screened` rather than silently deemed ineligible.
- **Portfolio dashboard + run diff now cover HSIP.** `clawmodeler_engine/portfolio.py` adds `hsip` to its Planner Pack artifact-coverage tuple, so a run with HSIP surfaces alongside the existing five deliverables in the CSV/JSON/Markdown dashboard and the desktop portfolio table. `clawmodeler_engine/diff.py` gains an `hsip` artifact entry (key column `project_id`; tracked fields include `crash_history_5yr`, `fatal_serious_5yr`, `systemic_risk_score`, `benefit_cost_ratio`, `proven_countermeasure`, `overlay_supplied`, `bc_ratio_passes`, `screen_status`) so `clawmodeler-engine diff --run-a ... --run-b ...` can compare HSIP screens between what-if runs. `tests/test_portfolio.py` gains `test_hsip_surfaces_in_planner_pack_artifacts` regression.
- `tests/test_planner_pack_hsip.py` — 11-case regression suite: empty rows raise `InsufficientDataError`, negative `min_bc_ratio` raises `ValueError`, overlay drives B/C pass/fail, missing overlay flags `not yet screened`, overlay without B/C is `awaiting benefit-cost ratio`, portfolio summary aggregates fatal+serious totals and mean B/C, fact_blocks pass `qa.is_valid_fact_block`, end-to-end with and without overlay, idempotent re-run, and missing run raises. `tests/test_qa_gate_planner_pack.py` gains `test_hsip_passes_qa_gate` and folds HSIP into the full-stack export-ready test.

### Changed

- **Planner Pack shared utilities extraction.** New `clawmodeler_engine/planner_pack/utilities.py` module — `append_fact_blocks` (de-duplicated JSONL append, extracted from CEQA), `coerce_str`, `parse_optional_float`, `jinja_env` (Environment factory for the shared template loader), and `validate_fact_block_shape` (emission-time mirror of `qa.is_valid_fact_block` — raises `ValueError` if a block is missing `method_ref` or `artifact_refs`, catching the v0.7.1 bug class at emission rather than export). All five existing Planner Pack modules (`ceqa`, `lapm`, `rtp`, `equity`, `atp`) refactored to import from `utilities`; the five local copies of `_append_fact_blocks`, plus duplicated `_parse_optional_float` / `_coerce_str` / Jinja `Environment` setup blocks, are removed. No user-visible behavior change on the five existing deliverables — every existing planner-pack test passes unchanged — but the single copy makes adding HSIP + CMAQ + STIP in v0.9.x a surgical change.
- `tests/test_planner_pack_utilities.py` — 13-case regression suite covering idempotent append, duplicate `fact_id` skip, empty-input short-circuit, `coerce_str` fallback + trimming, `parse_optional_float` None/empty/non-numeric handling, Jinja environment resolves the existing CEQA template, and `validate_fact_block_shape` accepts well-formed blocks + rejects missing `method_ref` / empty `artifact_refs` / missing `fact_id`.

## [0.8.3] — 2026-04-18

### Fixed

- **Dev-mode Tauri sidecar fallback.** `desktop/src-tauri/src/lib.rs` — `repo_root()` was walking three `.parent()` hops from `CARGO_MANIFEST_DIR` (`desktop/src-tauri`) and landing on the grandparent of the repo root. Fresh checkouts without `pip install -e .` fell back to `python3 -m clawmodeler_engine` with the wrong `current_dir`, so the engine module failed to import. Now correctly walks two hops to the repo root.

### Changed

- **CLI `--json` flag consistency.** `clawmodeler-engine doctor` and `clawmodeler-engine tools` now expose the flag through `dest="as_json"` to match every other subparser (11 commands). Behavior is unchanged — `--json` still produces machine-readable output — and `args.as_json` replaces the previous `args.json` reads inside the two command handlers. Removes accidental shadowing of the `json` module reference and restores uniformity across the CLI surface.

## [0.8.2] — 2026-04-18

### Added

- **Workspace portfolio dashboard.** New `clawmodeler_engine/portfolio.py` module + `clawmodeler-engine portfolio --workspace [--json]` CLI subcommand + desktop "Portfolio" panel (step 7). Summarizes every run in a workspace as one KPI row — `engine_version`, `created_at`, `base_run_id` (what-if lineage), scenario count, project count, mean `total_score`, top-scored project, VMT-flagged count (read from `vmt_screening.csv`), SB 535 DAC share (read from `equity_lens.csv` when present), Planner Pack artifact coverage (`ceqa_vmt`, `lapm_exhibit`, `rtp_chapter`, `equity_lens`, `atp_packet`), QA `export_ready` state, and a `has_what_if_overrides` flag. Writes `portfolio/summary.csv`, `portfolio/summary.json`, `portfolio/fact_blocks.jsonl` (`method_ref="portfolio.run_summary"`, `artifact_refs=[{"path": <summary.csv>, "type": "table"}]` — v0.7.1 QA-gate compliant), and `reports/portfolio.md`. No LLM is called; every cell is read deterministically from a run's shipped artifacts or labeled *not yet available*.
- `clawmodeler_engine/templates/portfolio.md.j2` — Markdown dashboard template with portfolio totals (export-ready ratio, mean score, total VMT flags, mean DAC share, engine versions, lineage edge count), per-run KPI table, and a what-if lineage table linking each what-if run back to its base.
- `tests/test_portfolio.py` — 10-test regression suite: empty workspace raises `InsufficientDataError`, missing `runs/` directory returns `[]`, single-run summary has KPIs, Planner Pack coverage + DAC share surface after `planner-pack equity-lens`, what-if runs surface `base_run_id` + `lineage_edges`, CSV/JSON/Markdown/fact_blocks round-trip, fact_blocks pass `qa.is_valid_fact_block`, scratch directories without manifests are skipped, and `portfolio --json` CLI round-trips.
- `desktop/src-tauri/src/lib.rs` — `clawmodeler_portfolio` Tauri command routing through the shared `run_engine_args` sidecar path; registered alongside the existing six commands.
- `desktop/src/main.ts` + `desktop/src/workbench.ts` + `desktop/src/styles.css` — workspace-level Portfolio panel (step 7). Sortable KPI table (run id, created, engine, base, projects, mean score, VMT flagged, DAC share, Planner Pack, ready), what-if tag for runs produced by `write_what_if`, two-checkbox quick-diff launcher (hard-capped to two selections), "Open" button that switches the workbench's active run id and refreshes artifacts, and a persisted sort-key + direction via localStorage.
- `desktop/src/workbench.test.ts` — 6 new Vitest cases covering `parsePortfolioPayload`, `sortPortfolioRuns` (numeric + string columns, nulls last, stable), `toggleRunSelection` (2-run cap), `validateDiffSelection` (exactly two distinct runs), `buildDiffArgs` shape, and `formatMeanScore`/`formatDacShare` em-dash rendering. 27/27 Vitest pass; Python suite 226/226 pass; ruff clean; `cargo check` clean.

## [0.8.1] — 2026-04-18

### Added

- **What-if desktop panel.** The v0.8.0 CLI `clawmodeler-engine what-if` is now drivable from the Tauri workbench. New "What-if" section (step 6) renders below Chat and includes: base/new run ID inputs, an opt-in scoring-weights block with four sliders (safety / equity / climate / feasibility) that rebalance the other three proportionally to keep the sum at exactly 1.0, reference VMT/capita + CEQA threshold inputs, include/exclude project-id textareas, and a sensitivity-floor dropdown (LOW / MEDIUM / HIGH). Submit validates client-side (sum = 1.0 to 1e-6, no include/exclude overlap, threshold fraction strictly between 0 and 1, at least one override supplied), then invokes the engine via the new Tauri command; on success the workbench's active run id switches to the new run and the artifacts panel refreshes automatically.
- `desktop/src-tauri/src/lib.rs` — `clawmodeler_what_if` Tauri command. Accepts workspace / base_run_id / new_run_id / four optional f64 weights / reference_vmt_per_capita / threshold_pct / include_projects / exclude_projects / sensitivity_floor, validates that the four weights are supplied together or not at all, and composes the `what-if --json` CLI invocation through the shared `run_engine_args` sidecar path. Registered alongside the existing five commands.
- `desktop/src/workbench.ts` — six new pure helpers: `DEFAULT_WHAT_IF_WEIGHTS` (0.30/0.25/0.25/0.20 — California ATP-aligned), `whatIfWeightSum`, `isValidWhatIfWeights`, `rebalanceWhatIfWeights` (clamps to [0,1] and redistributes the remaining three proportionally, with equal-share fallback when the other three sum to zero), `parseProjectIdList`, and `validateWhatIfForm` (returns a discriminated union — `{ok: true, payload}` or `{ok: false, error}` — with friendly human-readable error strings for every rejection path).
- `desktop/src/workbench.test.ts` — 11 new Vitest cases covering: default-weight constants, rebalance preserves sum=1, slider-range clamping, invalid-weight detection, form-level rejection paths (weight sum, same-id, include/exclude overlap, empty overrides, out-of-range threshold), valid weight-only submission round-trip, and `parseProjectIdList` comma/newline handling. 21/21 total Vitest pass; Python suite 216/216 unchanged.

## [0.8.0] — 2026-04-18

### Added

- `clawmodeler_engine/what_if.py` — **What-if simulator.** Deterministic parameter overrides on a finished run: `WhatIfOverrides` (scoring weights, reference VMT per capita, CEQA threshold, project include/exclude, sensitivity floor), `WhatIfResult` (per-project deltas, dropped project ids, scoring weights used), `compute_what_if` (no-side-effect preview), `what_if_fact_blocks` (summary + per-project delta blocks, `method_ref="what_if.parameter_override"`, `artifact_refs=[{"path": str, "type": "table"}]`), `render_what_if_markdown`, and `write_what_if` (re-invokes the full-stack scoring path with overrides, re-filters `project_scores.csv`, rewrites `fact_blocks.jsonl`, stamps the new run's manifest with `base_run_id` + `overrides`, builds a QA report). No LLM is called and no narrative is generated — the grounding covenant is preserved.
- `clawmodeler_engine/templates/what_if.md.j2` — Jinja2 template for the what-if report: applied-overrides list, scoring weights used, per-project deltas table, dropped-project list, citations (Gov Code §65080, CEQA Pub Res Code §21099 + §15064.3, OPR *Technical Advisory* Dec 2018, S&HC §§2380–2383).
- `clawmodeler-engine what-if` CLI subcommand. Flags: `--workspace`, `--base-run-id`, `--new-run-id`, `--weight-safety/equity/climate/feasibility` (must be supplied together and sum to 1.0), `--reference-vmt-per-capita`, `--threshold-pct` (0 < pct < 1), `--include-project` (repeatable), `--exclude-project` (repeatable), `--sensitivity-floor {LOW,MEDIUM,HIGH}`, `--json`.
- `tests/test_what_if.py` — 22-test regression suite: override-validation (weight sum, missing keys, empty overrides, invalid threshold/floor, include/exclude overlap), run creation (base-not-found, collision, weight shift, include/exclude filter, idempotent rerun, same base/new id), QA gate (new run `export_ready: true`, every what-if fact_block passes `qa.is_valid_fact_block`), composition (diff over base vs what-if produces `run_diff_row` blocks, full chain through Planner Pack CEQA + diff + export), manifest round-trip (new 1.1.0 with `base_run_id` + `overrides`, legacy 1.0.0 still validates), fact_block shape.

### Changed

- `clawmodeler_engine/model.py` — Factored the hard-coded scoring weights `0.30 / 0.25 / 0.25 / 0.20` (safety / equity / climate / feasibility) into `DEFAULT_SCORING_WEIGHTS` + `_resolve_scoring_weights` helper. `compute_project_scores` now accepts a `weights=` keyword argument and `run_full_stack` accepts a `scoring_weights=` keyword argument; both default to the original California ATP-aligned values so every existing caller is byte-identical. `what_if.py` is the only new caller that supplies overrides.
- `clawmodeler_engine/contracts.py` — **Manifest schema 1.0.0 → 1.1.0 (additive).** Two optional fields are now stamped by `write_what_if`: `base_run_id: str | None` and `overrides: dict | None`. `CURRENT_MANIFEST_VERSION` is now `"1.1.0"`; a new `LEGACY_MANIFEST_VERSIONS = ("1.0.0",)` tuple records which prior versions remain readable. Existing 1.0.0 manifests continue to validate unchanged; the additive fields are ignored when absent.
- `tests/clawmodeler_engine_test.py` — Bumped the one assertion on `manifest_version` from `"1.0.0"` to `"1.1.0"` to match the new stamp; all other assertions on manifest contents are unchanged.

## [0.7.1] — 2026-04-18

### Fixed

- **QA gate schema for Planner Pack and run-diff fact_blocks.** All Planner Pack emitters shipped in v0.6.0–v0.6.4 (`ceqa`, `lapm`, `rtp`, `equity`, `atp`) and the v0.7.0 run-to-run diff (`diff`) wrote fact_blocks with `source_table` / `source_row` keys but without the `method_ref` (str) and `artifact_refs` (non-empty list) keys that `qa.is_valid_fact_block` requires. The validator rejected every block as invalid, so any run that staged a Planner Pack or diff artifact returned `export_ready: false, blockers: ["fact_blocks_invalid"]` from `build_qa_report` and silently broke `clawmodeler-engine export`. No existing test exercised `export` after a Planner Pack command, which is how the bug reached `main`. Fix is additive: every emitter now sets `method_ref` to a module-specific dotted identifier (`planner_pack.ceqa_vmt`, `planner_pack.lapm_exhibit`, `planner_pack.rtp_chapter`, `planner_pack.equity_lens`, `planner_pack.atp_packet`, `diff.run_to_run`) and `artifact_refs` to a single-element list `[{"path": <source CSV>, "type": "table"}]`. The legacy `source_table` / `source_row` keys are preserved for backward compatibility with any tooling that read them directly. Core engine fact_blocks (project_scores, VMT screening, bridge validation, AI narrative) were unaffected — their existing `method_ref` + `artifact_refs` shape is unchanged.

### Added

- `tests/test_qa_gate_planner_pack.py` — 7-test regression suite: one test per Planner Pack emitter (`ceqa_vmt`, `lapm_exhibit`, `rtp_chapter`, `equity_lens`, `atp_packet`) plus the full-stack composition running all five in one run, each asserting `build_qa_report` returns `export_ready: true` with no blockers; plus one test for `write_run_diff` that reads `diffs/<a>_vs_<b>/fact_blocks.jsonl` directly (diffs don't live under a run tree) and validates every block against `qa.is_valid_fact_block`. These tests would have caught the bug on v0.6.0 and guard against the same schema drift happening again.

## [0.7.0] — 2026-04-18

### Added

- `clawmodeler_engine/diff.py` — **Run-to-run diff** across every shipped engine and Planner Pack artifact. `compute_run_diff`, `run_diff_fact_blocks`, `render_run_diff_markdown`, `write_run_diff`. Reads both runs' `project_scores.csv`, `vmt_screening.csv`, `ceqa_vmt.csv`, `lapm_exhibit.csv`, `rtp_chapter_projects.csv`, `rtp_chapter_scenarios.csv`, `equity_lens.csv`, and `atp_packet.csv` from `outputs/tables/`, classifies each keyed row as **added** / **removed** / **changed** / **unchanged**, and reports numeric deltas on score, VMT, cost, accessibility, and threshold columns. Artifacts that are not present in one or both runs are reported explicitly rather than silently defaulted. Emits per-change `run_diff_row` fact_blocks and per-artifact `run_diff_summary` fact_blocks so downstream narrative and chat turns can cite the differences under the ClawModeler citation contract.
- `clawmodeler_engine/templates/run_diff.md.j2` — Jinja2 template for the diff report: header (run IDs, engine versions, creation timestamps), scope, portfolio of changes table (one row per artifact with added/removed/changed/unchanged counts), per-artifact section with a Markdown table of row-level changes (field-by-field old → new with Δ for numeric columns), citations (Gov Code §65080, Pub Res Code §21099 + CEQA §15064.3, LAPM Chapter 3, S&HC §§2380–2383, Gov Code §39711 + H&S Code §39713), and notes.
- `clawmodeler-engine diff` CLI subcommand. Flags: `--workspace`, `--run-a`, `--run-b`, `--json`. Writes `diffs/<run_a>_vs_<run_b>/diff.csv` (flat one-row-per-field-change), `diff.json`, and `fact_blocks.jsonl`, and renders `reports/<run_a>_vs_<run_b>_diff.md`.
- `tests/test_run_diff.py` — 14 tests covering: identical-run-id rejection, added/removed/changed detection with numeric delta, artifact-presence reporting when one side is absent, unchanged-row counting without listing, empty-key-row filtering, per-row + per-artifact fact_block shape, presence phrase variants (both / only A / only B / neither), end-to-end on two unchanged runs, end-to-end on mutated project_scores, end-to-end with the full Planner Pack staged on both runs, flat CSV one-row-per-field-change check, same-run-id rejection, missing-run error, and idempotent re-runs.

### Changed

- None. v0.7.0 is strictly additive. Existing exports, chat, AI narrative, CEQA VMT, LAPM, RTP chapter, equity lens, ATP packet, and QA behavior are byte-identical to v0.6.4.

## [0.6.4] — 2026-04-18

### Added

- `clawmodeler_engine/planner_pack/atp.py` — **Planner Pack v5**: California Active Transportation Program (ATP) grant application packet generator. Drafts one ATP application per candidate project in a finished run, populated from `project_scores.csv` and enriched when the run already has `lapm_exhibit.csv` (programming fields), `ceqa_vmt.csv` (per-scenario significance collapsed into a run-level CEQA phrase), and `equity_lens.csv` (SB 535 / AB 1550 / tribal benefit category). Projects whose equity-lens benefit category is `DAC`, `Low-income near DAC`, or `Low-income` are flagged as eligible for ATP's disadvantaged-community benefit bonus (`ATP_DAC_SCORING_CATEGORIES`). Emits per-application `atp_application_project` fact_blocks and a portfolio-level `atp_application_summary` fact_block so downstream narrative and chat turns stay under the ClawModeler citation contract. Cites California Streets & Highways Code §§2380–2383, the CTC *Active Transportation Program Guidelines*, Gov Code §39711 (SB 535), H&S Code §39713 (AB 1550), Pub Res Code §21099 + CEQA Guidelines §15064.3, Caltrans LAPM Chapters 3 and 7, and Gov Code §65080 (RTP).
- `clawmodeler_engine/templates/planner_pack/atp_packet.md.j2` — Jinja2 template for the ATP packet: scope, methodology, portfolio summary, per-project application drafts (identifiers, description, benefits scoring table with safety/equity/climate/feasibility and the 30/25/25/20 weighted total, CEQA §15064.3 determination, DAC benefit section with SB 535 / AB 1550 / tribal flags and ATP bonus eligibility, scope/schedule/budget, readiness, RTP consistency, explicit past-performance / letters-of-support placeholder), citations, and notes.
- `clawmodeler-engine planner-pack atp-packet` CLI subcommand. Flags: `--workspace`, `--run-id`, `--agency`, `--cycle`, `--rtp-cycle-label`, `--json`. Writes `atp_packet.csv`, `atp_packet.json`, appends fact_blocks to `fact_blocks.jsonl`, and renders `reports/<run_id>_atp_packet.md`.
- `tests/test_atp_packet.py` — 14 tests covering computation without Planner Pack inputs, LAPM enrichment of programming fields, equity → DAC-eligibility mapping, CEQA per-scenario → run-level significance collapse, RTP cycle label propagation, readiness-note tiers derived from `sensitivity_flag` (LOW / MEDIUM / HIGH), portfolio aggregation (DAC share, mean total score), input validation (empty rows, all-empty project_ids), fact_block shape (per-project + portfolio summary), end-to-end on the demo workspace both without and with the full Planner Pack (CEQA + LAPM + equity overlay), missing-run error, and idempotent re-runs.

### Changed

- None. v0.6.4 is strictly additive. Existing exports, chat, AI narrative, CEQA VMT, LAPM, RTP chapter, equity lens, and QA behavior are byte-identical to v0.6.3.

## [0.6.3] — 2026-04-17

### Added

- `clawmodeler_engine/planner_pack/equity.py` — **Planner Pack v4**: SB 535 / AB 1550 / tribal equity lens overlay. Reads a finished run's `project_scores.csv` and an optional `inputs/equity_overlay.csv` sidecar (columns: `project_id`, `dac_sb535`, `low_income_ab1550`, `low_income_near_dac`, `tribal_area`, `ces_percentile`, `notes`); classifies each project into the AB 1550 benefit category the lead agency would report to CARB (DAC / low-income within ½ mile of DAC / low-income outside the buffer / other / unknown). Projects without an overlay row are reported as **Unknown** rather than silently assumed non-disadvantaged. Computes portfolio shares against the AB 1550 statutory minima (25% DAC, 10% low-income within ½ mile of DAC, 5% low-income outside). Cites Gov Code §39711 (SB 535), H&S Code §39713 (AB 1550), Pub Res Code §§21074 / 21080.3.1–21080.3.2 (AB 52 tribal consultation), CARB *Funding Guidelines for Agencies Administering California Climate Investments*, and OEHHA *CalEnviroScreen 4.0*.
- `clawmodeler_engine/templates/planner_pack/equity_lens.md.j2` — Jinja2 template for the equity packet: scope, methodology, per-project findings table, portfolio summary with AB 1550 target checks, findings split (DAC / low-income near DAC / low-income outside buffer / tribal area / overlay not staged), data sources and limitations, and citations.
- `clawmodeler-engine planner-pack equity-lens` CLI subcommand. Flags: `--workspace`, `--run-id`, `--agency`, `--dataset-note`, `--json`. Writes `equity_lens.csv`, `equity_lens.json`, appends `equity_lens_project` fact_blocks per project and a single `equity_lens_summary` fact_block for the portfolio to `fact_blocks.jsonl`, and renders `reports/<run_id>_equity_lens.md`.
- `tests/test_equity_lens.py` — 12 tests covering benefit-category classification (DAC / low-income near DAC / low-income / other), missing-overlay → Unknown behavior, portfolio shares vs. AB 1550 statutory minima, boolean coercion (true/yes/1/y, case-insensitive), input validation (empty rows, all-empty project_ids), default agency, fact_block shape (per-project + portfolio summary), end-to-end on the demo workspace both without and with a staged overlay, missing-run error, and idempotent re-runs.

### Changed

- None. v0.6.3 is strictly additive. Existing exports, chat, AI narrative, CEQA VMT, LAPM, RTP chapter, and QA behavior are byte-identical to v0.6.2.

## [0.6.2] — 2026-04-17

### Added

- `clawmodeler_engine/planner_pack/rtp.py` — **Planner Pack v3**: RTP *Projects and Performance* chapter generator. Composes a single chapter grounded in a finished run's `project_scores.csv` and `vmt_screening.csv`, and enriches it from `accessibility_delta.csv`, `ceqa_vmt.csv` (v0.6.0), and `lapm_exhibit.csv` (v0.6.1) when those outputs are present. The chapter cites California Government Code §65080, 23 CFR §450.322, the CTC *2017 RTP Guidelines*, CEQA §15064.3, and Caltrans LAPM Chapters 3 & 7.
- `clawmodeler_engine/templates/planner_pack/rtp_chapter.md.j2` — Jinja2 template for the RTP chapter: overview, Action Element project list, Performance Monitoring scenarios table with per-scenario VMT per capita, accessibility delta, CEQA determination, a CEQA findings split (significant vs. less-than-significant), financial + environmental placeholders, and citations.
- `clawmodeler-engine planner-pack rtp-chapter` CLI subcommand. Flags: `--workspace`, `--run-id`, `--agency`, `--rtp-cycle`, `--chapter-title`, `--json`. Writes `rtp_chapter_projects.csv`, `rtp_chapter_scenarios.csv`, `rtp_chapter.json`, appends `rtp_chapter_entry` fact_blocks to `fact_blocks.jsonl`, and renders `reports/<run_id>_rtp_chapter.md`.
- `tests/test_rtp_chapter.py` — 13 tests covering basic composition, CEQA enrichment, LAPM enrichment, accessibility-delta aggregation across zones, zero-population scenarios, input validation (empty scores, empty vmt, all-empty project_ids), fact_block shape, end-to-end on the demo workspace both without and with prior v0.6.0 + v0.6.1 outputs, missing-run error, and idempotent re-runs.

### Changed

- None. v0.6.2 is strictly additive. Existing exports, chat, AI narrative, CEQA VMT, LAPM, and QA behavior are byte-identical to v0.6.1.

## [0.6.1] — 2026-04-17

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

[0.7.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.7.0
[0.6.4]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.4
[0.6.3]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.3
[0.6.2]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.2
[0.6.1]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.1
[0.6.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.6.0
[0.5.1]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.5.1
[0.5.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.5.0
[0.4.1]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.4.1
[0.4.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.4.0
[0.3.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.3.0
[0.2.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.2.0
[0.1.0]: https://github.com/nfredmond/clawmodeler/releases/tag/v0.1.0
