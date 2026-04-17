"""LLM integration for ClawModeler AI-narrative reports.

The grounding contract is load-bearing: every narrative sentence must
cite a fact_id that exists in the run's fact_blocks.jsonl. Citation
enforcement is deterministic (regex + set membership), not an LLM judge.
"""

from .anthropic import (
    AnthropicMissingKeyError,
    AnthropicNotInstalledError,
    AnthropicProvider,
)
from .grounding import (
    CITATION_PATTERN,
    GroundedOutput,
    GroundingIssue,
    GroundingMode,
    Sentence,
    split_sentences,
    validate_and_ground,
)
from .ollama import (
    DEFAULT_ENDPOINT as OLLAMA_DEFAULT_ENDPOINT,
)
from .ollama import (
    DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL,
)
from .ollama import (
    OllamaNotInstalledError,
    OllamaProvider,
)
from .openai import (
    OpenAIMissingKeyError,
    OpenAINotInstalledError,
    OpenAIProvider,
)
from .provider import (
    FakeProvider,
    GenerationResult,
    LLMProvider,
    ProviderProbe,
)

__all__ = [
    "AnthropicMissingKeyError",
    "AnthropicNotInstalledError",
    "AnthropicProvider",
    "CITATION_PATTERN",
    "FakeProvider",
    "GenerationResult",
    "GroundedOutput",
    "GroundingIssue",
    "GroundingMode",
    "LLMProvider",
    "OLLAMA_DEFAULT_ENDPOINT",
    "OLLAMA_DEFAULT_MODEL",
    "OllamaNotInstalledError",
    "OllamaProvider",
    "OpenAIMissingKeyError",
    "OpenAINotInstalledError",
    "OpenAIProvider",
    "ProviderProbe",
    "Sentence",
    "split_sentences",
    "validate_and_ground",
]
