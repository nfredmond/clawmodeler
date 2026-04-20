---
summary: "CLI reference for ClawModeler transportation sketch-planning workflows"
read_when:
  - You want to run ClawModeler workspace, demo, workflow, Planner Pack, bridge, graph, what-if, diff, portfolio, or chat commands
  - You need the `clawmodeler-engine` Python sidecar entrypoint
title: "clawmodeler-engine"
---

# `clawmodeler-engine`

Run ClawModeler transportation sketch-planning workflows through the local Python sidecar. Outputs are screening-level unless a workspace includes calibrated model inputs, validation evidence, and method notes that support a detailed analysis tier.

## Common Commands

```bash
clawmodeler-engine doctor
clawmodeler-engine tools --json
clawmodeler-engine init --workspace ./demo
clawmodeler-engine demo --workspace ./demo --run-id demo
```

## Workflow Commands

```bash
clawmodeler-engine workflow full \
  --workspace ./demo \
  --inputs zones.geojson socio.csv network_edges.csv projects.csv feed.zip \
  --question question.json \
  --run-id demo \
  --scenarios baseline scenario-a \
  --routing-source auto \
  --routing-impedance minutes

clawmodeler-engine workflow demo-full --workspace ./demo --run-id demo
clawmodeler-engine workflow report-only --workspace ./demo --run-id demo
clawmodeler-engine workflow diagnose --workspace ./demo --run-id demo
```

## Stage Commands

```bash
clawmodeler-engine intake --workspace ./demo --inputs zones.geojson socio.csv
clawmodeler-engine plan --workspace ./demo --question question.json
clawmodeler-engine run --workspace ./demo --run-id demo --scenarios baseline scenario-a
clawmodeler-engine export --workspace ./demo --run-id demo --format md
```

`export --format` currently supports `md` and `pdf`. PDF requires the optional `pdf` dependency set.

## Planner Pack Commands

```bash
clawmodeler-engine planner-pack ceqa-vmt --workspace ./demo --run-id demo
clawmodeler-engine planner-pack lapm-exhibit --workspace ./demo --run-id demo
clawmodeler-engine planner-pack rtp-chapter --workspace ./demo --run-id demo
clawmodeler-engine planner-pack equity-lens --workspace ./demo --run-id demo
clawmodeler-engine planner-pack atp-packet --workspace ./demo --run-id demo
clawmodeler-engine planner-pack hsip --workspace ./demo --run-id demo --cycle-year 2027
clawmodeler-engine planner-pack cmaq --workspace ./demo --run-id demo --analysis-year 2027
clawmodeler-engine planner-pack stip --workspace ./demo --run-id demo
```

## Comparison Commands

```bash
clawmodeler-engine what-if \
  --workspace ./demo \
  --base-run-id demo \
  --new-run-id demo-safety \
  --weight-safety 0.4 \
  --weight-equity 0.25 \
  --weight-climate 0.2 \
  --weight-feasibility 0.15

clawmodeler-engine diff --workspace ./demo --run-a demo --run-b demo-safety --json
clawmodeler-engine portfolio --workspace ./demo --json
```

## Grounded Chat

```bash
clawmodeler-engine chat \
  --workspace ./demo \
  --run-id demo \
  --message "Which projects drove the VMT result?" \
  --json
```

Chat and AI narrative calls are downstream of a finished run. Every sentence must cite a real `fact_id` or it is blocked/dropped by the deterministic grounding gate.

## Bridge Commands

```bash
clawmodeler-engine bridge prepare-all --workspace ./demo --run-id demo
clawmodeler-engine bridge validate --workspace ./demo --run-id demo
clawmodeler-engine bridge sumo prepare --workspace ./demo --run-id demo
clawmodeler-engine bridge sumo execute --workspace ./demo --run-id demo --dry-run
clawmodeler-engine bridge matsim prepare --workspace ./demo --run-id demo
clawmodeler-engine bridge matsim execute --workspace ./demo --run-id demo --dry-run
clawmodeler-engine bridge urbansim prepare --workspace ./demo --run-id demo
```

`workflow full`, `workflow demo-full`, `workflow report-only`, `workflow diagnose`, `bridge prepare-all`, and `bridge validate` now emit stable readiness summaries for detailed engines. Structural bridge-package readiness can pass while `detailed_forecast_ready` remains false if calibration inputs, validation targets, model year, geography, or method notes are missing.

`bridge <engine> execute` writes `bridge_execution_report.json` for SUMO, MATSim, UrbanSim, DTALite, and TBEST. Use `--dry-run` to validate execution readiness without running the command. Execution status only confirms that the external command ran; calibrated forecast claims still require validation-ready detailed-engine evidence.

## Graph Commands

```bash
clawmodeler-engine graph osmnx \
  --workspace ./demo \
  --place "Davis, California, USA"

clawmodeler-engine graph map-zones --workspace ./demo
```

Runs may optionally set `question.routing`:

```json
{
  "routing": {
    "source": "auto",
    "graph_id": "davis-drive",
    "impedance": "minutes"
  }
}
```

Supported `source` values are `auto`, `network_edges_csv`, `graphml`, and `euclidean_proxy`. `minutes` is the only supported impedance in this pass.

## Notes

- `doctor` and `tools` inspect local Python modules, external binaries, and model bridge directories.
- Report export is blocked when ClawQA cannot find a manifest or valid fact-block evidence.
- Direct module access is available with `python3 -m clawmodeler_engine --help`.

See `docs/stack.md` for workspace contracts, analysis modules, bridge packages, and install profiles.
