"""Planner Pack — regulatory deliverables grounded in run fact_blocks.

Each submodule produces a deliverable planners hand to a client or
agency: a CEQA §15064.3 VMT significance memo, a Caltrans LAPM exhibit,
an RTP chapter, or an equity-lens overlay. Every deliverable reads from
a finished run's `fact_blocks.jsonl`, appends its own grounded
fact_blocks, and renders under the same citation contract that gates
`export --ai-narrative` and `chat`.
"""

from .atp import (
    ATP_DAC_SCORING_CATEGORIES,
    AtpGrantResult,
    AtpPortfolioSummary,
    AtpProjectApplication,
    atp_grant_fact_blocks,
    compute_atp_packet,
    render_atp_markdown,
    write_atp_packet,
)
from .atp import DEFAULT_AGENCY as DEFAULT_ATP_AGENCY
from .atp import DEFAULT_CYCLE as DEFAULT_ATP_CYCLE
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
from .equity import (
    AB1550_TARGET_DAC_SHARE,
    AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE,
    AB1550_TARGET_LOW_INCOME_SHARE,
    BENEFIT_CATEGORIES,
    DEFAULT_DATASET_NOTE,
    EquityLensResult,
    EquityPortfolioSummary,
    EquityProjectFinding,
    compute_equity_lens,
    equity_lens_fact_blocks,
    render_equity_lens_markdown,
    write_equity_lens,
)
from .equity import DEFAULT_AGENCY as DEFAULT_EQUITY_AGENCY
from .lapm import (
    DEFAULT_DISTRICT,
    DEFAULT_LEAD_AGENCY,
    LapmExhibitResult,
    LapmProgrammingExhibit,
    compute_lapm_exhibit,
    lapm_fact_blocks,
    render_lapm_markdown,
    write_lapm_exhibit,
)
from .rtp import (
    DEFAULT_AGENCY,
    DEFAULT_CHAPTER_TITLE,
    DEFAULT_RTP_CYCLE,
    RtpChapterResult,
    RtpProjectEntry,
    RtpScenarioEntry,
    compute_rtp_chapter,
    render_rtp_chapter_markdown,
    rtp_chapter_fact_blocks,
    write_rtp_chapter,
)

__all__ = [
    "AB1550_TARGET_DAC_SHARE",
    "AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE",
    "AB1550_TARGET_LOW_INCOME_SHARE",
    "ATP_DAC_SCORING_CATEGORIES",
    "AtpGrantResult",
    "AtpPortfolioSummary",
    "AtpProjectApplication",
    "BENEFIT_CATEGORIES",
    "DEFAULT_AGENCY",
    "DEFAULT_ATP_AGENCY",
    "DEFAULT_ATP_CYCLE",
    "DEFAULT_CHAPTER_TITLE",
    "DEFAULT_DATASET_NOTE",
    "DEFAULT_DISTRICT",
    "DEFAULT_EQUITY_AGENCY",
    "DEFAULT_LEAD_AGENCY",
    "DEFAULT_RTP_CYCLE",
    "EquityLensResult",
    "EquityPortfolioSummary",
    "EquityProjectFinding",
    "LapmExhibitResult",
    "LapmProgrammingExhibit",
    "OPR_DEFAULT_THRESHOLD_PCT",
    "PROJECT_TYPES",
    "REFERENCE_LABELS",
    "RtpChapterResult",
    "RtpProjectEntry",
    "RtpScenarioEntry",
    "CeqaVmtResult",
    "CeqaVmtScenario",
    "atp_grant_fact_blocks",
    "ceqa_vmt_fact_blocks",
    "compute_atp_packet",
    "compute_ceqa_vmt",
    "compute_equity_lens",
    "compute_lapm_exhibit",
    "compute_rtp_chapter",
    "equity_lens_fact_blocks",
    "lapm_fact_blocks",
    "render_atp_markdown",
    "render_ceqa_vmt_markdown",
    "render_equity_lens_markdown",
    "render_lapm_markdown",
    "render_rtp_chapter_markdown",
    "rtp_chapter_fact_blocks",
    "write_atp_packet",
    "write_ceqa_vmt",
    "write_equity_lens",
    "write_lapm_exhibit",
    "write_rtp_chapter",
]
