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
    ATP_DAC_SCORING_CATEGORIES,
    DEFAULT_ATP_AGENCY,
    DEFAULT_ATP_CYCLE,
    atp_grant_fact_blocks,
    compute_atp_packet,
    write_atp_packet,
    write_ceqa_vmt,
    write_equity_lens,
    write_lapm_exhibit,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "atp"):
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


def _stage_equity_overlay(workspace: Path) -> None:
    overlay_path = workspace / "inputs" / "equity_overlay.csv"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    score_path = (
        workspace / "runs" / "atp" / "outputs" / "tables" / "project_scores.csv"
    )
    rows = []
    with score_path.open("r", encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            pid = row.get("project_id") or ""
            if not pid:
                continue
            rows.append(
                {
                    "project_id": pid,
                    "dac_sb535": "true" if i == 0 else "false",
                    "low_income_ab1550": "true" if i in (0, 1) else "false",
                    "low_income_near_dac": "true" if i == 1 else "false",
                    "tribal_area": "true" if i == 2 else "false",
                    "ces_percentile": "88" if i == 0 else "",
                    "notes": f"Overlay row {i}.",
                }
            )
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
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


SCORE_ROWS = [
    {
        "project_id": "p1",
        "name": "Downtown complete streets",
        "safety_score": "80",
        "equity_score": "90",
        "climate_score": "70",
        "feasibility_score": "60",
        "total_score": "78",
        "sensitivity_flag": "LOW",
    },
    {
        "project_id": "p2",
        "name": "Safe Routes to School",
        "safety_score": "70",
        "equity_score": "80",
        "climate_score": "60",
        "feasibility_score": "75",
        "total_score": "72",
        "sensitivity_flag": "MEDIUM",
    },
]


class ComputeAtpPacketTest(unittest.TestCase):
    def test_defaults_without_planner_pack_inputs(self) -> None:
        result = compute_atp_packet(SCORE_ROWS, run_id="r1")
        self.assertEqual(result.agency, DEFAULT_ATP_AGENCY)
        self.assertEqual(result.cycle, DEFAULT_ATP_CYCLE)
        self.assertEqual(len(result.applications), 2)
        for app in result.applications:
            self.assertEqual(app.benefit_category, "Unknown")
            self.assertIsNone(app.estimated_cost_usd)
            self.assertFalse(app.atp_dac_benefit_eligible)
            self.assertIn("to be provided by lead agency", app.location_note)
            self.assertIn("not been run", app.ceqa_determination)

    def test_lapm_enrichment_populates_programming_fields(self) -> None:
        lapm_rows = [
            {
                "project_id": "p1",
                "location_note": "38.001, -121.002",
                "description": "Add buffered bike lanes on Main Street.",
                "project_type": "Active Transportation",
                "estimated_cost_usd": "2500000",
                "schedule_note": "PA&ED FY26; CON FY28.",
            }
        ]
        result = compute_atp_packet(
            SCORE_ROWS, run_id="r1", lapm_rows=lapm_rows
        )
        app = next(a for a in result.applications if a.project_id == "p1")
        self.assertEqual(app.location_note, "38.001, -121.002")
        self.assertEqual(app.project_type, "Active Transportation")
        self.assertEqual(app.estimated_cost_usd, 2500000.0)

    def test_equity_enrichment_drives_dac_eligibility(self) -> None:
        equity_rows = [
            {
                "project_id": "p1",
                "dac_sb535": "true",
                "low_income_ab1550": "true",
                "low_income_near_dac": "true",
                "tribal_area": "false",
                "benefit_category": "DAC",
                "overlay_supplied": "true",
            },
            {
                "project_id": "p2",
                "dac_sb535": "false",
                "low_income_ab1550": "false",
                "low_income_near_dac": "false",
                "tribal_area": "false",
                "benefit_category": "Other",
                "overlay_supplied": "true",
            },
        ]
        result = compute_atp_packet(
            SCORE_ROWS, run_id="r1", equity_rows=equity_rows
        )
        by_id = {a.project_id: a for a in result.applications}
        self.assertTrue(by_id["p1"].dac_sb535)
        self.assertTrue(by_id["p1"].atp_dac_benefit_eligible)
        self.assertEqual(by_id["p1"].benefit_category, "DAC")
        self.assertIn("DAC", ATP_DAC_SCORING_CATEGORIES)
        self.assertFalse(by_id["p2"].atp_dac_benefit_eligible)
        self.assertEqual(by_id["p2"].benefit_category, "Other")

    def test_ceqa_rows_summarize_significance_mix(self) -> None:
        ceqa_rows = [
            {"scenario_id": "baseline", "determination": "less than significant"},
            {
                "scenario_id": "infill-growth",
                "determination": "potentially significant",
            },
        ]
        result = compute_atp_packet(
            SCORE_ROWS, run_id="r1", ceqa_rows=ceqa_rows
        )
        for app in result.applications:
            self.assertIn("1 potentially significant", app.ceqa_determination)
            self.assertIn("1 less-than-significant", app.ceqa_determination)

    def test_rtp_cycle_label_populates_consistency_note(self) -> None:
        result = compute_atp_packet(
            SCORE_ROWS,
            run_id="r1",
            rtp_cycle_label="2026 RTP",
        )
        for app in result.applications:
            self.assertIn("2026 RTP", app.rtp_consistency_note)

    def test_readiness_note_varies_with_sensitivity_flag(self) -> None:
        rows = [
            {**SCORE_ROWS[0], "sensitivity_flag": "LOW"},
            {**SCORE_ROWS[0], "project_id": "p3", "sensitivity_flag": "HIGH"},
        ]
        result = compute_atp_packet(rows, run_id="r1")
        by_id = {a.project_id: a for a in result.applications}
        self.assertIn("ready for PA&ED", by_id["p1"].readiness_note)
        self.assertIn("Two or more", by_id["p3"].readiness_note)

    def test_portfolio_summary_aggregates(self) -> None:
        equity_rows = [
            {
                "project_id": "p1",
                "dac_sb535": "true",
                "low_income_ab1550": "true",
                "low_income_near_dac": "false",
                "tribal_area": "false",
                "benefit_category": "DAC",
                "overlay_supplied": "true",
            },
            {
                "project_id": "p2",
                "dac_sb535": "false",
                "low_income_ab1550": "true",
                "low_income_near_dac": "false",
                "tribal_area": "true",
                "benefit_category": "Low-income",
                "overlay_supplied": "true",
            },
        ]
        result = compute_atp_packet(
            SCORE_ROWS, run_id="r1", equity_rows=equity_rows
        )
        summary = result.summary
        assert summary is not None
        self.assertEqual(summary.application_count, 2)
        self.assertEqual(summary.dac_application_count, 1)
        self.assertEqual(summary.low_income_application_count, 1)
        self.assertEqual(summary.tribal_application_count, 1)
        self.assertEqual(summary.dac_share, 0.5)
        self.assertAlmostEqual(summary.mean_total_score, 75.0)

    def test_empty_rows_raises(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_atp_packet([], run_id="r1")

    def test_all_empty_project_ids_raises(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_atp_packet([{"project_id": "", "name": "x"}], run_id="r1")


class AtpFactBlocksTest(unittest.TestCase):
    def test_per_application_and_summary_blocks(self) -> None:
        result = compute_atp_packet(
            [SCORE_ROWS[0]], run_id="r1", agency="City of Grass Valley", cycle="ATP Cycle 7"
        )
        blocks = atp_grant_fact_blocks(result, Path("/tmp/atp_packet.csv"))
        self.assertEqual(len(blocks), 2)
        project_block, summary_block = blocks
        self.assertEqual(project_block["fact_type"], "atp_application_project")
        self.assertEqual(project_block["fact_id"], "atp-application-p1")
        self.assertIn("total screening score", project_block["claim_text"])
        self.assertEqual(summary_block["fact_type"], "atp_application_summary")
        self.assertEqual(summary_block["fact_id"], "atp-application-summary")
        self.assertIn("ATP Cycle 7", summary_block["claim_text"])


class WriteAtpPacketTest(unittest.TestCase):
    def test_end_to_end_without_planner_pack_outputs(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            before = fact_blocks_path.read_text(encoding="utf-8").count("\n")

            summary = write_atp_packet(
                workspace,
                run_id,
                agency="Nevada County Transportation Commission",
                cycle="ATP Cycle 7",
            )

            self.assertGreater(summary["application_count"], 0)
            self.assertGreater(summary["fact_block_count"], 0)
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("California ATP Application Packet", report_text)
            self.assertIn("ATP Cycle 7", report_text)
            self.assertIn("to be provided by lead agency", report_text)
            after = fact_blocks_path.read_text(encoding="utf-8").count("\n")
            self.assertGreater(after, before)

    def test_end_to_end_with_full_planner_pack(self) -> None:
        with demo_workspace() as (workspace, run_id):
            write_ceqa_vmt(workspace, run_id)
            write_lapm_exhibit(
                workspace,
                run_id,
                lead_agency="City of Grass Valley",
                district="District 3",
            )
            _stage_equity_overlay(workspace)
            write_equity_lens(workspace, run_id)

            summary = write_atp_packet(
                workspace,
                run_id,
                agency="City of Grass Valley",
                cycle="ATP Cycle 7",
                rtp_cycle_label="2026 RTP",
            )
            payload = json.loads(
                Path(summary["json_path"]).read_text(encoding="utf-8")
            )
            applications = payload["applications"]
            self.assertGreater(len(applications), 0)
            at_least_one_dac_eligible = any(
                a["atp_dac_benefit_eligible"] for a in applications
            )
            self.assertTrue(at_least_one_dac_eligible)
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("2026 RTP", report_text)
            self.assertIn("potentially significant", report_text.lower() + " potentially significant")

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_atp_packet(workspace, "no-such-run")

    def test_idempotent_fact_block_append(self) -> None:
        with demo_workspace() as (workspace, run_id):
            first = write_atp_packet(workspace, run_id)
            second = write_atp_packet(workspace, run_id)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)


if __name__ == "__main__":
    unittest.main()
