"""Ochiai Statistical Fault Localization formula calculation (Stage 2: SBFL)."""

import math
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from autonomous_repair.localization.coverage_tracer import TestCoverageResult


@dataclass
class LineSuspiciousness:
    """Calculated suspiciousness score for an individual source line."""
    file_path: str
    line_number: int
    score: float
    failed_count: int
    passed_count: int
    total_failed: int
    total_passed: int
    code_content: str = ""

    def __repr__(self) -> str:
        return f"LineSuspiciousness({self.file_path}:{self.line_number}, score={self.score:.4f}, failed={self.failed_count}/{self.total_failed}, passed={self.passed_count}/{self.total_passed})"


class OchiaiCalculator:
    """Computes Ochiai spectrum-based fault localization scores."""

    @staticmethod
    def calculate(
        test_traces: List[TestCoverageResult],
        file_content_getter=None,
    ) -> List[LineSuspiciousness]:
        """Compute line suspiciousness using the statistical Ochiai formula:
        Score(s) = Failed(s) / sqrt( TotalFailed * (Failed(s) + Passed(s)) )
        """
        total_failed = sum(1 for t in test_traces if not t.passed)
        total_passed = sum(1 for t in test_traces if t.passed)

        if total_failed == 0:
            # If all tests pass, suspiciousness is 0 everywhere
            return []

        # Count executions per statement (file_path, line_number)
        failed_counts: Dict[Tuple[str, int], int] = {}
        passed_counts: Dict[Tuple[str, int], int] = {}

        all_statements: Set[Tuple[str, int]] = set()

        for trace in test_traces:
            is_fail = not trace.passed
            for file_path, lines in trace.executed_lines.items():
                for line_num in lines:
                    stmt = (file_path, line_num)
                    all_statements.add(stmt)
                    if is_fail:
                        failed_counts[stmt] = failed_counts.get(stmt, 0) + 1
                    else:
                        passed_counts[stmt] = passed_counts.get(stmt, 0) + 1

        scored_lines: List[LineSuspiciousness] = []

        for stmt in all_statements:
            file_path, line_num = stmt
            ef = failed_counts.get(stmt, 0)  # executed in failing
            ep = passed_counts.get(stmt, 0)  # executed in passing

            if ef == 0:
                score = 0.0
            else:
                denominator = math.sqrt(total_failed * (ef + ep))
                score = (ef / denominator) if denominator > 0 else 0.0

            code_text = ""
            if file_content_getter:
                try:
                    code_text = file_content_getter(file_path, line_num)
                except Exception:
                    code_text = ""

            scored_lines.append(
                LineSuspiciousness(
                    file_path=file_path,
                    line_number=line_num,
                    score=score,
                    failed_count=ef,
                    passed_count=ep,
                    total_failed=total_failed,
                    total_passed=total_passed,
                    code_content=code_text,
                )
            )

        # Sort descending by score, then tie-break by higher failed_count, then lower passed_count
        scored_lines.sort(
            key=lambda item: (item.score, item.failed_count, -item.passed_count),
            reverse=True,
        )
        return scored_lines
