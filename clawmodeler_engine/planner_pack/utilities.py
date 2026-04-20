"""Shared helpers for Planner Pack modules.

Every Planner Pack deliverable (CEQA, LAPM, RTP, equity, ATP, HSIP, CMAQ,
STIP) follows the same compute/fact_blocks/render/write quartet and the
same three cross-cutting concerns: appending fact_blocks to a JSONL log
with de-duplication, coercing CSV string cells into the right Python
type, and spinning up a Jinja2 environment rooted at
``clawmodeler_engine/templates/planner_pack/``. Those three concerns live
here so a new grant module only adds grant-specific logic, not another
copy of the shared plumbing.

``validate_fact_block_shape`` is the emission-time mirror of
``qa.is_valid_fact_block``. It raises at the moment a module writes a
block rather than waiting for ``build_qa_report`` to reject the run at
export time — which was the v0.7.1 bug class where Planner Pack fact
blocks silently shipped without ``method_ref`` / ``artifact_refs``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..report import read_fact_blocks


def append_fact_blocks(path: Path, new_blocks: list[dict[str, Any]]) -> int:
    """Append fact_blocks to a JSONL log, skipping entries with duplicate fact_id."""
    if not new_blocks:
        return 0
    existing_ids: set[str] = set()
    if path.exists():
        existing_ids = {str(b.get("fact_id")) for b in read_fact_blocks(path)}
    appended = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for block in new_blocks:
            if block["fact_id"] in existing_ids:
                continue
            f.write(json.dumps(block) + "\n")
            appended += 1
    return appended


def coerce_str(value: Any, default: str = "") -> str:
    """Return a trimmed string, falling back to *default* when the input is empty."""
    if value in (None, ""):
        return default
    return str(value).strip() or default


def parse_optional_float(value: Any) -> float | None:
    """Parse a numeric CSV cell, returning None for missing or non-numeric input."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def jinja_env() -> Any:
    """Jinja2 environment rooted at ``clawmodeler_engine/templates/planner_pack/``."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    templates_dir = Path(__file__).parent.parent / "templates" / "planner_pack"
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


def manifest_artifact_paths(workspace: Path, run_root: Path, key: str) -> list[Path]:
    """Return artifact path candidates recorded in a run manifest.

    Planner Pack modules historically looked for optional sidecars under
    ``runs/<id>/outputs/run_manifest.json`` and assumed each manifest artifact
    value was a list. Actual ClawModeler runs write ``runs/<id>/manifest.json``,
    and hand-edited manifests often store one path as a plain string. This
    helper accepts both the current and legacy manifest locations and normalizes
    string/list/dict path shapes into concrete ``Path`` candidates.
    """
    paths: list[Path] = []
    seen: set[str] = set()
    for manifest_path in (
        run_root / "manifest.json",
        run_root / "outputs" / "run_manifest.json",
    ):
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
        if not isinstance(artifacts, dict):
            continue
        for raw_path in _path_values(artifacts.get(key)):
            candidate = _resolve_manifest_path(workspace, run_root, raw_path)
            token = str(candidate)
            if token not in seen:
                seen.add(token)
                paths.append(candidate)
    return paths


def _path_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, Path)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, dict):
        for key in ("path", "staged_path", "source_path"):
            paths = _path_values(value.get(key))
            if paths:
                return paths
        return []
    if isinstance(value, (list, tuple, set)):
        paths: list[str] = []
        for item in value:
            paths.extend(_path_values(item))
        return paths
    return []


def _resolve_manifest_path(workspace: Path, run_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    workspace_path = workspace / path
    if workspace_path.exists():
        return workspace_path
    return run_root / path


def validate_fact_block_shape(block: dict[str, Any]) -> None:
    """Raise if *block* is missing a field the QA gate requires.

    Mirrors ``qa.is_valid_fact_block`` so drift is caught at emission time
    rather than at export time.
    """
    if not isinstance(block, dict):
        raise ValueError(f"fact_block must be a dict, got {type(block).__name__}")
    fact_id = block.get("fact_id")
    if not isinstance(fact_id, str) or not fact_id.strip():
        raise ValueError("fact_block is missing a non-empty string 'fact_id'")
    claim_text = block.get("claim_text")
    if not isinstance(claim_text, str) or not claim_text.strip():
        raise ValueError(f"fact_block {fact_id!r} is missing a non-empty 'claim_text'")
    method_ref = block.get("method_ref")
    if not isinstance(method_ref, str) or not method_ref.strip():
        raise ValueError(f"fact_block {fact_id!r} is missing a non-empty 'method_ref'")
    artifact_refs = block.get("artifact_refs")
    if not isinstance(artifact_refs, list) or len(artifact_refs) == 0:
        raise ValueError(f"fact_block {fact_id!r} is missing a non-empty 'artifact_refs' list")
