from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    OPR_DEFAULT_THRESHOLD_PCT,
    ceqa_vmt_fact_blocks,
    compute_ceqa_vmt,
    write_ceqa_vmt,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "ceqa"):
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


class ComputeCeqaVmtTest(unittest.TestCase):
    def test_significant_and_below_scenarios(self) -> None:
        rows = [
            {"scenario_id": "hi", "population": 100, "daily_vmt": 2500},
            {"scenario_id": "lo", "population": 100, "daily_vmt": 1500},
        ]
        result = compute_ceqa_vmt(
            rows,
            reference_vmt_per_capita=22.0,
            threshold_pct=0.15,
        )
        self.assertEqual(result.threshold_pct, 0.15)
        self.assertAlmostEqual(result.threshold_vmt_per_capita, 22.0 * 0.85, places=3)
        by_id = {s.scenario_id: s for s in result.scenarios}
        self.assertTrue(by_id["hi"].significant)
        self.assertEqual(by_id["hi"].determination, "potentially significant")
        self.assertTrue(by_id["hi"].mitigation_required)
        self.assertAlmostEqual(by_id["hi"].vmt_per_capita, 25.0, places=3)
        self.assertFalse(by_id["lo"].significant)
        self.assertEqual(by_id["lo"].determination, "less than significant")
        self.assertFalse(by_id["lo"].mitigation_required)
        self.assertAlmostEqual(by_id["lo"].vmt_per_capita, 15.0, places=3)

    def test_at_threshold_is_significant(self) -> None:
        rows = [
            {"scenario_id": "edge", "population": 100, "daily_vmt": 1870.0},
        ]
        result = compute_ceqa_vmt(rows, reference_vmt_per_capita=22.0)
        self.assertTrue(result.scenarios[0].significant)

    def test_zero_population_skipped(self) -> None:
        rows = [
            {"scenario_id": "empty", "population": 0, "daily_vmt": 100},
            {"scenario_id": "ok", "population": 50, "daily_vmt": 500},
        ]
        result = compute_ceqa_vmt(rows, reference_vmt_per_capita=22.0)
        ids = [s.scenario_id for s in result.scenarios]
        self.assertEqual(ids, ["ok"])

    def test_empty_rows_raise_insufficient_data(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_ceqa_vmt([], reference_vmt_per_capita=22.0)

    def test_invalid_project_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_ceqa_vmt(
                [{"scenario_id": "a", "population": 10, "daily_vmt": 10}],
                reference_vmt_per_capita=22.0,
                project_type="industrial",
            )

    def test_invalid_reference_label_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_ceqa_vmt(
                [{"scenario_id": "a", "population": 10, "daily_vmt": 10}],
                reference_vmt_per_capita=22.0,
                reference_label="global",
            )

    def test_invalid_threshold_pct_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_ceqa_vmt(
                [{"scenario_id": "a", "population": 10, "daily_vmt": 10}],
                reference_vmt_per_capita=22.0,
                threshold_pct=1.5,
            )

    def test_negative_reference_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_ceqa_vmt(
                [{"scenario_id": "a", "population": 10, "daily_vmt": 10}],
                reference_vmt_per_capita=-1.0,
            )

    def test_default_threshold_matches_opr(self) -> None:
        self.assertAlmostEqual(OPR_DEFAULT_THRESHOLD_PCT, 0.15)


class CeqaFactBlocksTest(unittest.TestCase):
    def test_fact_block_shape(self) -> None:
        rows = [
            {"scenario_id": "hi", "population": 100, "daily_vmt": 2500},
            {"scenario_id": "lo", "population": 100, "daily_vmt": 1500},
        ]
        result = compute_ceqa_vmt(rows, reference_vmt_per_capita=22.0)
        blocks = ceqa_vmt_fact_blocks(result, Path("/tmp/ceqa_vmt.csv"))
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            self.assertEqual(block["fact_type"], "ceqa_vmt_determination")
            self.assertTrue(block["fact_id"].startswith("ceqa-vmt-"))
            self.assertIn("CEQA §15064.3", block["claim_text"])
            self.assertIn(block["source_table"], "/tmp/ceqa_vmt.csv")
        by_scenario = {b["scenario_id"]: b for b in blocks}
        self.assertIn("potentially significant", by_scenario["hi"]["claim_text"])
        self.assertIn("less than significant", by_scenario["lo"]["claim_text"])


class WriteCeqaVmtTest(unittest.TestCase):
    def test_end_to_end_on_demo_workspace(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            before = fact_blocks_path.read_text(encoding="utf-8").count("\n")

            summary = write_ceqa_vmt(
                workspace,
                run_id,
                reference_vmt_per_capita=22.0,
                threshold_pct=0.15,
            )

            self.assertGreater(summary["scenario_count"], 0)
            self.assertGreater(summary["fact_block_count"], 0)
            csv_path = Path(summary["csv_path"])
            json_path = Path(summary["json_path"])
            report_path = Path(summary["report_path"])
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(report_path.exists())

            report_text = report_path.read_text(encoding="utf-8")
            self.assertIn("CEQA §15064.3", report_text)
            self.assertIn(run_id, report_text)

            after = fact_blocks_path.read_text(encoding="utf-8").count("\n")
            self.assertGreater(after, before)

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["project_type"], "residential")
            self.assertEqual(payload["reference_label"], "regional")
            self.assertGreater(len(payload["scenarios"]), 0)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_ceqa_vmt(workspace, "no-such-run")

    def test_reference_falls_back_to_analysis_plan(self) -> None:
        with demo_workspace() as (workspace, run_id):
            summary = write_ceqa_vmt(workspace, run_id)
            self.assertGreater(summary["reference_vmt_per_capita"], 0.0)

    def test_idempotent_fact_block_append(self) -> None:
        with demo_workspace() as (workspace, run_id):
            first = write_ceqa_vmt(workspace, run_id, reference_vmt_per_capita=22.0)
            second = write_ceqa_vmt(workspace, run_id, reference_vmt_per_capita=22.0)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)


if __name__ == "__main__":
    unittest.main()
