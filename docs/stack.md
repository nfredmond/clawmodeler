# ClawModeler Stack

ClawModeler is a local-first transportation sketch-planning stack. The current implementation centers on the Python sidecar `clawmodeler-engine` plus a Tauri v2 desktop workbench with a vanilla TypeScript front end. The sidecar stages inputs, chooses a screening engine, runs local analysis, writes reproducibility artifacts, gates report export, prepares handoff folders for heavier transportation modeling engines, and emits Planner Pack artifacts.

For the product-level overview, start with `README.md`. For the sequencing plan and rabbit-hole guardrails, see `docs/roadmap.md`.

## Sidecar Commands

Run the sidecar through the package scripts:

```bash
pnpm engine -- --version
pnpm engine:test
```

Or run the installed console script directly:

```bash
clawmodeler-engine doctor
clawmodeler-engine tools
clawmodeler-engine init --workspace ./demo
clawmodeler-engine workflow demo-full --workspace ./demo --run-id demo
clawmodeler-engine workflow full --workspace ./demo --inputs zones.geojson socio.csv --question question.json --run-id demo
clawmodeler-engine planner-pack ceqa-vmt --workspace ./demo --run-id demo
clawmodeler-engine portfolio --workspace ./demo --json
```

## Internal Structure

The CLI and end-to-end workflows share the same core stage functions:

- `clawmodeler_engine/orchestration.py` owns intake, planning, engine selection, run manifest creation, calibrated-readiness stamping, QA-gated export, and report writing.
- `clawmodeler_engine/workflow.py` composes those shared stages into full, demo, report-only, and diagnose workflows.
- `clawmodeler_engine/cli.py` parses command-line arguments and prints concise JSON command results.
- `clawmodeler_engine/readiness.py` centralizes detailed-engine forecast-readiness rules, evidence discovery, and blocker summaries.
- `clawmodeler_engine/report.py` renders Markdown reports from manifests and fact-block artifacts.
- `desktop/src-tauri/src/lib.rs` exposes the sidecar to the desktop shell.
- `desktop/src/workbench.ts` owns browser-safe UI helpers and shared client-side validation.

New workflow behavior should be added to the shared orchestration layer first, then exposed through CLI or workflow wrappers. This keeps manual commands and `workflow full` aligned.

## Workspace Contract

Each workspace follows the plan contract:

- `inputs/` contains staged user inputs.
- `cache/graphs/` is reserved for OSMnx GraphML caches.
- `cache/gtfs/` is reserved for transit feed cache material.
- `runs/{run_id}/manifest.json` records inputs, hashes, methods, assumptions, scenarios, outputs, engine selection, and `detailed_engine_readiness`.
- `runs/{run_id}/qa_report.json` records export gate status.
- `runs/{run_id}/outputs/tables/` contains CSV and JSONL outputs.
- `runs/{run_id}/outputs/bridges/` contains external engine handoff manifests, each with `forecast_readiness` when applicable.
- `reports/` contains exported reports.

Core JSON artifacts are versioned with `schema_version` and `artifact_type`. The sidecar validates these contracts in `clawmodeler_engine/contracts.py` before writing or loading key artifacts. Current contract-covered artifacts include:

- `question`
- `intake_receipt`
- `analysis_plan`
- `engine_selection`
- `run_manifest`
- `qa_report`
- `bridge_manifest`
- `bridge_prepare_report`
- `bridge_validation_report`
- `bridge_execution_report`
- `workflow_report`
- `workflow_diagnosis`

When the Python `duckdb` module is installed, the sidecar creates `project.duckdb` and syncs staged zones, socioeconomic rows, projects, network edges, zone-node maps, run scenarios, and fact blocks into starter relational tables. If DuckDB is absent, it writes an explicit missing-dependency note beside the database path and continues with file-backed artifacts.

## Implemented Analysis Modules

The current stack implements these plan modules:

- Intake: stages GeoJSON, CSV, GTFS zip, Shapefile placeholders, and unknown files for audit.
- Model Brain: writes `analysis_plan.json` and `engine_selection.json`.
- Scenario Lab: applies scenario-level population and jobs multipliers plus per-zone deltas.
- Accessibility Engine: writes 15, 30, and 45 minute cumulative jobs-accessible outputs using a Euclidean proxy travel-time method.
- Accessibility Engine: uses staged `network_edges.csv` shortest paths when available, then `cache/graphs/*.graphml`, otherwise falls back to Euclidean proxy travel times.
- Accessibility Engine: supports optional `question.routing` controls for `auto`, `network_edges_csv`, `graphml`, or `euclidean_proxy` routing source selection.
- Intake validates `network_edges.csv` endpoint IDs and positive travel-time minutes against staged GeoJSON zones.
- Workflow reports include a routing QA diagnostic that compares selected network shortest paths with straight-line proxy travel times between staged zone centroids, including reachable-pair coverage. This is a screening comparison, not calibration.
- VMT & Climate: writes screening VMT and CO2e estimates using explicit per-capita and emissions-factor assumptions.
- Transit Analyzer: validates GTFS core files and writes route span, trip count, and frequency metrics.
- Project Scoring: writes weighted safety, equity, climate, and feasibility scores.
- Narrative Engine: exports Markdown only when QA confirms manifest and fact-block evidence are present.
- Bridge Exports: creates MATSim, SUMO, UrbanSim, DTALite, and TBEST handoff manifests.
- Calibrated-model execution gates: record whether each detailed-engine package is handoff-only, calibration-required, or validation-ready based on project-specific evidence.
- SUMO Bridge: generates and validates SUMO plain node, edge, trip, config, and shell script files from staged zone-level network and demand inputs.
- MATSim Bridge: generates MATSim network, population, config, and shell script files from staged zone-level network and demand inputs.
- UrbanSim Bridge: generates zone, household, job, building, and config tables from staged zone-level socioeconomic inputs.
- DTALite Bridge: generates node, link, demand, and settings files from staged zone-level network and demand inputs.
- TBEST Bridge: generates stop, route, service, and config tables from staged GTFS inputs.
- Bridge Prepare All: prepares every applicable bridge package and records skipped packages with reasons.
- Bridge Validation: writes a combined bridge validation report across prepared external-engine packages and separates structural package readiness from detailed forecast readiness.
- Bridge Execution: writes execution reports for SUMO, MATSim, UrbanSim, DTALite, and TBEST bridge commands, with dry-run support, tool checks, generated-command previews, expected-output summaries, operator next steps, and forecast-readiness limitations preserved.
- Planner Pack: writes CEQA VMT, LAPM, RTP, equity, ATP, HSIP, CMAQ, and STIP artifacts from finished runs.
- What-if: derives a new run from a baseline with deterministic overrides.
- Diff: compares two runs across engine and Planner Pack tables.
- Portfolio: summarizes every run in a workspace.
- Grounded chat and AI narrative: downstream only, with fact-block citation validation.

