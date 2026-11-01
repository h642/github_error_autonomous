"""Spectrum-Based Fault Localization (SBFL) module exports."""

from autonomous_repair.localization.coverage_tracer import CoverageTracer, TestCoverageResult
from autonomous_repair.localization.ochiai import OchiaiCalculator, LineSuspiciousness
from autonomous_repair.localization.context_extractor import ASTContextExtractor, SuspiciousBlock

__all__ = [
    "CoverageTracer",
    "TestCoverageResult",
    "OchiaiCalculator",
    "LineSuspiciousness",
    "ASTContextExtractor",
    "SuspiciousBlock",
]
