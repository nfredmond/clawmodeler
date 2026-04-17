from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    DEFAULT_DISTRICT,
    DEFAULT_LEAD_AGENCY,
    compute_lapm_exhibit,
    lapm_fact_blocks,
    write_lapm_exhibit,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "lapm"):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inputs = write_demo_inputs(root)
        workspace = root / "workspace"
        write_intake(
            workspace,
            [
                inputs["zones"],
                inputs["socio"],
                inputs["projects"],
                inputs["network_edges"],
                inputs["gtfs"],
            ],
        )
        write_plan(workspace, inputs["question"])
        write_run(workspace, run_id, ["baseline", "infill-growth"])
        yield workspace, run_id


class ComputeLapmExhibitTest(unittest.TestCase):
    def test_scores_become_exhibits(self) -> None:
        score_rows = [
            {
                "project_id": "p1",
                "name": "Complete Streets",
                "safety_score": "80",
                "equity_score": "70",
                "climate_score": "60",
                "feasibility_score": "90",
                "total_score": "75",
                "sensitivity_flag": "LOW",
            }
        ]
        result = compute_lapm_exhibit(score_rows, run_id="r1")
        self.assertEqual(result.project_count, 1)
        exhibit = result.exhibits[0]
        self.assertEqual(exhibit.project_id, "p1")
        self.assertEqual(exhibit.total_score, 75.0)
        self.assertEqual(exhibit.lead_agency, DEFAULT_LEAD_AGENCY)
        self.assertEqual(exhibit.district, DEFAULT_DISTRICT)
        self.assertIn("Location to be provided", exhibit.location_note)
        self.assertIn("description to be provided", exhibit.description)
        self.assertIsNone(exhibit.estimated_cost_usd)

    def test_sidecar_enriches_location_cost_description(self) -> None:
        score_rows = [
            {
                "project_id": "p1",
                "name": "Complete Streets",
                "safety_score": "80",
                "equity_score": "70",
                "climate_score": "60",
                "feasibility_score": "90",
                "total_score": "75",
                "sensitivity_flag": "LOW",
            }
        ]
        project_rows = [
            {
                "project_id": "p1",
                "lat": "38.001",
                "lon": "-121.002",
                "description": "Add buffered bike lanes on Main Street.",
                "project_type": "Active Transportation",
                "estimated_cost_usd": "2500000",
                "schedule": "PA&ED FY26; PS&E FY27; CON FY28.",
            }
        ]
        result = compute_lapm_exhibit(
            score_rows,
            run_id="r1",
            project_rows=project_rows,
            lead_agency="City of Grass Valley",
            district="District 3",
        )
        exhibit = result.exhibits[0]
        self.assertIn("38.001", exhibit.location_note)
        self.assertIn("-121.002", exhibit.location_note)
        self.assertEqual(exhibit.description, "Add buffered bike lanes on Main Street.")
        self.assertEqual(exhibit.project_type, "Active Transportation")
        self.assertEqual(exhibit.estimated_cost_usd, 2500000.0)
        self.assertIn("FY26", exhibit.schedule_note)
        self.assertEqual(exhibit.lead_agency, "City of Grass Valley")
        self.assertEqual(exhibit.district, "District 3")

    def test_empty_rows_raise(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_lapm_exhibit([], run_id="r1")

    def test_missing_project_id_skipped(self) -> None:
        score_rows = [
            {"project_id": "", "name": "nope", "total_score": "0"},
            {
                "project_id": "ok",
                "name": "OK",
                "safety_score": "50",
                "equity_score": "50",
                "climate_score": "50",
                "feasibility_score": "50",
                "total_score": "50",
                "sensitivity_flag": "HIGH",
            },
        ]
        result = compute_lapm_exhibit(score_rows, run_id="r1")
        self.assertEqual([e.project_id for e in result.exhibits], ["ok"])

    def test_all_empty_project_ids_raises(self) -> None:
        score_rows = [{"project_id": "", "name": "nope"}]
        with self.assertRaises(InsufficientDataError):
            compute_lapm_exhibit(score_rows, run_id="r1")


class LapmFactBlocksTest(unittest.TestCase):
    def test_fact_block_shape(self) -> None:
        score_rows = [
            {
                "project_id": "p1",
                "name": "Complete Streets",
                "safety_score": "80",
                "equity_score": "70",
                "climate_score": "60",
                "feasibility_score": "90",
                "total_score": "75",
                "sensitivity_flag": "LOW",
            }
        ]
        result = compute_lapm_exhibit(score_rows, run_id="r1")
        blocks = lapm_fact_blocks(result, Path("/tmp/lapm_exhibit.csv"))
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block["fact_type"], "lapm_programming_exhibit")
        self.assertEqual(block["fact_id"], "lapm-programming-p1")
        self.assertIn("Caltrans LAPM Chapter 3", block["claim_text"])
        self.assertIn("75.0/100", block["claim_text"])


class WriteLapmExhibitTest(unittest.TestCase):
    def test_end_to_end_on_demo_workspace(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            before = fact_blocks_path.read_text(encoding="utf-8").count("\n")

            summary = write_lapm_exhibit(
                workspace,
                run_id,
                lead_agency="City of Grass Valley",
                district="District 3",
            )

            self.assertGreater(summary["project_count"], 0)
            self.assertGreater(summary["fact_block_count"], 0)
            csv_path = Path(summary["csv_path"])
            json_path = Path(summary["json_path"])
            report_path = Path(summary["report_path"])
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(report_path.exists())

            report_text = report_path.read_text(encoding="utf-8")
            self.assertIn("Caltrans LAPM", report_text)
            self.assertIn("City of Grass Valley", report_text)
            self.assertIn("District 3", report_text)

            after = fact_blocks_path.read_text(encoding="utf-8").count("\n")
            self.assertGreater(after, before)

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["lead_agency"], "City of Grass Valley")
            self.assertEqual(payload["district"], "District 3")
            self.assertGreater(len(payload["exhibits"]), 0)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_lapm_exhibit(workspace, "no-such-run")

    def test_idempotent_fact_block_append(self) -> None:
        with demo_workspace() as (workspace, run_id):
            first = write_lapm_exhibit(workspace, run_id)
            second = write_lapm_exhibit(workspace, run_id)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)


if __name__ == "__main__":
    unittest.main()
