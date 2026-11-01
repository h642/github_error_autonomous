"""Base interfaces and manifest detection for Secure Sandboxing & Ingestion (Stage 1)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ExecutionResult:
    """Represents the outcome of a command execution inside the sandbox."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    success: bool
    timed_out: bool = False

    @property
    def combined_output(self) -> str:
        out = []
        if self.stdout:
            out.append(self.stdout)
        if self.stderr:
            out.append(self.stderr)
        return "\n".join(out)


@dataclass
class ManifestInfo:
    """Detected dependency manifests and ecosystem conventions."""
    ecosystem: str  # "python", "javascript", "java", etc.
    manifest_files: List[Path]
    test_framework: str  # "pytest", "npm-test", "mvn-test"
    default_test_command: str


class ManifestDetector:
    """Scans a repository to automatically detect dependency manifests."""

    @staticmethod
    def detect(repo_path: Path) -> ManifestInfo:
        repo = Path(repo_path)
        manifests: List[Path] = []

        # Check Python
        pyproject = repo / "pyproject.toml"
        reqs = repo / "requirements.txt"
        setup_py = repo / "setup.py"
        if pyproject.exists():
            manifests.append(pyproject)
        if reqs.exists():
            manifests.append(reqs)
        if setup_py.exists():
            manifests.append(setup_py)

        if manifests:
            return ManifestInfo(
                ecosystem="python",
                manifest_files=manifests,
                test_framework="pytest",
                default_test_command="python3 -m pytest -v"
            )

        # Check JavaScript / Node
        pkg_json = repo / "package.json"
        if pkg_json.exists():
            manifests.append(pkg_json)
            return ManifestInfo(
                ecosystem="javascript",
                manifest_files=manifests,
                test_framework="npm",
                default_test_command="npm test"
            )

        # Check Java / Maven
        pom = repo / "pom.xml"
        if pom.exists():
            manifests.append(pom)
            return ManifestInfo(
                ecosystem="java",
                manifest_files=manifests,
                test_framework="maven",
                default_test_command="mvn test"
            )

        # Fallback to python generic
        return ManifestInfo(
            ecosystem="unknown",
            manifest_files=[],
            test_framework="pytest",
            default_test_command="python3 -m pytest"
        )


class AbstractSandbox(ABC):
    """Abstract sandbox environment for running isolated repository operations."""

    @abstractmethod
    def initialize(self) -> None:
        """Provision the sandbox environment and copy repository files."""
        pass

    @abstractmethod
    def execute(self, cmd: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute a shell command inside the sandbox."""
        pass

    @abstractmethod
    def read_file(self, relative_path: str) -> str:
        """Read text content from a file within the sandbox."""
        pass

    @abstractmethod
    def write_file(self, relative_path: str, content: str) -> None:
        """Write text content to a file within the sandbox."""
        pass

    @abstractmethod
    def apply_patch(self, patch_diff: str) -> ExecutionResult:
        """Apply a unified git diff patch to the sandbox repository."""
        pass

    @abstractmethod
    def run_tests(self, test_command: Optional[str] = None) -> ExecutionResult:
        """Run the test suite inside the isolated sandbox."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Destroy ephemeral resources."""
        pass

    @property
    @abstractmethod
    def sandbox_dir(self) -> Path:
        """Return the root path of the sandbox on the host or mount."""
        pass
