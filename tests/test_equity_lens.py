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
    BENEFIT_CATEGORIES,
    DEFAULT_EQUITY_AGENCY,
    compute_equity_lens,
    equity_lens_fact_blocks,
    write_equity_lens,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "equity"):
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


def _stage_overlay(workspace: Path, rows: list[dict[str, str]]) -> Path:
    overlay_path = workspace / "inputs" / "equity_overlay.csv"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "project_id",
        "dac_sb535",
        "low_income_ab1550",
        "low_income_near_dac",
        "tribal_area",
        "ces_percentile",
        "notes",
    ]
    with overlay_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return overlay_path


SCORE_ROWS: list[dict[str, str]] = [
    {
        "project_id": "p1",
        "name": "Downtown DAC bike lanes",
        "safety_score": "80",
        "equity_score": "90",
        "climate_score": "70",
        "feasibility_score": "60",
        "total_score": "78",
        "sensitivity_flag": "LOW",
    },
    {
        "project_id": "p2",
        "name": "Adjacent low-income transit upgrades",
        "safety_score": "70",
        "equity_score": "80",
        "climate_score": "60",
        "feasibility_score": "75",
        "total_score": "72",
        "sensitivity_flag": "LOW",
    },
    {
        "project_id": "p3",
        "name": "Rural tribal-area road safety",
        "safety_score": "65",
        "equity_score": "70",
        "climate_score": "55",
        "feasibility_score": "50",
        "total_score": "63",
        "sensitivity_flag": "MEDIUM",
    },
    {
        "project_id": "p4",
        "name": "Suburban corridor retrofit",
        "safety_score": "55",
        "equity_score": "45",
        "climate_score": "50",
        "feasibility_score": "60",
        "total_score": "52",
        "sensitivity_flag": "HIGH",
    },
]


