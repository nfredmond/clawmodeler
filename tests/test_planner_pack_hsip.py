from __future__ import annotations

import csv
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    compute_hsip,
    hsip_fact_blocks,
    write_hsip,
)
from clawmodeler_engine.planner_pack.hsip import DEFAULT_CYCLE_LABEL
from clawmodeler_engine.qa import build_qa_report, is_valid_fact_block
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "hsip"):
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


def _stage_hsip_overlay(workspace: Path, run_id: str) -> Path:
    overlay_path = workspace / "inputs" / "hsip_overlay.csv"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    score_path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
    )
    rows: list[dict[str, str]] = []
    with score_path.open("r", encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            pid = row.get("project_id") or ""
            if not pid:
                continue
            rows.append(
                {
                    "project_id": pid,
                    "crash_history_5yr": str(20 + i * 3),
                    "fatal_serious_5yr": str(1 + i),
                    "systemic_risk_score": f"{0.5 + i * 0.1:.2f}",
                    "benefit_cost_ratio": f"{1.5 + i * 0.25:.2f}" if i != 1 else "0.80",
                    "proven_countermeasure": "true" if i != 2 else "false",
                    "proven_countermeasure_citation": (
                        "FHWA Proven Safety Countermeasure — Roundabouts"
                        if i != 2
                        else ""
                    ),
                    "data_source_ref": f"TIMS 2020-2024 crash export row {i}.",
                }
            )
    fieldnames = [
        "project_id",
        "crash_history_5yr",
        "fatal_serious_5yr",
        "systemic_risk_score",
        "benefit_cost_ratio",
        "proven_countermeasure",
        "proven_countermeasure_citation",
        "data_source_ref",
    ]
    with overlay_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    return overlay_path


class ComputeHsipTest(unittest.TestCase):
    def test_empty_rows_raise_insufficient_data(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_hsip([], run_id="x", cycle_year=2027)

    def test_negative_min_bc_ratio_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_hsip(
                [{"project_id": "a", "name": "A", "total_score": "10"}],
                run_id="x",
                cycle_year=2027,
                min_bc_ratio=-0.1,
            )

    def test_overlay_drives_bc_ratio_pass(self) -> None:
        score_rows = [
            {"project_id": "p1", "name": "Project 1", "total_score": "75"},
            {"project_id": "p2", "name": "Project 2", "total_score": "60"},
        ]
        overlay = [
            {
                "project_id": "p1",
                "benefit_cost_ratio": "2.5",
                "fatal_serious_5yr": "3",
                "proven_countermeasure": "true",
            },
            {
                "project_id": "p2",
                "benefit_cost_ratio": "0.7",
                "fatal_serious_5yr": "1",
                "proven_countermeasure": "false",
            },
        ]
        result = compute_hsip(
            score_rows,
            run_id="r",
            cycle_year=2027,
            min_bc_ratio=1.0,
            overlay_rows=overlay,
        )
        by_id = {s.project_id: s for s in result.screens}
        self.assertTrue(by_id["p1"].bc_ratio_passes)
        self.assertEqual(by_id["p1"].screen_status, "eligible")
        self.assertTrue(by_id["p1"].proven_countermeasure)
        self.assertFalse(by_id["p2"].bc_ratio_passes)
        self.assertEqual(by_id["p2"].screen_status, "below minimum B/C")
        self.assertFalse(by_id["p2"].proven_countermeasure)

    def test_missing_overlay_flags_not_yet_screened(self) -> None:
        score_rows = [
            {"project_id": "p1", "name": "P1", "total_score": "10"},
        ]
        result = compute_hsip(score_rows, run_id="r", cycle_year=2027)
        screen = result.screens[0]
        self.assertFalse(screen.overlay_supplied)
        self.assertEqual(screen.screen_status, "not yet screened")
        self.assertIsNone(screen.benefit_cost_ratio)
        self.assertFalse(screen.bc_ratio_passes)

    def test_overlay_without_bc_ratio_is_awaiting(self) -> None:
        score_rows = [{"project_id": "p1", "name": "P1", "total_score": "10"}]
        overlay = [
            {"project_id": "p1", "fatal_serious_5yr": "2"},
        ]
        result = compute_hsip(
            score_rows,
            run_id="r",
            cycle_year=2027,
            overlay_rows=overlay,
        )
        screen = result.screens[0]
        self.assertTrue(screen.overlay_supplied)
        self.assertEqual(screen.screen_status, "awaiting benefit-cost ratio")

    def test_portfolio_summary_aggregates(self) -> None:
        score_rows = [
            {"project_id": "a", "name": "A", "total_score": "50"},
            {"project_id": "b", "name": "B", "total_score": "60"},
        ]
        overlay = [
            {
                "project_id": "a",
                "benefit_cost_ratio": "2.0",
                "fatal_serious_5yr": "2",
                "systemic_risk_score": "0.8",
                "proven_countermeasure": "true",
            },
            {
                "project_id": "b",
                "benefit_cost_ratio": "1.0",
                "fatal_serious_5yr": "4",
                "systemic_risk_score": "0.4",
                "proven_countermeasure": "false",
            },
        ]
        result = compute_hsip(
            score_rows,
            run_id="r",
            cycle_year=2027,
            overlay_rows=overlay,
        )
        summary = result.summary
        assert summary is not None
        self.assertEqual(summary.project_count, 2)
        self.assertEqual(summary.overlay_supplied_count, 2)
        self.assertEqual(summary.bc_ratio_passes_count, 2)
        self.assertEqual(summary.proven_countermeasure_count, 1)
        self.assertEqual(summary.total_fatal_serious_5yr, 6.0)
        self.assertEqual(summary.mean_benefit_cost_ratio, 1.5)


class HsipFactBlockShapeTest(unittest.TestCase):
    def test_blocks_pass_is_valid_fact_block(self) -> None:
        score_rows = [{"project_id": "p1", "name": "P1", "total_score": "10"}]
        overlay = [{"project_id": "p1", "benefit_cost_ratio": "2.0"}]
        result = compute_hsip(
            score_rows,
            run_id="r",
            cycle_year=2027,
            overlay_rows=overlay,
        )
        blocks = hsip_fact_blocks(result, Path("/tmp/hsip.csv"))
        self.assertGreaterEqual(len(blocks), 2)
        fact_types = {b["fact_type"] for b in blocks}
        self.assertIn("hsip_project_screen", fact_types)
        self.assertIn("hsip_portfolio_summary", fact_types)
        for block in blocks:
            self.assertTrue(
                is_valid_fact_block(block),
                f"HSIP fact_block failed QA validator: {block}",
            )
            self.assertEqual(block["method_ref"], "planner_pack.hsip")


class WriteHsipTest(unittest.TestCase):
    def test_end_to_end_without_overlay(self) -> None:
        with demo_workspace() as (workspace, run_id):
            summary = write_hsip(workspace, run_id, cycle_year=2027)
            self.assertGreater(summary["project_count"], 0)
            self.assertEqual(summary["cycle_label"], DEFAULT_CYCLE_LABEL)
            self.assertEqual(summary["overlay_supplied_count"], 0)
            self.assertEqual(summary["bc_ratio_passes_count"], 0)
            self.assertTrue(Path(summary["report_path"]).exists())
            self.assertTrue(Path(summary["csv_path"]).exists())
            self.assertTrue(Path(summary["json_path"]).exists())

    def test_end_to_end_with_overlay_passes_qa_gate(self) -> None:
        with demo_workspace("qahsip") as (workspace, run_id):
            _stage_hsip_overlay(workspace, run_id)
            summary = write_hsip(
                workspace,
                run_id,
                cycle_year=2027,
                cycle_label="HSIP Cycle 12",
                min_bc_ratio=1.0,
            )
            self.assertGreater(summary["overlay_supplied_count"], 0)
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("23 USC 148", report_text)
            self.assertIn("HSIP Cycle 12", report_text)
            payload = json.loads(
                Path(summary["json_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["cycle_year"], 2027)
            self.assertEqual(payload["min_bc_ratio"], 1.0)

            qa = build_qa_report(workspace, run_id)
            self.assertTrue(qa["export_ready"])
            self.assertEqual(qa["blockers"], [])

    def test_idempotent_append(self) -> None:
        with demo_workspace("idem") as (workspace, run_id):
            _stage_hsip_overlay(workspace, run_id)
            first = write_hsip(workspace, run_id, cycle_year=2027)
            second = write_hsip(workspace, run_id, cycle_year=2027)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_hsip(workspace, "no-such-run", cycle_year=2027)


if __name__ == "__main__":
    unittest.main()