## Desktop Workbench

The desktop app is a Tauri v2 shell around the sidecar. In packaged builds it invokes the bundled `clawmodeler-engine` binary; in development it falls back to `python3 -m clawmodeler_engine` from the repo root. The Vite dev middleware mirrors the Tauri command routes so browser development and desktop development exercise the same workflow surfaces.

The current planner-facing flow is guided by a top-level Workflow Guide. It links to the existing panels and derives readiness from the active workspace, run artifacts, QA report, workflow report, Planner Pack coverage, chat state, what-if state, and portfolio/diff selections. Recent workspaces, active run history, and planner-facing run labels are persisted locally in the desktop workbench:

1. Pick or create a workspace.
2. Run the built-in demo or a full workflow.
3. Review QA readiness, bridge package readiness, detailed forecast readiness, bridge generated-file counts, manifest path, generated artifacts, warnings, and sidecars.
4. Preview the report.
5. Generate Planner Pack artifacts.
6. Preview generated text artifacts.
7. Ask grounded chat questions about a finished run.
8. Create what-if runs.
9. Refresh the portfolio and diff two runs.

The fixture-backed acceptance gate for this flow is:

```bash
pnpm desktop:acceptance
```

The release-specific sidecar gate is:

```bash
pnpm release:sidecar-smoke
```

Release asset names and Latest-release policy are checked by `scripts/check-release-assets.mjs` and `scripts/release-latest-policy.mjs`.

The accessibility and VMT modules are intentionally labeled as screening-level. They are ready to be replaced or augmented with OSMnx/NetworkX, R5, MOVES, and detailed engine outputs without changing the CLI contract. Until project-specific calibration inputs, validation targets, model year, geography, and method notes are recorded, detailed-engine bridge packages remain handoff artifacts rather than authoritative forecasts.

When OSMnx is installed, `openclaw clawmodeler graph osmnx` can build a GraphML cache in `cache/graphs/`. The accessibility engine can consume GraphML cache files with edge `minutes`, `travel_time_min`, `travel_time_minutes`, OSMnx-style `travel_time` seconds, or `length` plus `speed_kph` values. Run `openclaw clawmodeler graph map-zones` after intake to generate and register `inputs/zone_node_map.csv` from staged zones and GraphML node coordinates, or stage a CSV with `zone_id,node_id` columns when a custom mapping is required. Intake requires staged zone-node maps to cover the staged GeoJSON zones. Use `question.routing.graph_id` to pin a named GraphML cache; `question.routing.impedance` currently supports `minutes` only.

## Max Toolbox

`clawmodeler_toolbox.json` is the machine-readable inventory agents use to decide what they can run. It includes runtime, GIS, routing, transit, simulation, optimization, ML, reporting, and packaging tools.

Use:

```bash
openclaw clawmodeler tools
openclaw clawmodeler tools --json
openclaw clawmodeler doctor --json
```

Install profiles are declared as requirement files:

- `clawmodeler-requirements-light.txt`
- `clawmodeler-requirements-standard.txt`
- `clawmodeler-requirements-full.txt`
- `clawmodeler-requirements-gpu.txt`

Install one with:

```bash
bash scripts/clawmodeler/install-profile.sh standard
```

The `gpu` profile includes PyTorch and other ML tooling. It should be used for validated or exploratory ML-assisted modeling, not as a substitute for calibrated transportation model evidence.

## Local Modeling Engines

These local directories are intentional modeling resources for agents:

- `matsim-libs/`: MATSim bridge target for agent-based simulation exports.
- `sumo/`: SUMO bridge target for microscopic operations simulation.
- `urbansim/`: UrbanSim bridge target for land-use and transportation interaction workflows.
- `DTALite/`: DTALite bridge target for dynamic traffic assignment workflows.
- `tbest-tools/`: TBEST bridge target for stop-level transit ridership workflows.

Do not delete or treat these directories as accidental untracked files. The sidecar records their presence in `runs/{run_id}/outputs/bridges/*/bridge_manifest.json`.

## QA Gate

Report export is blocked unless:

- `manifest.json` exists,
- `fact_blocks.jsonl` exists,
- at least one fact-block is present,
- narrative claim coverage is zero-missing.

Blocked exports write `reports/{run_id}_export_blocked.md` and exit with code `40`.
