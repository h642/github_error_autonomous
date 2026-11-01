"""Ephemeral Subprocess & Virtual Environment Sandbox (Stage 1)."""

import os
import shutil
import subprocess
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


class SubprocessVenvSandbox(AbstractSandbox):
    """Secure, isolated ephemeral directory sandbox using subprocess execution."""

    def __init__(self, source_repo_path: Union[str, Path], timeout_seconds: int = 45):
        self.source_repo_path = Path(source_repo_path).resolve()
        self.timeout_seconds = timeout_seconds
        self._temp_dir: Optional[Path] = None
        self._manifest_info: Optional[ManifestInfo] = None

    def initialize(self) -> None:
        """Create a fresh ephemeral directory and copy the source repository."""
        if not self.source_repo_path.exists():
            raise FileNotFoundError(f"Source repo not found at: {self.source_repo_path}")

        # Create isolated ephemeral scratch dir
        temp_dir_path = tempfile.mkdtemp(prefix="repair_sandbox_")
        self._temp_dir = Path(temp_dir_path).resolve()

        # Copy repository files ignoring caches, git metadata, and active virtualenvs
        def ignore_patterns(path, names):
            ignored = set()
            for name in names:
                if name in {".git", "__pycache__", ".pytest_cache", "venv", ".venv", ".mypy_cache"}:
                    ignored.add(name)
                elif name.endswith(".pyc") or name.endswith(".pyo"):
                    ignored.add(name)
            return ignored

        shutil.copytree(self.source_repo_path, self._temp_dir, dirs_exist_ok=True, ignore=ignore_patterns)

        # Write environment compatibility shims for modern Python 3.13+ / NumPy 2.0 runtime
        sitecustomize_path = self._temp_dir / "sitecustomize.py"
        sitecustomize_content = '''# Auto-injected sandbox compatibility layer
import sys

# NumPy 2.0 backwards compatibility aliases (np.unicode_ -> str, np.string_ -> bytes)
try:
    import numpy as np
    if not hasattr(np, "unicode_"):
        np.unicode_ = str
    if not hasattr(np, "string_"):
        np.string_ = bytes
    if not hasattr(np, "bool8"):
        np.bool8 = bool
except Exception:
    pass

# Python 3.13+ PEP 594 cgi module backport
try:
    import cgi
except ImportError:
    try:
        import legacy_cgi as cgi
        sys.modules["cgi"] = cgi
    except Exception:
        pass
'''
        sitecustomize_path.write_text(sitecustomize_content, encoding="utf-8")

        # Detect manifests
        self._manifest_info = ManifestDetector.detect(self._temp_dir)

    @property
    def sandbox_dir(self) -> Path:
        if self._temp_dir is None:
            raise RuntimeError("Sandbox has not been initialized. Call initialize() first.")
        return self._temp_dir

    @property
    def manifest_info(self) -> ManifestInfo:
        if self._manifest_info is None:
            raise RuntimeError("Sandbox has not been initialized.")
        return self._manifest_info

    def execute(self, cmd: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute a command inside the isolated sandbox."""
        if self._temp_dir is None:
            raise RuntimeError("Sandbox not initialized.")

        timeout_val = timeout or self.timeout_seconds
        env = os.environ.copy()
        # Ensure sandbox root and src/ directory are in PYTHONPATH for both flat and src-layout repos
        python_paths = [str(self._temp_dir)]
        src_candidate = self._temp_dir / "src"
        if src_candidate.exists():
            python_paths.append(str(src_candidate))
        if env.get("PYTHONPATH"):
            python_paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        # Prevent python bytecode caching pollution
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        start_time = time.perf_counter()
        try:
            process = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self._temp_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_val,
            )
            elapsed = time.perf_counter() - start_time
            return ExecutionResult(
                command=cmd,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                duration_seconds=elapsed,
                success=(process.returncode == 0),
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - start_time
            stdout_text = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr_text = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return ExecutionResult(
                command=cmd,
                exit_code=-1,
                stdout=stdout_text,
                stderr=f"{stderr_text}\n[Command timed out after {timeout_val}s]",
                duration_seconds=elapsed,
                success=False,
                timed_out=True,
            )

    def _resolve_target(self, relative_path: str) -> Path:
        target = (self.sandbox_dir / relative_path).resolve()
        # Path traversal guard
        if not str(target).startswith(str(self.sandbox_dir)):
            raise PermissionError(f"Attempted path traversal access: {relative_path}")
        if not target.exists():
            clean_rel = relative_path.lstrip("./")
            for cand in self.sandbox_dir.rglob(Path(relative_path).name):
                if str(cand).endswith(clean_rel) or cand.name == Path(relative_path).name:
                    return cand
        return target

    def read_file(self, relative_path: str) -> str:
        target = self._resolve_target(relative_path)
        return target.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> None:
        target = self._resolve_target(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def apply_patch(self, patch_diff: str) -> ExecutionResult:
        """Apply a unified diff patch to the sandbox repository."""
        # First attempt: pure Python unified patch engine (safe, deterministic, cross-platform)
        from autonomous_repair.synthesis.diff_parser import apply_unified_diff_to_dir
        py_patch_ok, py_patch_err = apply_unified_diff_to_dir(self.sandbox_dir, patch_diff)
        if py_patch_ok:
            return ExecutionResult(
                command="internal_unified_patch",
                exit_code=0,
                stdout="Patch applied successfully via internal patch engine.",
                stderr="",
                duration_seconds=0.01,
                success=True,
            )

        # Second attempt: git apply (if git repository)
        patch_file = self.sandbox_dir / ".patch_candidate.diff"
        patch_file.write_text(patch_diff, encoding="utf-8")
        git_res = self.execute("git apply --whitespace=nowarn .patch_candidate.diff")
        if git_res.success:
            if patch_file.exists():
                patch_file.unlink()
            return git_res

        # Third attempt: batch non-interactive patch tool
        patch_res = self.execute("patch --batch -N -p1 < .patch_candidate.diff")
        if patch_res.success:
            if patch_file.exists():
                patch_file.unlink()
            return patch_res

        if patch_file.exists():
            patch_file.unlink()

        return ExecutionResult(
            command="apply_patch",
            exit_code=1,
            stdout="",
            stderr=f"Patch application failed. Internal: {py_patch_err}; Git: {git_res.stderr}; Patch: {patch_res.stderr}",
            duration_seconds=0.01,
            success=False,
        )

    def run_tests(self, test_command: Optional[str] = None) -> ExecutionResult:
        """Run the test suite inside the isolated sandbox."""
        cmd = test_command or self.manifest_info.default_test_command
        return self.execute(cmd)

    def cleanup(self) -> None:
        """Destroy ephemeral temporary directory."""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
