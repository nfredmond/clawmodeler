from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import (
    write_export,
    write_intake,
    write_plan,
    write_run,
)


def _pdf_deps_available() -> bool:
    try:
        import markdown_it  # noqa: F401
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


@contextmanager
def demo_workspace(run_id: str = "pdf"):
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


@unittest.skipUnless(_pdf_deps_available(), "markdown-it-py and weasyprint required")
class PdfExportTest(unittest.TestCase):
    def test_each_report_type_renders_valid_pdf(self) -> None:
        with demo_workspace() as (workspace, run_id):
            for report_type in ("technical", "layperson", "brief"):
                path = write_export(
                    workspace, run_id, "pdf", report_type=report_type
                )
                self.assertIsInstance(path, Path)
                data = path.read_bytes()
                self.assertTrue(
                    data.startswith(b"%PDF-"),
                    f"{report_type} did not produce a PDF magic header",
                )
                self.assertGreater(
                    len(data),
                    1024,
                    f"{report_type} PDF suspiciously small ({len(data)} bytes)",
                )

    def test_all_report_types_via_format_all(self) -> None:
        with demo_workspace() as (workspace, run_id):
            paths = write_export(workspace, run_id, "pdf", report_type="all")
            self.assertIsInstance(paths, list)
            self.assertEqual(len(paths), 3)
            for path in paths:
                self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
                self.assertTrue(path.suffix == ".pdf")

    def test_pdf_with_grounded_ai_narrative(self) -> None:
        from clawmodeler_engine.llm import FakeProvider

        with demo_workspace() as (workspace, run_id):
            fact_ids_path = (
                workspace
                / "runs"
                / run_id
                / "outputs"
                / "tables"
                / "fact_blocks.jsonl"
            )
            import json

            fact_ids: list[str] = []
            with fact_ids_path.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        fact_ids.append(json.loads(line)["fact_id"])
            self.assertGreaterEqual(len(fact_ids), 2)

            provider = FakeProvider(
                canned_text=(
                    f"Baseline VMT screening looks stable. [fact:{fact_ids[0]}] "
                    f"Jobs access improves under build. [fact:{fact_ids[1]}]"
                ),
                model="canned-test",
            )
            with patch(
                "clawmodeler_engine.llm.build_provider", return_value=provider
            ):
                path = write_export(
                    workspace,
                    run_id,
                    "pdf",
                    report_type="technical",
                    ai_narrative=True,
                )
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"%PDF-"))
            self.assertGreater(len(data), 1024)


class PdfDependencyMissingTest(unittest.TestCase):
    def test_missing_deps_raises_with_install_hint(self) -> None:
        from clawmodeler_engine.pdf import (
            PdfDependencyMissingError,
            _require_pdf_deps,
        )

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def fake_import(name, *args, **kwargs):
            if name in ("markdown_it", "weasyprint"):
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(PdfDependencyMissingError) as ctx:
                _require_pdf_deps()
            self.assertIn("pdf", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
