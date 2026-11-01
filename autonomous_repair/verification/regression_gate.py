"""Gate 1: Baseline Regression and Unit Testing Gate (Stage 4)."""

import re
import time
from dataclasses import dataclass
from typing import Optional

from autonomous_repair.sandbox.base import AbstractSandbox, ExecutionResult


@dataclass
class RegressionGateResult:
    """Outcome of baseline regression testing after patch application."""
    passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration_seconds: float
    output: str
    failure_details: str = ""


class RegressionGate:
    """Runs baseline test suite to confirm all unit tests pass without regression."""

    def __init__(self, sandbox: AbstractSandbox):
        self.sandbox = sandbox

    def evaluate(self, test_command: Optional[str] = None) -> RegressionGateResult:
        start_time = time.perf_counter()
        # Run pytest with standard verbose flags
        cmd = test_command or "python3 -m pytest -v"
        exec_res: ExecutionResult = self.sandbox.execute(cmd)
        duration = time.perf_counter() - start_time

        combined = exec_res.combined_output
        passed_count = 0
        failed_count = 0

        # Parse pytest summary lines, e.g. "5 passed, 1 failed in 0.12s"
        summary_match = re.search(r"(=+.*?(\d+)\s+passed.*?(=+|\Z))", combined)
        pass_m = re.search(r"(\d+)\s+passed", combined)
        fail_m = re.search(r"(\d+)\s+failed", combined)
        error_m = re.search(r"(\d+)\s+error", combined)

        if pass_m:
            passed_count = int(pass_m.group(1))
        if fail_m:
            failed_count += int(fail_m.group(1))
        if error_m:
            failed_count += int(error_m.group(1))

        total_tests = passed_count + failed_count
        if total_tests == 0 and exec_res.success:
            # If no explicit summary but exited 0
            total_tests = 1
            passed_count = 1

        is_passed = (exec_res.exit_code == 0 and failed_count == 0)

        failure_details = ""
        if not is_passed:
            # Extract failure messages or stack traces
            lines = combined.splitlines()
            failures = [l for l in lines if "FAILED" in l or "ERROR" in l]
            failure_details = "\n".join(failures[:10]) or exec_res.stderr

        return RegressionGateResult(
            passed=is_passed,
            total_tests=total_tests,
            passed_tests=passed_count,
            failed_tests=failed_count,
            duration_seconds=duration,
            output=combined,
            failure_details=failure_details,
        )
