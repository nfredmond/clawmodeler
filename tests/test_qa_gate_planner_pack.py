from __future__ import annotations

import csv
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.diff import write_run_diff
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    write_atp_packet,
    write_ceqa_vmt,
    write_equity_lens,
    write_lapm_exhibit,
    write_rtp_chapter,
)
from clawmodeler_engine.qa import build_qa_report, is_valid_fact_block


@contextmanager
def demo_workspace(run_id: str = "qagate"):
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


def _stage_equity_overlay(workspace: Path, run_id: str) -> None:
    overlay_path = workspace / "inputs" / "equity_overlay.csv"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    score_path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
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


class PlannerPackQaGateTest(unittest.TestCase):
    """Every planner-pack emitter must produce fact_blocks that pass
    qa.is_valid_fact_block — fact_id, claim_text, method_ref (str), and
    artifact_refs (non-empty list). Regression for the v0.7.1 bug where
    planner-pack blocks emitted source_table/source_row instead of
    method_ref/artifact_refs and silently broke the export gate."""

    def test_ceqa_vmt_passes_qa_gate(self) -> None:
        with demo_workspace("ceqa") as (workspace, run_id):
            write_ceqa_vmt(workspace, run_id)
            report = build_qa_report(workspace, run_id)
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_lapm_exhibit_passes_qa_gate(self) -> None:
        with demo_workspace("lapm") as (workspace, run_id):
            write_lapm_exhibit(workspace, run_id)
            report = build_qa_report(workspace, run_id)
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_rtp_chapter_passes_qa_gate(self) -> None:
        with demo_workspace("rtp") as (workspace, run_id):
            write_rtp_chapter(workspace, run_id)
            report = build_qa_report(workspace, run_id)
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_equity_lens_passes_qa_gate(self) -> None:
        with demo_workspace("equity") as (workspace, run_id):
            _stage_equity_overlay(workspace, run_id)
            write_equity_lens(workspace, run_id)
            report = build_qa_report(workspace, run_id)
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_atp_packet_passes_qa_gate(self) -> None:
        with demo_workspace("atp") as (workspace, run_id):
            _stage_equity_overlay(workspace, run_id)
            write_lapm_exhibit(workspace, run_id)
            write_atp_packet(workspace, run_id)
            report = build_qa_report(workspace, run_id)
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_full_planner_pack_stack_passes_qa_gate(self) -> None:
        with demo_workspace("fullstack") as (workspace, run_id):
            _stage_equity_overlay(workspace, run_id)
            write_ceqa_vmt(workspace, run_id)
            write_lapm_exhibit(workspace, run_id)
            write_rtp_chapter(workspace, run_id)
            write_equity_lens(workspace, run_id)
            write_atp_packet(workspace, run_id)
            report = build_qa_report(workspace, run_id)
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_run_diff_emits_valid_fact_blocks(self) -> None:
        """Diff fact_blocks live in ``diffs/<a>_vs_<b>/`` rather than a run
        tree, so they don't flow through ``build_qa_report``; verify each
        block satisfies ``is_valid_fact_block`` directly so the schema
        stays consistent with planner-pack emitters."""
        import json as _json

        with demo_workspace("diff_a") as (workspace, run_a):
            write_run(workspace, "diff_b", ["baseline", "infill-growth"])
            write_run_diff(workspace, run_a, "diff_b")
            path = (
                workspace
                / "diffs"
                / f"{run_a}_vs_diff_b"
                / "fact_blocks.jsonl"
            )
            self.assertTrue(path.exists())
            blocks = [
                _json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertGreater(len(blocks), 0)
            for block in blocks:
                self.assertTrue(
                    is_valid_fact_block(block),
                    f"diff fact_block failed QA validator: {block}",
                )


if __name__ == "__main__":
    unittest.main()