class ComputeEquityLensTest(unittest.TestCase):
    def test_benefit_category_classification(self) -> None:
        overlay_rows = [
            {
                "project_id": "p1",
                "dac_sb535": "true",
                "low_income_ab1550": "true",
                "low_income_near_dac": "true",
                "tribal_area": "false",
                "ces_percentile": "92.5",
                "notes": "CalEnviroScreen 4.0 pctl 92.5 — SB 535 DAC.",
            },
            {
                "project_id": "p2",
                "dac_sb535": "false",
                "low_income_ab1550": "true",
                "low_income_near_dac": "true",
                "tribal_area": "false",
                "ces_percentile": "58",
                "notes": "Low-income tract within 1/2 mi of DAC.",
            },
            {
                "project_id": "p3",
                "dac_sb535": "false",
                "low_income_ab1550": "true",
                "low_income_near_dac": "false",
                "tribal_area": "true",
                "ces_percentile": "45",
                "notes": "Tribal land; low-income outside 1/2-mi buffer.",
            },
            {
                "project_id": "p4",
                "dac_sb535": "false",
                "low_income_ab1550": "false",
                "low_income_near_dac": "false",
                "tribal_area": "false",
                "ces_percentile": "",
                "notes": "Not SB 535, not AB 1550.",
            },
        ]
        result = compute_equity_lens(
            SCORE_ROWS,
            run_id="r1",
            overlay_rows=overlay_rows,
            agency="NCTC",
        )
        by_id = {f.project_id: f for f in result.findings}
        self.assertEqual(by_id["p1"].benefit_category, "DAC")
        self.assertEqual(by_id["p2"].benefit_category, "Low-income near DAC")
        self.assertEqual(by_id["p3"].benefit_category, "Low-income")
        self.assertEqual(by_id["p4"].benefit_category, "Other")
        self.assertEqual(by_id["p1"].ces_percentile, 92.5)
        self.assertTrue(by_id["p3"].tribal_area)
        for f in result.findings:
            self.assertIn(f.benefit_category, BENEFIT_CATEGORIES)
            self.assertTrue(f.overlay_supplied)

    def test_missing_overlay_yields_unknown(self) -> None:
        result = compute_equity_lens(SCORE_ROWS, run_id="r1")
        for f in result.findings:
            self.assertEqual(f.benefit_category, "Unknown")
            self.assertFalse(f.overlay_supplied)
            self.assertFalse(f.dac_sb535)
            self.assertIsNone(f.ces_percentile)
            self.assertIn("lead agency", f.notes.lower())
        assert result.summary is not None
        self.assertEqual(result.summary.unknown_count, 4)
        self.assertEqual(result.summary.dac_count, 0)
        self.assertFalse(result.summary.ab1550_dac_target_met)

    def test_portfolio_shares_and_targets(self) -> None:
        overlay_rows = [
            {
                "project_id": pid,
                "dac_sb535": "true" if pid == "p1" else "false",
                "low_income_ab1550": "true" if pid in ("p2",) else "false",
                "low_income_near_dac": "true" if pid == "p2" else "false",
                "tribal_area": "false",
                "ces_percentile": "",
                "notes": "",
            }
            for pid in ("p1", "p2", "p3", "p4")
        ]
        result = compute_equity_lens(
            SCORE_ROWS,
            run_id="r1",
            overlay_rows=overlay_rows,
        )
        summary = result.summary
        assert summary is not None
        self.assertEqual(summary.project_count, 4)
        self.assertEqual(summary.dac_count, 1)
        self.assertEqual(summary.low_income_near_dac_count, 1)
        self.assertEqual(summary.low_income_count, 0)
        self.assertEqual(summary.unknown_count, 0)
        self.assertEqual(summary.dac_share, 0.25)
        self.assertEqual(summary.low_income_near_dac_share, 0.25)
        self.assertTrue(summary.ab1550_dac_target_met)
        self.assertTrue(summary.ab1550_low_income_near_dac_target_met)
        self.assertFalse(summary.ab1550_low_income_target_met)

    def test_bool_coercion_accepts_common_truthy_values(self) -> None:
        overlay_rows = [
            {
                "project_id": "p1",
                "dac_sb535": "Yes",
                "low_income_ab1550": "1",
                "low_income_near_dac": "Y",
                "tribal_area": "TRUE",
                "ces_percentile": "",
                "notes": "",
            }
        ]
        result = compute_equity_lens(
            [SCORE_ROWS[0]],
            run_id="r1",
            overlay_rows=overlay_rows,
        )
        finding = result.findings[0]
        self.assertTrue(finding.dac_sb535)
        self.assertTrue(finding.low_income_ab1550)
        self.assertTrue(finding.low_income_near_dac)
        self.assertTrue(finding.tribal_area)

    def test_empty_rows_raises(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_equity_lens([], run_id="r1")

    def test_all_empty_project_ids_raises(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_equity_lens(
                [{"project_id": "", "name": "x"}], run_id="r1"
            )

    def test_default_agency_used_when_not_supplied(self) -> None:
        result = compute_equity_lens(SCORE_ROWS, run_id="r1")
        self.assertEqual(result.agency, DEFAULT_EQUITY_AGENCY)


class EquityLensFactBlocksTest(unittest.TestCase):
    def test_per_project_and_summary_blocks(self) -> None:
        overlay_rows = [
            {
                "project_id": "p1",
                "dac_sb535": "true",
                "low_income_ab1550": "",
                "low_income_near_dac": "",
                "tribal_area": "",
                "ces_percentile": "",
                "notes": "DAC per CES 4.0.",
            }
        ]
        result = compute_equity_lens(
            [SCORE_ROWS[0]], run_id="r1", overlay_rows=overlay_rows
        )
        blocks = equity_lens_fact_blocks(result, Path("/tmp/equity_lens.csv"))
        self.assertEqual(len(blocks), 2)
        project_block = blocks[0]
        summary_block = blocks[1]
        self.assertEqual(project_block["fact_type"], "equity_lens_project")
        self.assertEqual(project_block["fact_id"], "equity-lens-project-p1")
        self.assertIn("SB 535 DAC", project_block["claim_text"])
        self.assertEqual(summary_block["fact_type"], "equity_lens_summary")
        self.assertEqual(summary_block["fact_id"], "equity-lens-summary")
        self.assertIn("100.0%", summary_block["claim_text"])


class WriteEquityLensTest(unittest.TestCase):
    def test_end_to_end_without_overlay(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            before = fact_blocks_path.read_text(encoding="utf-8").count("\n")

            summary = write_equity_lens(
                workspace,
                run_id,
                agency="Nevada County Transportation Commission",
            )

            self.assertGreater(summary["project_count"], 0)
            self.assertEqual(summary["overlay_supplied_count"], 0)
            self.assertGreater(summary["fact_block_count"], 0)
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("Equity Lens", report_text)
            self.assertIn("Nevada County Transportation Commission", report_text)
            self.assertIn("Unknown", report_text)

            after = fact_blocks_path.read_text(encoding="utf-8").count("\n")
            self.assertGreater(after, before)

    def test_end_to_end_with_overlay(self) -> None:
        with demo_workspace() as (workspace, run_id):
            score_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
            )
            with score_path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertGreater(len(rows), 0)
            overlay_rows = []
            for i, row in enumerate(rows):
                pid = row.get("project_id") or ""
                if not pid:
                    continue
                overlay_rows.append(
                    {
                        "project_id": pid,
                        "dac_sb535": "true" if i == 0 else "false",
                        "low_income_ab1550": "true" if i in (0, 1) else "false",
                        "low_income_near_dac": "true" if i == 1 else "false",
                        "tribal_area": "true" if i == 2 else "false",
                        "ces_percentile": "85" if i == 0 else "",
                        "notes": f"Overlay row {i}.",
                    }
                )
            _stage_overlay(workspace, overlay_rows)

            summary = write_equity_lens(workspace, run_id)
            portfolio = summary["summary"]
            self.assertIsNotNone(portfolio)
            assert portfolio is not None
            self.assertEqual(
                portfolio["project_count"], summary["overlay_supplied_count"]
            )
            self.assertGreaterEqual(portfolio["dac_count"], 1)

            payload = json.loads(
                Path(summary["json_path"]).read_text(encoding="utf-8")
            )
            categories = {
                f["project_id"]: f["benefit_category"] for f in payload["findings"]
            }
            self.assertIn("DAC", categories.values())
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("Portfolio summary", report_text)
            self.assertIn("Citations", report_text)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_equity_lens(workspace, "no-such-run")

    def test_idempotent_fact_block_append(self) -> None:
        with demo_workspace() as (workspace, run_id):
            first = write_equity_lens(workspace, run_id)
            second = write_equity_lens(workspace, run_id)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)


if __name__ == "__main__":
    unittest.main()
