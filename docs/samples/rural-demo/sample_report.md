
# ClawModeler Technical Report

- Run ID: `rural-demo`
- Generated: `2026-04-22T05:30:08Z`
- Engine version: `0.9.6`
- Routing engine: `osmnx_networkx`
- QA status: **READY**




## Methods

- `intake`
- `model_brain`
- `scenario_lab`
- `accessibility_engine`
- `vmt_climate`
- `transit_analyzer`
- `project_scoring`
- `narrative_engine`
- `bridge_exports`


## Scenarios

| Scenario | Name | Population × | Jobs × |
|---|---|---|---|
| `baseline` | Current Conditions | 1.0 | 1.0 |
| `infill-growth` | Infill Growth | 1.08 | 1.18 |



## Evidence (fact-blocks)

| Fact ID | Type | Scenario | Claim | Method |
|---|---|---|---|---|
| `access-baseline` | `accessibility` | `baseline` | Scenario baseline has a maximum proxy jobs-accessible value of 2600. | `accessibility.euclidean_proxy` |
| `access-infill-growth` | `accessibility` | `infill-growth` | Scenario infill-growth has a maximum proxy jobs-accessible value of 3368. | `accessibility.euclidean_proxy` |
| `access-delta-infill-growth` | `accessibility_delta` | `infill-growth` | Scenario infill-growth changes summed proxy jobs access by 6081. | `accessibility.delta` |
| `vmt-baseline` | `vmt_screening` | `baseline` | Scenario baseline has screening daily VMT of 53200. | `vmt.per_capita_proxy` |
| `vmt-infill-growth` | `vmt_screening` | `infill-growth` | Scenario infill-growth has screening daily VMT of 62206. | `vmt.per_capita_proxy` |
| `transit-r10` | `transit` | `—` | Route r10 has 3 GTFS trips in the staged feed. | `transit.gtfs_schedule` |
| `score-top-ranked` | `project_scoring` | `—` | Southgate Trail Connector is the top-ranked scoring row with a total score of 77.6. | `scoring.weighted_rubric` |
| `figure-vmt-by-scenario` | `figure_vmt_screening` | `—` | Screening daily VMT per scenario visualized as a bar chart. | `figure.vmt_bar` |
| `figure-vmt-co2e-trend` | `figure_vmt_co2e` | `—` | Dual-axis chart of daily VMT and CO2e by scenario. | `figure.vmt_co2e_trend` |
| `figure-access-delta` | `figure_accessibility_delta` | `—` | Accessibility delta vs. baseline summarized per scenario. | `figure.access_delta_bar` |
| `figure-project-scores` | `figure_project_scores` | `—` | Top project scores from the weighted rubric. | `figure.project_score_bar` |
| `figure-access-hist-baseline` | `figure_accessibility_distribution` | `baseline` | Distribution of jobs-accessible values for scenario baseline. | `figure.access_histogram` |
| `figure-access-hist-infill-growth` | `figure_accessibility_distribution` | `infill-growth` | Distribution of jobs-accessible values for scenario infill-growth. | `figure.access_histogram` |
| `map-population` | `map_population` | `—` | Population choropleth across the study-area zones. | `map.population_choropleth` |
| `map-vmt` | `map_vmt` | `—` | Screening daily VMT choropleth by zone (population × per-capita proxy). | `map.vmt_proxy_choropleth` |
| `map-access-baseline` | `map_accessibility` | `baseline` | Jobs-accessible choropleth for scenario baseline. | `map.access_choropleth` |
| `map-access-infill-growth` | `map_accessibility` | `infill-growth` | Jobs-accessible choropleth for scenario infill-growth. | `map.access_choropleth` |
| `ceqa-vmt-baseline` | `ceqa_vmt_determination` | `baseline` | Under CEQA §15064.3, scenario baseline VMT per capita is 19.0 — less than significant, 10.6% below the 15%-below-regional threshold of 21.2 VMT/capita. | `planner_pack.ceqa_vmt` |
| `ceqa-vmt-infill-growth` | `ceqa_vmt_determination` | `infill-growth` | Under CEQA §15064.3, scenario infill-growth VMT per capita is 19.0 — less than significant, 10.6% below the 15%-below-regional threshold of 21.2 VMT/capita. | `planner_pack.ceqa_vmt` |



## Figures

### Vmt By Scenario

![Vmt By Scenario](runs/rural-demo/outputs/figures/vmt_by_scenario.png)

### Vmt Co2E Trend

![Vmt Co2E Trend](runs/rural-demo/outputs/figures/vmt_co2e_trend.png)

### Access Delta By Scenario

![Access Delta By Scenario](runs/rural-demo/outputs/figures/access_delta_by_scenario.png)

### Project Score Distribution

![Project Score Distribution](runs/rural-demo/outputs/figures/project_score_distribution.png)

### Accessibility Hist Baseline

![Accessibility Hist Baseline](runs/rural-demo/outputs/figures/accessibility_hist_baseline.png)

### Accessibility Hist Infill-Growth

![Accessibility Hist Infill-Growth](runs/rural-demo/outputs/figures/accessibility_hist_infill-growth.png)



## Interactive maps

- [Population By Zone](runs/rural-demo/outputs/maps/population_by_zone.html)
- [Vmt By Zone](runs/rural-demo/outputs/maps/vmt_by_zone.html)
- [Access Baseline](runs/rural-demo/outputs/maps/access_baseline.html)
- [Access Infill-Growth](runs/rural-demo/outputs/maps/access_infill-growth.html)


## Assumptions and limitations

