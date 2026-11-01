"""Test instrumentation and line coverage tracing per test (Stage 2: SBFL)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from autonomous_repair.sandbox.base import AbstractSandbox


@dataclass
class TestCoverageResult:
    """Coverage trace and outcome for an individual test case."""
    __test__ = False
    test_id: str
    passed: bool
    executed_lines: Dict[str, Set[int]]  # file_path -> set of line numbers
    duration_seconds: float
    error_message: str = ""


class CoverageTracer:
    """Discovers test cases and collects individual statement coverage profiles."""

    def __init__(self, sandbox: AbstractSandbox, source_subpath: str = ""):
        self.sandbox = sandbox
        self.source_subpath = source_subpath

    def discover_tests(self) -> List[str]:
        """Discover all test IDs in the sandbox using pytest --collect-only."""
        res = self.sandbox.execute("python3 -m pytest --collect-only")
        test_ids: List[str] = []
        if res.stdout:
            for line in res.stdout.strip().splitlines():
                line = line.strip()
                # Matches node IDs like `tests/test_pension.py::test_early_retirement_penalty_applied`
                if "::" in line and not line.startswith("<") and not line.startswith("="):
                    tid = line.split()[0]
                    # Exclude property tests during fault localization to focus SBFL on baseline failures
                    if "test_properties" not in tid:
                        test_ids.append(tid)

        return test_ids

    def trace_test(self, test_id: str) -> TestCoverageResult:
        """Run a single test under coverage.py and extract covered lines."""
        # Use an isolated data file for each test
        cov_file = f".coverage_{abs(hash(test_id)) % 100000}"
        
        # We specify source directory to avoid tracking stdlib and site-packages
        source_opt = f"--source={self.source_subpath}" if self.source_subpath else "--source=."
        cmd = f"python3 -m coverage run --data-file={cov_file} {source_opt} -m pytest {test_id}"
        
        exec_res = self.sandbox.execute(cmd)
        passed = (exec_res.exit_code == 0)

        # Extract coverage data via python script in sandbox
        extractor_script = f"""
import json, sys
from coverage import CoverageData

cov_data = CoverageData('{cov_file}')
cov_data.read()
results = {{}}
for filename in cov_data.measured_files():
    # Only keep project files, exclude test files themselves
    if 'tests' not in filename and 'site-packages' not in filename:
        lines = cov_data.lines(filename)
        if lines:
            results[filename] = sorted(list(lines))
print(json.dumps(results))
"""
        json_res = self.sandbox.execute(f"python3 -c \"{extractor_script.strip()}\"")
        executed_lines: Dict[str, Set[int]] = {}
        if json_res.exit_code == 0 and json_res.stdout.strip():
            try:
                raw_data = json.loads(json_res.stdout.strip())
                for file_path, lines in raw_data.items():
                    # Normalize path relative to sandbox directory
                    try:
                        rel_path = str(Path(file_path).relative_to(self.sandbox.sandbox_dir))
                    except ValueError:
                        rel_path = file_path
                    executed_lines[rel_path] = set(lines)
            except Exception:
                pass

        # Cleanup coverage file
        cleanup_file = self.sandbox.sandbox_dir / cov_file
        if cleanup_file.exists():
            cleanup_file.unlink()

        return TestCoverageResult(
            test_id=test_id,
            passed=passed,
            executed_lines=executed_lines,
            duration_seconds=exec_res.duration_seconds,
            error_message=exec_res.stderr if not passed else "",
        )

    def trace_all(self, test_ids: Optional[List[str]] = None) -> List[TestCoverageResult]:
        """Collect traces across all tests."""
        ids = test_ids or self.discover_tests()
        results: List[TestCoverageResult] = []
        for tid in ids:
            res = self.trace_test(tid)
            results.append(res)
        return results
