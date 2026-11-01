"""Docker-isolated execution sandbox (Stage 1)."""

import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Union

from autonomous_repair.sandbox.base import (
    AbstractSandbox,
    ExecutionResult,
    ManifestDetector,
    ManifestInfo,
)


class DockerSandbox(AbstractSandbox):
    """Isolated execution environment running inside an ephemeral Docker container."""

    def __init__(
        self,
        source_repo_path: Union[str, Path],
        image: str = "python:3.11-slim",
        timeout_seconds: int = 45,
    ):
        self.source_repo_path = Path(source_repo_path).resolve()
        self.image = image
        self.timeout_seconds = timeout_seconds
        self._temp_dir: Optional[Path] = None
        self._container = None
        self._docker_client = None
        self._manifest_info: Optional[ManifestInfo] = None

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker CLI / daemon is accessible."""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return shutil.which("docker") is not None

    def initialize(self) -> None:
        if not self.is_docker_available():
            raise RuntimeError("Docker is not available or Docker daemon is not running.")

        try:
            import docker
            self._docker_client = docker.from_env()
        except ImportError:
            raise RuntimeError("The 'docker' python library is not installed.")

        temp_dir_path = tempfile.mkdtemp(prefix="repair_docker_")
        self._temp_dir = Path(temp_dir_path).resolve()
        shutil.copytree(self.source_repo_path, self._temp_dir, dirs_exist_ok=True)
        self._manifest_info = ManifestDetector.detect(self._temp_dir)

        # Launch ephemeral container with repo mounted into /workspace
        self._container = self._docker_client.containers.run(
            image=self.image,
            command="sleep infinity",
            volumes={str(self._temp_dir): {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            detach=True,
            remove=True,
        )

    @property
    def sandbox_dir(self) -> Path:
        if self._temp_dir is None:
            raise RuntimeError("Docker sandbox not initialized.")
        return self._temp_dir

    def execute(self, cmd: str, timeout: Optional[int] = None) -> ExecutionResult:
        if self._container is None:
            raise RuntimeError("Docker container not running.")

        start = time.perf_counter()
        exec_res = self._container.exec_run(
            cmd=["/bin/sh", "-c", cmd],
            workdir="/workspace",
            environment={"PYTHONPATH": "/workspace"},
        )
        elapsed = time.perf_counter() - start
        output_str = exec_res.output.decode("utf-8", errors="replace") if exec_res.output else ""

        return ExecutionResult(
            command=cmd,
            exit_code=exec_res.exit_code,
            stdout=output_str if exec_res.exit_code == 0 else "",
            stderr=output_str if exec_res.exit_code != 0 else "",
            duration_seconds=elapsed,
            success=(exec_res.exit_code == 0),
        )

    def read_file(self, relative_path: str) -> str:
        target = (self.sandbox_dir / relative_path).resolve()
        return target.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> None:
        target = (self.sandbox_dir / relative_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def apply_patch(self, patch_diff: str) -> ExecutionResult:
        patch_file = self.sandbox_dir / ".candidate_patch.diff"
        patch_file.write_text(patch_diff, encoding="utf-8")
        res = self.execute("patch -p1 < .candidate_patch.diff || git apply .candidate_patch.diff")
        if patch_file.exists():
            patch_file.unlink()
        return res

    def run_tests(self, test_command: Optional[str] = None) -> ExecutionResult:
        cmd = test_command or "python3 -m pytest"
        return self.execute(cmd)

    def cleanup(self) -> None:
        if self._container:
            try:
                self._container.stop(timeout=2)
            except Exception:
                pass
            self._container = None
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