- Accessibility uses staged network_edges.csv shortest paths.
- Proxy accessibility speed is 45.0 kph.
- VMT screening uses 19.0 daily VMT per capita unless overridden.
- Emissions screening uses 0.404 kg CO2e per VMT unless overridden.
- Bridge packages may be ready for handoff and structural validation while detailed forecast readiness remains blocked until project-specific calibration inputs, validation targets, and method notes are recorded.


## QA report

- Manifest present: `True`
- Fact-blocks present: `True`
- Fact-block count: `19`
- Export allowed: `True`


## Artifact inventory

### bridges

- `runs/rural-demo/outputs/bridges/matsim/bridge_manifest.json`
- `runs/rural-demo/outputs/bridges/sumo/bridge_manifest.json`
- `runs/rural-demo/outputs/bridges/urbansim/bridge_manifest.json`
- `runs/rural-demo/outputs/bridges/dtalite/bridge_manifest.json`
- `runs/rural-demo/outputs/bridges/tbest/bridge_manifest.json`

### figures

- `runs/rural-demo/outputs/figures/vmt_by_scenario.png`
- `runs/rural-demo/outputs/figures/vmt_co2e_trend.png`
- `runs/rural-demo/outputs/figures/access_delta_by_scenario.png`
- `runs/rural-demo/outputs/figures/project_score_distribution.png`
- `runs/rural-demo/outputs/figures/accessibility_hist_baseline.png`
- `runs/rural-demo/outputs/figures/accessibility_hist_infill-growth.png`

### maps

- `runs/rural-demo/outputs/maps/population_by_zone.html`
- `runs/rural-demo/outputs/maps/vmt_by_zone.html`
- `runs/rural-demo/outputs/maps/access_baseline.html`
- `runs/rural-demo/outputs/maps/access_infill-growth.html`

### tables

- `runs/rural-demo/outputs/tables/accessibility_by_zone.csv`
- `runs/rural-demo/outputs/tables/accessibility_delta.csv`
- `runs/rural-demo/outputs/tables/vmt_screening.csv`
- `runs/rural-demo/outputs/tables/transit_metrics_by_route.csv`
- `runs/rural-demo/outputs/tables/project_scores.csv`
- `runs/rural-demo/outputs/tables/fact_blocks.jsonl`
- `runs/rural-demo/outputs/tables/scenario_diff_summary.csv`



## Bridge Packages

| Engine | Package status | Forecast readiness | Notes |
|---|---|---|---|
| `dtalite` | `ready_for_dtalite` | `handoff_only` | demand rows: 6 |
| `matsim` | `ready_for_matsim` | `handoff_only` | persons: 28 |
| `sumo` | `ready_for_netconvert` | `handoff_only` | trips: 84, bridge QA ready: True |
| `tbest` | `ready_for_tbest` | `handoff_only` | routes: 1 |
| `urbansim` | `ready_for_urbansim` | `handoff_only` | households: 750, jobs: 1300 |


### dtalite readiness

- Status: **Handoff only**
- Summary: dtalite is currently a handoff package only. ClawModeler does not have project-specific calibration and validation evidence recorded for authoritative forecast claims.

- Missing readiness blockers:
  - model_year_missing
  - calibration_geography_missing
  - method_notes_missing
  - calibration_inputs_missing
  - validation_targets_missing
  - missing_calibration_inputs:traffic_counts,od_seed_matrix,capacity_controls
  - missing_validation_targets:link_volumes,travel_times


### matsim readiness

- Status: **Handoff only**
- Summary: matsim is currently a handoff package only. ClawModeler does not have project-specific calibration and validation evidence recorded for authoritative forecast claims.

- Missing readiness blockers:
  - model_year_missing
  - calibration_geography_missing
  - method_notes_missing
  - calibration_inputs_missing
  - validation_targets_missing
  - missing_calibration_inputs:od_seed_or_survey,counts_or_screenlines,population_controls
  - missing_validation_targets:mode_share,screenline_or_link_counts


### sumo readiness

- Status: **Handoff only**
- Summary: sumo is currently a handoff package only. ClawModeler does not have project-specific calibration and validation evidence recorded for authoritative forecast claims.

- Missing readiness blockers:
  - model_year_missing
  - calibration_geography_missing
  - method_notes_missing
  - calibration_inputs_missing
  - validation_targets_missing
  - missing_calibration_inputs:observed_counts,network_controls,demand_controls
  - missing_validation_targets:travel_times,delay_or_queue


### tbest readiness

- Status: **Handoff only**
- Summary: tbest is currently a handoff package only. ClawModeler does not have project-specific calibration and validation evidence recorded for authoritative forecast claims.

- Missing readiness blockers:
  - model_year_missing
  - calibration_geography_missing
  - method_notes_missing
  - calibration_inputs_missing
  - validation_targets_missing
  - missing_calibration_inputs:observed_ridership,service_context,fare_or_network_notes
  - missing_validation_targets:route_boardings,stop_boardings


### urbansim readiness

- Status: **Handoff only**
- Summary: urbansim is currently a handoff package only. ClawModeler does not have project-specific calibration and validation evidence recorded for authoritative forecast claims.

- Missing readiness blockers:
  - model_year_missing
  - calibration_geography_missing
  - method_notes_missing
  - calibration_inputs_missing
  - validation_targets_missing
  - missing_calibration_inputs:land_use_inventory,household_controls,job_controls
  - missing_validation_targets:household_totals,job_totals






---

*ClawModeler is a screening-level planning workbench. Outputs labeled "screening" are not substitutes for detailed engineering analysis.*

