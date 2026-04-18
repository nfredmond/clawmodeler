from __future__ import annotations

import csv
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.diff import (
    ArtifactDiff,
    FieldChange,
    RowChange,
    RunDiffResult,
    compute_run_diff,
    run_diff_fact_blocks,
    write_run_diff,
)
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    write_atp_packet,
    write_ceqa_vmt,
    write_equity_lens,
    write_lapm_exhibit,
    write_rtp_chapter,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def two_run_workspace():
    """Create a workspace with two distinct finished runs."""
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
        write_run(workspace, "baseline-run", ["baseline", "infill-growth"])
        write_run(workspace, "revised-run", ["baseline", "infill-growth"])
        yield workspace, "baseline-run", "revised-run"


def _mutate_project_scores(workspace: Path, run_id: str) -> None:
    """Edit project_scores.csv in place to create a diff target."""
    path = workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []
    rows[0]["total_score"] = str(float(rows[0]["total_score"]) + 5.0)
    rows[0]["sensitivity_flag"] = "HIGH"
    rows = rows[:-1]  # remove last row — creates a "removed" entry
    rows.append(
        {
            "project_id": "new-bike-lane",
            "name": "New Bike Lane on Main St",
            "safety_score": "70",
            "equity_score": "60",
            "climate_score": "55",
            "feasibility_score": "80",
            "total_score": "67.5",
            "sensitivity_flag": "LOW",
        }
    )
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class ComputeRunDiffTest(unittest.TestCase):
    def test_rejects_identical_run_ids(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_run_diff(
                run_a_id="same",
                run_b_id="same",
                artifact_rows_a={},
                artifact_rows_b={},
                artifact_present_a={},
                artifact_present_b={},
            )

    def test_detects_added_removed_changed_rows(self) -> None:
        rows_a = [
            {"project_id": "p1", "name": "P1", "total_score": "70.0", "sensitivity_flag": "LOW"},
            {"project_id": "p2", "name": "P2", "total_score": "65.0", "sensitivity_flag": "LOW"},
        ]
        rows_b = [
            {"project_id": "p1", "name": "P1", "total_score": "75.0", "sensitivity_flag": "LOW"},
            {"project_id": "p3", "name": "P3", "total_score": "80.0", "sensitivity_flag": "LOW"},
        ]
        result = compute_run_diff(
            run_a_id="a",
            run_b_id="b",
            artifact_rows_a={"project_scores": rows_a},
            artifact_rows_b={"project_scores": rows_b},
            artifact_present_a={"project_scores": True},
            artifact_present_b={"project_scores": True},
        )
        proj = next(a for a in result.artifacts if a.artifact == "project_scores")
        self.assertEqual(proj.added_count, 1)
        self.assertEqual(proj.removed_count, 1)
        self.assertEqual(proj.changed_count, 1)
        statuses = sorted(r.status for r in proj.row_changes)
        self.assertEqual(statuses, ["added", "changed", "removed"])
        changed_row = next(r for r in proj.row_changes if r.status == "changed")
        score_change = next(c for c in changed_row.changes if c.field == "total_score")
        self.assertEqual(score_change.numeric_delta, 5.0)

    def test_absent_artifact_reports_present_false(self) -> None:
        result = compute_run_diff(
            run_a_id="a",
            run_b_id="b",
            artifact_rows_a={"project_scores": []},
            artifact_rows_b={"project_scores": []},
            artifact_present_a={"project_scores": False},
            artifact_present_b={"project_scores": True},
        )
        proj = next(a for a in result.artifacts if a.artifact == "project_scores")
        self.assertFalse(proj.present_in_a)
        self.assertTrue(proj.present_in_b)

    def test_unchanged_rows_counted_but_not_listed(self) -> None:
        rows = [
            {"project_id": "p1", "name": "P1", "total_score": "70.0", "sensitivity_flag": "LOW"},
        ]
        result = compute_run_diff(
            run_a_id="a",
            run_b_id="b",
            artifact_rows_a={"project_scores": rows},
            artifact_rows_b={"project_scores": rows},
            artifact_present_a={"project_scores": True},
            artifact_present_b={"project_scores": True},
        )
        proj = next(a for a in result.artifacts if a.artifact == "project_scores")
        self.assertEqual(proj.unchanged_count, 1)
        self.assertEqual(proj.changed_count, 0)
        self.assertEqual(len(proj.row_changes), 0)

    def test_empty_project_id_rows_ignored(self) -> None:
        rows_a = [
            {"project_id": "", "name": "orphan", "total_score": "10"},
            {"project_id": "p1", "name": "P1", "total_score": "70"},
        ]
        rows_b = [{"project_id": "p1", "name": "P1", "total_score": "70"}]
        result = compute_run_diff(
            run_a_id="a",
            run_b_id="b",
            artifact_rows_a={"project_scores": rows_a},
            artifact_rows_b={"project_scores": rows_b},
            artifact_present_a={"project_scores": True},
            artifact_present_b={"project_scores": True},
        )
        proj = next(a for a in result.artifacts if a.artifact == "project_scores")
        self.assertEqual(proj.added_count, 0)
        self.assertEqual(proj.removed_count, 0)
        self.assertEqual(proj.unchanged_count, 1)


class RunDiffFactBlocksTest(unittest.TestCase):
    def test_emits_row_and_summary_blocks(self) -> None:
        result = RunDiffResult(
            run_a_id="a",
            run_b_id="b",
            run_a_engine_version="0.6.4",
            run_b_engine_version="0.7.0",
            run_a_created_at=None,
            run_b_created_at=None,
            artifacts=[
                ArtifactDiff(
                    artifact="project_scores",
                    label="Project screening scores",
                    filename="project_scores.csv",
                    key_column="project_id",
                    present_in_a=True,
                    present_in_b=True,
                    row_count_a=2,
                    row_count_b=2,
                    added_count=0,
                    removed_count=0,
                    changed_count=1,
                    unchanged_count=1,
                    row_changes=[
                        RowChange(
                            key="p1",
                            name="P1",
                            status="changed",
                            changes=[
                                FieldChange(
                                    field="total_score",
                                    from_value="70",
                                    to_value="75",
                                    numeric_delta=5.0,
                                )
                            ],
                        )
                    ],
                )
            ],
            generated_at="2026-04-18T00:00:00+00:00",
        )
        blocks = run_diff_fact_blocks(result, Path("/tmp/diff.csv"))
        self.assertEqual(len(blocks), 2)
        row_block = next(b for b in blocks if b["fact_type"] == "run_diff_row")
        summary_block = next(b for b in blocks if b["fact_type"] == "run_diff_summary")
        self.assertEqual(row_block["artifact"], "project_scores")
        self.assertIn("total_score: 70 → 75", row_block["claim_text"])
        self.assertIn("Δ +5.0", row_block["claim_text"])
        self.assertIn("present in both runs", summary_block["claim_text"])
        self.assertIn("1 changed", summary_block["claim_text"])

    def test_presence_phrase_when_only_b_has_artifact(self) -> None:
        result = RunDiffResult(
            run_a_id="old",
            run_b_id="new",
            run_a_engine_version=None,
            run_b_engine_version=None,
            run_a_created_at=None,
            run_b_created_at=None,
            artifacts=[
                ArtifactDiff(
                    artifact="equity_lens",
                    label="SB 535 / AB 1550 / tribal equity lens",
                    filename="equity_lens.csv",
                    key_column="project_id",
                    present_in_a=False,
                    present_in_b=True,
                    row_count_a=0,
                    row_count_b=3,
                    added_count=3,
                    removed_count=0,
                    changed_count=0,
                    unchanged_count=0,
                    row_changes=[],
                )
            ],
            generated_at="",
        )
        blocks = run_diff_fact_blocks(result, Path("/tmp/diff.csv"))
        summary = next(b for b in blocks if b["fact_type"] == "run_diff_summary")
        self.assertIn("present only in run new", summary["claim_text"])


class WriteRunDiffTest(unittest.TestCase):
    def test_end_to_end_unchanged_runs(self) -> None:
        with two_run_workspace() as (workspace, run_a, run_b):
            summary = write_run_diff(workspace, run_a, run_b)
            self.assertEqual(summary["totals"]["added"], 0)
            self.assertEqual(summary["totals"]["removed"], 0)
            self.assertEqual(summary["totals"]["changed"], 0)
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("Run Diff", report_text)
            self.assertIn(run_a, report_text)
            self.assertIn(run_b, report_text)

    def test_end_to_end_detects_mutations(self) -> None:
        with two_run_workspace() as (workspace, run_a, run_b):
            _mutate_project_scores(workspace, run_b)
            summary = write_run_diff(workspace, run_a, run_b)
            totals = summary["totals"]
            self.assertGreaterEqual(totals["added"], 1)
            self.assertGreaterEqual(totals["removed"], 1)
            self.assertGreaterEqual(totals["changed"], 1)
            payload = json.loads(Path(summary["json_path"]).read_text(encoding="utf-8"))
            proj = next(
                a for a in payload["artifacts"] if a["artifact"] == "project_scores"
            )
            self.assertTrue(proj["present_in_a"])
            self.assertTrue(proj["present_in_b"])
            self.assertGreaterEqual(proj["added_count"], 1)

    def test_end_to_end_with_full_planner_pack(self) -> None:
        with two_run_workspace() as (workspace, run_a, run_b):
            for run_id in (run_a, run_b):
                write_ceqa_vmt(workspace, run_id)
                write_lapm_exhibit(
                    workspace,
                    run_id,
                    lead_agency="City of Grass Valley",
                    district="District 3",
                )
                write_rtp_chapter(workspace, run_id)
                write_equity_lens(workspace, run_id)
                write_atp_packet(
                    workspace,
                    run_id,
                    agency="City of Grass Valley",
                    cycle="ATP Cycle 7",
                )
            _mutate_project_scores(workspace, run_b)
            summary = write_run_diff(workspace, run_a, run_b)
            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("CEQA §15064.3 VMT determinations", report_text)
            self.assertIn("California ATP application packet", report_text)
            self.assertIn("SB 535 / AB 1550 / tribal equity lens", report_text)

    def test_flat_csv_has_one_row_per_field_change(self) -> None:
        with two_run_workspace() as (workspace, run_a, run_b):
            _mutate_project_scores(workspace, run_b)
            summary = write_run_diff(workspace, run_a, run_b)
            with Path(summary["csv_path"]).open() as f:
                rows = list(csv.DictReader(f))
            statuses = {r["status"] for r in rows}
            self.assertIn("added", statuses)
            self.assertIn("removed", statuses)
            self.assertIn("changed", statuses)

    def test_rejects_same_run_id(self) -> None:
        with two_run_workspace() as (workspace, run_a, _):
            with self.assertRaises(InsufficientDataError):
                write_run_diff(workspace, run_a, run_a)

    def test_rejects_missing_run(self) -> None:
        with two_run_workspace() as (workspace, run_a, _):
            with self.assertRaises(InsufficientDataError):
                write_run_diff(workspace, run_a, "no-such-run")

    def test_idempotent_fact_block_append(self) -> None:
        with two_run_workspace() as (workspace, run_a, run_b):
            _mutate_project_scores(workspace, run_b)
            first = write_run_diff(workspace, run_a, run_b)
            second = write_run_diff(workspace, run_a, run_b)
            fact_blocks_path = Path(first["diff_dir"]) / "fact_blocks.jsonl"
            line_count = fact_blocks_path.read_text(encoding="utf-8").count("\n")
            self.assertEqual(second["fact_block_count"], 0)
            self.assertGreaterEqual(first["fact_block_count"], 1)
            self.assertEqual(line_count, first["fact_block_count"])


if __name__ == "__main__":
    unittest.main()
