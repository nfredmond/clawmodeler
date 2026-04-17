"""Planner Pack — regulatory deliverables grounded in run fact_blocks.

Each submodule produces a deliverable planners hand to a client or
agency: a CEQA §15064.3 VMT significance memo, a Caltrans LAPM exhibit,
an RTP chapter, or an equity-lens overlay. Every deliverable reads from
a finished run's `fact_blocks.jsonl`, appends its own grounded
fact_blocks, and renders under the same citation contract that gates
`export --ai-narrative` and `chat`.
"""

from .ceqa import (
    OPR_DEFAULT_THRESHOLD_PCT,
    PROJECT_TYPES,
    REFERENCE_LABELS,
    CeqaVmtResult,
    CeqaVmtScenario,
    ceqa_vmt_fact_blocks,
    compute_ceqa_vmt,
    render_ceqa_vmt_markdown,
    write_ceqa_vmt,
)

__all__ = [
    "OPR_DEFAULT_THRESHOLD_PCT",
    "PROJECT_TYPES",
    "REFERENCE_LABELS",
    "CeqaVmtResult",
    "CeqaVmtScenario",
    "ceqa_vmt_fact_blocks",
    "compute_ceqa_vmt",
    "render_ceqa_vmt_markdown",
    "write_ceqa_vmt",
]
