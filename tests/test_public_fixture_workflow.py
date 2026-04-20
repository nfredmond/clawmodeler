from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawmodeler_engine.diff import write_run_diff
from clawmodeler_engine.planner_pack import write_ceqa_vmt
from clawmodeler_engine.portfolio import write_portfolio
from clawmodeler_engine.what_if import WhatIfOverrides, write_what_if
from clawmodeler_engine.workflow import run_full_workflow
from clawmodeler_engine.workspace import read_json

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tiny_region"


class PublicFixtureWorkflowTest(unittest.TestCase):
    def test_tiny_region_runs_full_planner_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "tiny-region"
            workflow_path = run_full_workflow(
                workspace,
                input_paths=[
                    FIXTURE / "zones.geojson",
                    FIXTURE / "socio.csv",
                    FIXTURE / "projects.csv",
                    FIXTURE / "network_edges.csv",
                ],
                question_path=FIXTURE / "question.json",
                run_id="baseline",
                scenarios=["baseline", "station-growth"],
                prepare_bridges=True,
            )

            workflow = read_json(workflow_path)
            self.assertTrue(workflow["qa"]["export_ready"])
            self.assertTrue(workflow["bridge_validation"]["export_ready"])
            self.assertTrue((workspace / "reports" / "baseline_report.md").exists())

            bridge_prepare = workflow["bridges"]
            self.assertEqual(
                {item["bridge"] for item in bridge_prepare["prepared"]},
                {"sumo", "matsim", "urbansim", "dtalite"},
            )
            skipped = {item["bridge"]: item for item in bridge_prepare["skipped"]}
            self.assertEqual(skipped["tbest"]["missing_inputs"], ["gtfs_zip"])
            for item in bridge_prepare["prepared"]:
                generated_files = item.get("generated_files", [])
                self.assertGreater(len(generated_files), 0)
                self.assertTrue(any(Path(path).exists() for path in generated_files))

            ceqa = write_ceqa_vmt(workspace, "baseline")
            self.assertTrue(Path(ceqa["report_path"]).exists())

            _, what_if = write_what_if(
                workspace,
                "baseline",
                "safety-heavy",
                WhatIfOverrides(
                    scoring_weights={
                        "safety": 0.4,
                        "equity": 0.25,
                        "climate": 0.2,
                        "feasibility": 0.15,
                    }
                ),
            )
            self.assertEqual(what_if.base_run_id, "baseline")
            self.assertEqual(what_if.new_run_id, "safety-heavy")

            diff = write_run_diff(workspace, "baseline", "safety-heavy")
            self.assertTrue(Path(diff["report_path"]).exists())

            portfolio = write_portfolio(workspace)
            self.assertEqual(portfolio["run_count"], 2)
            self.assertTrue(Path(portfolio["report_path"]).exists())


if __name__ == "__main__":
    unittest.main()
