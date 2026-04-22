# ClawModeler Starter Template

A minimum viable input set for a brand-new ClawModeler project. Replace the zeros and example rows with your own data before running the workflow.

## Files

- **`zones.geojson`** — your project's zones as GeoJSON polygons. Each feature needs a `properties.zone_id` string. Real-world sources: TAZ layers from your MPO or RTPA, census block groups from TIGER, or planning boundaries drawn in QGIS.
- **`socio.csv`** — population and jobs per zone. Must include columns `zone_id`, `population`, `jobs`. Every `zone_id` here must also appear in `zones.geojson`. Real-world sources: ACS 5-year estimates, LEHD LODES for jobs, your local agency's adopted control totals.
- **`projects.csv`** — candidate projects with scoring rubric inputs. Must include columns `project_id`, `name`, `safety`, `equity`, `climate`, `feasibility`. Scores are 0–100; higher means better. Real-world sources: your project list from the regional transportation plan (RTP), active transportation plan (ATP), or grant application portfolio.

## Optional

Any of these can be added without breaking the required-inputs workflow:

- **`network_edges.csv`** — zone-to-zone travel times, columns `from_zone_id`, `to_zone_id`, `minutes`. Produces real accessibility metrics instead of Euclidean proxies.
- **GTFS ZIP** — any valid GTFS feed. Produces transit route metrics and stop-access proxies. Most agencies publish a GTFS feed; check the [TransitLand](https://www.transit.land/) catalog if you're unsure.
- **`question.json`** — an analysis-plan declaration. ClawModeler will generate a starter one from the desktop app, so you typically don't write this by hand.

## Minimum run

Once you've filled in the three required files:

```bash
clawmodeler-engine workflow full \
  --workspace ./my-project \
  --inputs zones.geojson socio.csv projects.csv \
  --question question.json \
  --run-id first-run \
  --scenarios baseline
```

Or, equivalently, use the desktop app's **Run Full Workflow** button after pointing it at your folder.

## Limits

This template is deliberately small. It will run end-to-end, but every output will be labeled screening-level and will carry the limitations baked into three zones of synthetic data. Use it to test the pipeline, not to draw policy conclusions.
