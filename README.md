# ClawModeler

[![CI](https://github.com/nfredmond/clawmodeler/actions/workflows/ci.yml/badge.svg)](https://github.com/nfredmond/clawmodeler/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

ClawModeler is a standalone, local-first transportation sketch-planning workbench. It helps a planner go from raw transportation data to reproducible scenario outputs, QA-gated evidence, and report-ready narratives without uploading project files to a cloud service.

The long-term goal is an installable desktop app plus `clawmodeler-engine` sidecar where planners can inspect local tools, select defensible methods, run workflows, validate outputs, compare alternatives, and generate Planner Pack artifacts with every limitation visible.

For the big-picture roadmap and scope guardrails, see `docs/roadmap.md`.

## Download

Pre-built desktop installers are attached to every [GitHub release](https://github.com/nfredmond/clawmodeler/releases/latest). Free for all platforms.

| Platform | Installer |
|---|---|
| Linux (any distro) | `ClawModeler_<version>_amd64.AppImage` |
| Debian / Ubuntu | `ClawModeler_<version>_amd64.deb` |
| Fedora / RHEL | `ClawModeler-<version>-1.x86_64.rpm` |
| macOS Apple Silicon (M1/M2/M3/M4) | `ClawModeler_<version>_aarch64.dmg` |
| Windows 10 / 11 | `ClawModeler_<version>_x64_en-US.msi` or `ClawModeler_<version>_x64-setup.exe` |

**Intel Mac (x86_64):** no pre-built installer at this time. GitHub's `macos-13` hosted-runner pool is being deprecated and is unreliable for release builds. Intel Mac users can build from source (see Quick Start), or wait for a self-hosted Intel runner in a future release.

### First-run on macOS or Windows (unsigned builds)

ClawModeler currently ships without Apple or Microsoft code-signing certificates to keep every platform free. The first launch needs a one-time bypass:

- **macOS:** Right-click `ClawModeler.app` → **Open** → **Open** (Gatekeeper remembers it afterwards).
- **Windows:** SmartScreen dialog → **More info** → **Run anyway**.

Code signing is planned for a future release.

## What It Does

ClawModeler coordinates:

- data intake for zones, socioeconomic tables, GTFS, project lists, and model handoff files,
- method selection based on available data and installed tools,
- scenario transforms for baseline and alternatives,
- accessibility analysis,
- VMT and climate screening,
- transit schedule metrics,
- project scoring,
- bridge exports for heavier transportation models,
- reproducibility manifests,
- fact-block evidence,
- QA-gated report export.

Current analysis outputs are intentionally labeled as screening-level when proxy methods are used. The stack is built so detailed engines can replace or augment those proxy methods without changing the user-facing workflow.

## Quick Start

Most users should grab a [release installer](#download) instead. These steps are for developers who want to run from source.

Clone and install the Python engine:

```bash
git clone https://github.com/nfredmond/clawmodeler
cd clawmodeler
python3 -m pip install -e .
clawmodeler-engine doctor
clawmodeler-engine tools
clawmodeler-engine --help
```

Run the built-in demo:

```bash
clawmodeler-engine init --workspace ./demo-workspace
clawmodeler-engine demo --workspace ./demo-workspace
```

Run the sidecar tests:

```bash
pnpm engine:test
```

Run a workspace:

```bash
clawmodeler-engine workflow full \
  --workspace ./demo-workspace \
  --inputs zones.geojson socio.csv network_edges.csv projects.csv feed.zip \
  --question question.json \
  --run-id demo \
  --scenarios baseline scenario-a

clawmodeler-engine workflow demo-full \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine workflow report-only \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine workflow diagnose \
  --workspace ./demo-workspace
```

Or run each stage manually:

```bash
clawmodeler-engine intake \
  --workspace ./demo-workspace \
  --inputs zones.geojson socio.csv projects.csv feed.zip

clawmodeler-engine plan \
  --workspace ./demo-workspace \
  --question question.json

clawmodeler-engine run \
  --workspace ./demo-workspace \
  --run-id demo \
  --scenarios baseline scenario-a

clawmodeler-engine export \
  --workspace ./demo-workspace \
  --run-id demo \
  --format md

clawmodeler-engine bridge sumo prepare \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine bridge sumo validate \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine bridge matsim prepare \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine bridge urbansim prepare \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine bridge prepare-all \
  --workspace ./demo-workspace \
  --run-id demo

clawmodeler-engine bridge validate \
  --workspace ./demo-workspace \
  --run-id demo
```

Prepare an OSMnx graph cache when the standard profile is installed:

```bash
clawmodeler-engine graph osmnx \
  --workspace ./demo-workspace \
  --place "Davis, California, USA" \
  --network-type drive \
  --graph-id davis-drive

clawmodeler-engine graph map-zones \
  --workspace ./demo-workspace
```

Direct sidecar access is also available:

```bash
python3 -m clawmodeler_engine --help
```

## Agent Workflow

Agents should follow this sequence:

1. Run `clawmodeler-engine doctor --json`.
2. Run `clawmodeler-engine tools --json`.
3. Inspect available runtimes, Python modules, local engine source trees, model inventory, profiles, and method policy.
4. Choose the strongest defensible method available.
5. Prefer `workflow full` when the user wants the whole job handled end to end.
6. Use `workflow diagnose` when data, tools, or next steps are unclear.
7. Otherwise run intake validation.
8. Write a `question.json` that records scenarios and assumptions.
9. Run planning and modeling.
10. Prepare bridge packages with `bridge prepare-all`, or use specific commands such as `bridge sumo prepare`, `bridge matsim prepare`, or `bridge urbansim prepare`.
11. Validate bridge packages with commands such as `bridge sumo validate` or `bridge validate`.
12. Inspect `qa_report.json`.
13. Export only if QA passes.
14. Summarize outputs by citing artifacts and limitations.

Agents must not invent data, silently bypass QA, or present screening-level outputs as detailed engineering forecasts.

## Inputs

Useful inputs include:

- GeoJSON zones with `properties.zone_id`,
- socioeconomic CSV with `zone_id`, `population`, and `jobs`,
- candidate project CSV with `project_id`, `name`, `safety`, `equity`, `climate`, and `feasibility`,
- optional network edge CSV with `from_zone_id`, `to_zone_id`, and `minutes`,
- optional zone-to-node map CSV with `zone_id` and `node_id` for GraphML networks,
- GTFS zip feeds,
- optional OSM/network inputs,
- optional OD matrices,
- optional local model handoff files.

If required data is missing, ClawModeler should either run a reduced analysis with explicit limitations or ask for the missing data.

## Workspace Layout

Each workspace follows this contract:

```text
workspace/
  project.duckdb
  inputs/
  cache/
    graphs/
    gtfs/
  runs/
    <run_id>/
      manifest.json
      qa_report.json
      outputs/
        tables/
        maps/
        figures/
        bridges/
  reports/
  logs/
```

The manifest records inputs, hashes, methods, scenarios, assumptions, output artifacts, and engine selection. The QA report records whether export is allowed.

## Max Toolbox

The toolbox is declared in `clawmodeler_toolbox.json` and surfaced through:

```bash
clawmodeler-engine tools
clawmodeler-engine tools --json
clawmodeler-engine doctor --json
```

It includes:

- runtimes: Python, Java, Docker,
- GIS: DuckDB, GDAL/OGR, GeoPandas, Shapely, pyproj,
- routing: NetworkX, OSMnx,
- transit: GTFS tooling, R5 bridge target, TBEST tools,
- simulation: SUMO, MATSim,
- assignment: DTALite,
- land use: UrbanSim,
- optimization: OR-Tools, CVXPY, PuLP,
- ML: scikit-learn, PyTorch, XGBoost, LightGBM, transformers,
- reporting: Pandoc, Graphviz, Office/PDF helpers.

Local transportation model directories may exist next to this repository or in a larger modeling workspace:

```text
matsim-libs/
sumo/
urbansim/
DTALite/
tbest-tools/
```

Do not package them accidentally. Agents should treat them as local modeling engines or bridge targets when present, while keeping the ClawModeler Python wheel lean.

## Install Profiles

Python dependency profiles are provided:

```text
clawmodeler-requirements-light.txt
clawmodeler-requirements-standard.txt
clawmodeler-requirements-full.txt
clawmodeler-requirements-gpu.txt
```

Install a profile:

```bash
bash scripts/install-profile.sh standard
```

Profiles:

- `light`: fast screening, DuckDB, table handling, basic geometry, report templating.
- `standard`: GIS, OSM routing, GTFS, plotting, Excel/Word/PDF helpers.
- `full`: simulation, matrix, optimization, bridge libraries, SUMO Python tooling.
- `gpu`: full plus PyTorch and ML libraries.

The GPU profile is optional. ML tools are powerful, but they require training data, validation, and clear limitations before their outputs can support planning claims.

## Method Policy

ClawModeler agents should choose methods like this:

- Quick screening or incomplete data: use DuckDB/GIS/NetworkX/OSMnx when available, otherwise use proxy screening and label limitations.
- Transit accessibility with GTFS: prefer R5 and Java when available; otherwise compute GTFS route metrics and stop-access proxies.
- Corridor or intersection operations: prefer SUMO; otherwise create a SUMO bridge export.
- Agent-based simulation: prefer MATSim and Java; otherwise create a MATSim bridge export.
- Land-use interaction: prefer UrbanSim; otherwise create a bridge export and request development inputs.
- Dynamic traffic assignment: use DTALite bridge workflows when OD matrices and network inputs exist.
- Emissions: use VMT screening for early planning and create a MOVES export for defensible detailed emissions work.
- ML: use only as exploratory or validated modeling when training and validation data exist.

## QA Rules

Report export is blocked unless:

- `manifest.json` exists,
- `qa_report.json` exists,
- `fact_blocks.jsonl` exists,
- at least one fact-block is present,
- narrative claims are grounded.

Blocked exports write:

```text
reports/<run_id>_export_blocked.md
```

## Current Status

Implemented now:

- CLI surface: `clawmodeler-engine ...`,
- sidecar CLI commands: `doctor`, `tools`, `demo`, `intake`, `plan`, `run`, `export`,
- one-command demo workspace generation and report export,
- network edge CSV shortest-path accessibility with a built-in Dijkstra fallback,
- GraphML cache shortest-path accessibility from `cache/graphs/*.graphml`,
- OSMnx-style GraphML parsing for `travel_time` seconds and `length`/`speed_kph`,
- OSMnx GraphML cache builder command,
- GraphML zone-to-node mapping command,
- workspace folder creation,
- input staging and validation,
- scenario transforms,
- proxy accessibility metrics,
- VMT and CO2e screening,
- GTFS route metrics,
- project scoring,
- fact-block generation,
- QA-gated Markdown export,
- QA-gated PDF export when the `pdf` optional dependency set is installed,
- bridge manifests for SUMO, MATSim, UrbanSim, DTALite, and TBEST,
- Planner Pack artifacts for CEQA VMT, LAPM, RTP, equity, ATP, HSIP, CMAQ, and STIP,
- run-to-run diff, what-if runs, grounded chat, and portfolio summaries,
- Tauri v2 desktop workbench with a vanilla TypeScript front end,
- toolbox inventory and install profiles.

Still to build:

- real DuckDB spatial ingestion path as the default,
- deeper OSMnx/NetworkX routing controls,
- R5 transit accessibility execution,
- SUMO network/demand conversion and execution,
- MATSim population/plans conversion,
- UrbanSim scenario adapter,
- DTALite assignment adapter,
- MOVES export package,
- DOCX report rendering,
- packaged install profiles for desktop and containers.

## Verification

Useful checks:

```bash
pnpm engine:test
bash scripts/check-packaging.sh
clawmodeler-engine doctor --json
clawmodeler-engine tools
```
