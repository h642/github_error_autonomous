"""Configuration management for the Autonomous Software Repair Pipeline.

Aligned with UN SDGs:
- SDG 9: Industry, Innovation, and Infrastructure (Resilient digital systems)
- SDG 16: Peace, Justice, and Strong Institutions (Transparent, dependable civic code)
"""

from dataclasses import dataclass, field
from typing import Optional, List
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class RepairConfig:
    """Pipeline configuration parameters and safety guardrails."""

    # Stage 1: Sandbox & Execution
    sandbox_timeout_seconds: int = 45
    python_executable: str = "python3"
    use_docker_if_available: bool = True

    # Stage 2: Spectrum-Based Fault Localization (SBFL)
    sbfl_metric: str = "ochiai"  # Options: "ochiai", "tarantula"
    top_k_suspicious_blocks: int = 5
    min_suspiciousness_threshold: float = 0.05
    surrounding_context_lines: int = 6

    # Stage 3: Multi-Hypothesis Generation & Synthesis
    max_repair_iterations: int = 5
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")  # "openai", "anthropic", "gemini", "mock"
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    temperature: float = 0.2
    max_tokens: int = 2500
    min_hypotheses_count: int = 3
    max_hypotheses_count: int = 5

    # Stage 4: Multi-Layer Verification Gates
    enforce_regression_gate: bool = True
    enforce_property_gate: bool = True
    enforce_mutation_gate: bool = True
    property_test_max_examples: int = 20
    max_mutation_candidates: int = 3
    min_mutation_score_threshold: float = 0.65  # Minimum % of mutants that must be killed

    # Stage 5: Reviewer PR Packaging
    target_repo_name: str = "public-interest/civic-infra"
    author_name: str = "SDG-Autonomous-Repair-Agent <bot@sdg-repair.org>"
    sdg_goals: List[str] = field(default_factory=lambda: ["SDG 9", "SDG 16"])
