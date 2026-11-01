"""Multi-layer verification gate orchestrator (Stage 4)."""

import time
from dataclasses import dataclass, field
from typing import List, Optional

from autonomous_repair.config import RepairConfig
from autonomous_repair.sandbox.base import AbstractSandbox
from autonomous_repair.verification.mutation_gate import MutationGate, MutationGateResult
from autonomous_repair.verification.property_gate import PropertyGate, PropertyGateResult
from autonomous_repair.verification.regression_gate import RegressionGate, RegressionGateResult


@dataclass
class VerificationMatrix:
    """Aggregated outcome across all 3 verification gates."""
    regression: RegressionGateResult
    property_fuzz: Optional[PropertyGateResult]
    mutation: Optional[MutationGateResult]
    all_passed: bool
    total_duration_seconds: float
    feedback_for_next_iteration: str = ""

    def summary_table(self) -> str:
        reg_status = "PASSED" if self.regression.passed else "FAILED"
        prop_status = (
            ("PASSED" if self.property_fuzz.passed else "FAILED")
            if self.property_fuzz
            else "SKIPPED"
        )
        mut_status = (
            ("PASSED" if self.mutation.passed else "FAILED")
            if self.mutation
            else "SKIPPED"
        )

        mut_pct = f"{self.mutation.mutation_score * 100:.1f}%" if self.mutation else "N/A"

        return f"""| Gate | Verification Check | Status | Key Metric |
|------|--------------------|--------|------------|
| Gate 1 | Baseline Regression Tests | **{reg_status}** | {self.regression.passed_tests}/{self.regression.total_tests} passed |
| Gate 2 | Generative Property Fuzzing (Hypothesis) | **{prop_status}** | {self.property_fuzz.examples_evaluated if self.property_fuzz else 0} examples |
| Gate 3 | Mutation Testing (AST Mutants) | **{mut_status}** | Score: {mut_pct} |
"""


class MultiLayerVerifier:
    """Orchestrates Gate 1 (Regression), Gate 2 (Properties), and Gate 3 (Mutations)."""

    def __init__(self, sandbox: AbstractSandbox, config: RepairConfig):
        self.sandbox = sandbox
        self.config = config
        self.regression_gate = RegressionGate(sandbox)
        self.property_gate = PropertyGate(sandbox, max_examples=config.property_test_max_examples)
        self.mutation_gate = MutationGate(
            sandbox,
            threshold=config.min_mutation_score_threshold,
            max_mutants=config.max_mutation_candidates,
        )

    def verify_patch(
        self,
        patched_files: List[str],
        property_test_path: str = "tests/test_properties.py",
        baseline_test_cmd: Optional[str] = None,
    ) -> VerificationMatrix:
        start_time = time.perf_counter()
        feedback_parts: List[str] = []

        # Gate 1: Regression check
        reg_result = self.regression_gate.evaluate(baseline_test_cmd)
        if not reg_result.passed:
            feedback_parts.append(
                f"[Gate 1 Failed]: Unit tests failed after applying the patch. "
                f"Failures: {reg_result.failed_tests}/{reg_result.total_tests}.\n"
                f"Trace/Output snippet: {reg_result.failure_details}"
            )
            # If regression gate fails, we can stop early to conserve compute
            elapsed = time.perf_counter() - start_time
            return VerificationMatrix(
                regression=reg_result,
                property_fuzz=None,
                mutation=None,
                all_passed=False,
                total_duration_seconds=elapsed,
                feedback_for_next_iteration="\n".join(feedback_parts),
            )

        # Gate 2: Property-based testing
        prop_result: Optional[PropertyGateResult] = None
        if self.config.enforce_property_gate:
            prop_result = self.property_gate.evaluate(property_test_path)
            if not prop_result.passed:
                feedback_parts.append(
                    f"[Gate 2 Failed]: Generative property test falsified: {prop_result.falsified_property}.\n"
                    f"Counterexample discovered: {prop_result.shrunk_counterexample}"
                )

        # Gate 3: Mutation testing
        mut_result: Optional[MutationGateResult] = None
        if self.config.enforce_mutation_gate and (prop_result is None or prop_result.passed):
            mut_result = self.mutation_gate.evaluate(patched_files)
            if not mut_result.passed:
                survived = [m.description for m in mut_result.mutants if not m.killed]
                feedback_parts.append(
                    f"[Gate 3 Failed]: Mutation testing score was {mut_result.mutation_score * 100:.1f}%, "
                    f"which is below required threshold of {self.config.min_mutation_score_threshold * 100:.1f}%.\n"
                    f"Surviving mutants: {survived[:5]}"
                )

        elapsed = time.perf_counter() - start_time
        all_passed = (
            reg_result.passed
            and (prop_result is None or prop_result.passed)
            and (mut_result is None or mut_result.passed)
        )

        return VerificationMatrix(
            regression=reg_result,
            property_fuzz=prop_result,
            mutation=mut_result,
            all_passed=all_passed,
            total_duration_seconds=elapsed,
            feedback_for_next_iteration="\n".join(feedback_parts),
        )
