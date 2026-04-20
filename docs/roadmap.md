# ClawModeler Roadmap

This document keeps ClawModeler focused as a standalone, local-first transportation sketch-planning app. The goal is not to add every possible model adapter; the goal is a reproducible planner workflow that makes assumptions, QA blockers, artifacts, and limitations visible.

## End Goal

ClawModeler should let a planner install the desktop app or run `clawmodeler-engine` directly, then complete an auditable screening workflow:

- stage local planning data in a predictable workspace,
- select the strongest method justified by the available data and tools,
- run baseline and alternative scenarios,
- prepare handoff packages for detailed engines such as SUMO, MATSim, UrbanSim, DTALite, and TBEST,
- validate generated artifacts before using them,
- compare runs and portfolio-level results,
- generate Planner Pack artifacts for CEQA, LAPM, RTP, equity, ATP, HSIP, CMAQ, and STIP,
- export reports only from manifests and fact blocks,
- clearly label assumptions, missing data, and screening-level results.

## Current Checkpoint

The current post-0.9.6 checkpoint is a releasable sidecar plus a guided Tauri v2 desktop workbench with hardened release gates and calibrated-model execution readiness:

- `clawmodeler-engine doctor`, `tools`, `workflow full`, `workflow demo-full`, `workflow report-only`, and `workflow diagnose` cover the core workflow.
- Bridge packages are generated and validated for SUMO, MATSim, UrbanSim, DTALite, and TBEST where inputs support them.
- Bridge execution reports are available for SUMO, MATSim, UrbanSim, DTALite, and TBEST commands, including dry-run readiness checks.
- Run manifests, bridge manifests, workflow summaries, reports, and desktop summaries now distinguish handoff-only bridge readiness from calibrated forecast readiness.
- Detailed-engine readiness records method notes, required calibration inputs, required validation targets, and missing readiness blockers.
- Routing choices are controlled through both CLI and desktop workflow surfaces, with diagnostics recorded in workflow reports.
- The tiny public fixture and desktop acceptance gate now prove network-edge routing end to end and record a network-vs-proxy zone-pair comparison without treating it as calibration.
- Intake rejects malformed `network_edges.csv` files, rejects network endpoints that do not join to staged GeoJSON zones, validates `zone_node_map.csv` coverage, and tests a public GraphML routing fixture.
- Bridge execution dry runs and command reports are available from both CLI and desktop surfaces, with generated bridge outputs included in audit reports.
- QA blocks unsupported report export and validates manifest and fact-block evidence.
- Planner Pack emitters cover CEQA VMT, LAPM, RTP, equity, ATP, HSIP, CMAQ, and STIP.
- Diff, what-if, portfolio, and grounded chat are deterministic downstream tools over finished runs.
- The desktop app is vanilla TypeScript on Tauri v2 and invokes only the `clawmodeler-engine` sidecar or local Python fallback.
- The desktop workbench has a top-level Workflow Guide that links workspace setup, run execution, QA/artifact review, Planner Pack generation, grounded chat, what-if, portfolio, and diff readiness.
- The desktop workbench can preview text artifacts locally and the repo has a fixture-backed desktop workflow acceptance gate.
- Release gates smoke-test the packaged sidecar, validate installer asset names, check version consistency, serialize tag publishing, and only mark the highest SemVer tag as Latest.

## Next Engineering Milestones

1. **Turn bridge execution from dry-run confidence into useful operator feedback.**

   Keep execution optional, but improve per-bridge command checks, missing-tool messages, generated-script previews, and report links before attempting deeper external-engine automation.

2. **Persist desktop project state.**

   Add saved recent workspaces, active run history, and explicit run labels so the desktop workbench feels like a durable local app rather than a stateless launcher over files.

3. **Deepen the local data layer.**

   Build on the DuckDB starter sync with stable table schemas, import validation summaries, and queryable run/artifact indexes for portfolio, diff, and desktop summaries.

4. **Add optional ML workflows last.**

   Expose ML libraries through the toolbox only when there is a defined training target, validation set, and model-governance story.

## Rabbit Holes To Avoid

- Do not claim calibrated forecasts from proxy accessibility, VMT, or demand logic.
- Do not hand-tune every external engine option before the starter bridge packages are stable.
- Do not vendor large upstream model source trees into the Python wheel by accident.
- Do not let CLI orchestration, workflow orchestration, desktop routing, and tests become separate versions of the same behavior.
- Do not let AI generate planning evidence; chat and narrative features must stay grounded in shipped artifacts.

## Decision Gates

Proceed to detailed traffic assignment only when the workspace includes a usable network, OD or demand data, and a validation target.

Proceed to transit ridership forecasting only when the workspace includes GTFS, stop or route context, demand drivers, and a validation target.

Proceed to land-use interaction modeling only when the workspace includes land-use inventory, household/job controls, and scenario assumptions.

Proceed to ML or GPU methods only when the workspace includes enough labeled data to validate the model and the report can explain the method plainly.

Proceed to production packaging only when the wheel stays lean, includes required templates, and the desktop sidecar path works outside editable installs.

## Definition Of Done For The Next Pass

The next pass is done when bridge execution reports explain missing tools, generated commands, dry-run readiness, and output files clearly enough that a planner can tell whether they have a handoff package, an executable local engine, or validated detailed-model evidence.
