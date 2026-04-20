#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python3}"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/clawmodeler-desktop-accept.XXXXXX")"

cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

workspace="$work_dir/workspace"
fixture="$repo_root/tests/fixtures/tiny_region"

export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"

echo "Running desktop workflow acceptance against tiny_region fixture"
"$python_bin" -m clawmodeler_engine workflow full \
  --workspace "$workspace" \
  --inputs \
    "$fixture/zones.geojson" \
    "$fixture/socio.csv" \
    "$fixture/projects.csv" \
    "$fixture/network_edges.csv" \
  --question "$fixture/question.json" \
  --run-id baseline \
  --scenarios baseline station-growth

"$python_bin" -m clawmodeler_engine planner-pack ceqa-vmt \
  --workspace "$workspace" \
  --run-id baseline \
  --json >/dev/null

"$python_bin" -m clawmodeler_engine what-if \
  --workspace "$workspace" \
  --base-run-id baseline \
  --new-run-id safety-heavy \
  --weight-safety 0.40 \
  --weight-equity 0.25 \
  --weight-climate 0.20 \
  --weight-feasibility 0.15 \
  --json >/dev/null

"$python_bin" -m clawmodeler_engine diff \
  --workspace "$workspace" \
  --run-a baseline \
  --run-b safety-heavy \
  --json >/dev/null

"$python_bin" -m clawmodeler_engine portfolio \
  --workspace "$workspace" \
  --json >/dev/null

"$python_bin" - "$workspace" <<'PY'
from pathlib import Path
import json
import sys

workspace = Path(sys.argv[1])
workflow = json.loads((workspace / "runs" / "baseline" / "workflow_report.json").read_text())
bridge_validation = workflow["bridge_validation"]
portfolio = json.loads((workspace / "portfolio" / "summary.json").read_text())

required_files = [
    workspace / "reports" / "baseline_report.md",
    workspace / "reports" / "baseline_ceqa_vmt.md",
    workspace / "reports" / "baseline_vs_safety-heavy_diff.md",
    workspace / "reports" / "portfolio.md",
    workspace / "runs" / "baseline" / "manifest.json",
    workspace / "runs" / "baseline" / "qa_report.json",
    workspace / "runs" / "safety-heavy" / "manifest.json",
]
missing = [str(path) for path in required_files if not path.exists()]
if missing:
    raise SystemExit(f"missing acceptance files: {missing}")

if not workflow["qa"]["export_ready"]:
    raise SystemExit("QA export readiness was false")
if not bridge_validation["export_ready"]:
    raise SystemExit("bridge export readiness was false")
if portfolio["run_count"] != 2:
    raise SystemExit(f"expected 2 portfolio runs, got {portfolio['run_count']}")

prepared = {item["bridge"] for item in workflow["bridges"]["prepared"]}
if prepared != {"sumo", "matsim", "urbansim", "dtalite"}:
    raise SystemExit(f"unexpected prepared bridges: {sorted(prepared)}")

print("Desktop workflow acceptance passed.")
PY
