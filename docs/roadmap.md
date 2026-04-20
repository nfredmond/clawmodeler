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

The current post-0.9.5 checkpoint is a releasable sidecar plus a guided Tauri v2 desktop workbench with hardened release gates and calibrated-model execution readiness:

- `clawmodeler-engine doctor`, `tools`, `workflow full`, `workflow demo-full`, `workflow report-only`, and `workflow diagnose` cover the core workflow.
- Bridge packages are generated and validated for SUMO, MATSim, UrbanSim, DTALite, and TBEST where inputs support them.
- Run manifests, bridge manifests, workflow summaries, reports, and desktop summaries now distinguish handoff-only bridge readiness from calibrated forecast readiness.
- Detailed-engine readiness records method notes, required calibration inputs, required validation targets, and missing readiness blockers.
- QA blocks unsupported report export and validates manifest and fact-block evidence.
- Planner Pack emitters cover CEQA VMT, LAPM, RTP, equity, ATP, HSIP, CMAQ, and STIP.
- Diff, what-if, portfolio, and grounded chat are deterministic downstream tools over finished runs.
- The desktop app is vanilla TypeScript on Tauri v2 and invokes only the `clawmodeler-engine` sidecar or local Python fallback.
- The desktop workbench has a top-level Workflow Guide that links workspace setup, run execution, QA/artifact review, Planner Pack generation, grounded chat, what-if, portfolio, and diff readiness.
- The desktop workbench can preview text artifacts locally and the repo has a fixture-backed desktop workflow acceptance gate.
- The release workflow smoke-tests the packaged sidecar, validates installer asset names, serializes tag publishing, and only marks the highest SemVer tag as Latest.

## Next Engineering Milestones

1. **Harden fixture and bridge confidence.**

   Expand the tiny public fixture only when it improves acceptance coverage, then improve bridge validation messages before adding deeper external-engine execution.

2. **Upgrade the data/routing engine.**

   Make DuckDB spatial ingestion and deeper OSMnx/NetworkX routing controls the next core data-path upgrade.

3. **Add optional ML workflows last.**

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

The next pass is done when the fixture and acceptance coverage prove the calibrated-readiness language stays intact across CLI, bridge validation, reports, and desktop surfaces while bridge-package messaging remains concise and planner-readable.
