"""Sandbox module exports and automatic environment factory."""

from pathlib import Path
from typing import Union

from autonomous_repair.sandbox.base import (
    AbstractSandbox,
    ExecutionResult,
    ManifestDetector,
    ManifestInfo,
)
from autonomous_repair.sandbox.subprocess_venv import SubprocessVenvSandbox
from autonomous_repair.sandbox.docker_sandbox import DockerSandbox


def create_sandbox(
    repo_path: Union[str, Path],
    prefer_docker: bool = False,
    timeout_seconds: int = 45,
) -> AbstractSandbox:
    """Factory creating an isolated sandbox (Docker if requested and available, else Subprocess)."""
    if prefer_docker and DockerSandbox.is_docker_available():
        try:
            sandbox = DockerSandbox(repo_path, timeout_seconds=timeout_seconds)
            sandbox.initialize()
            return sandbox
        except Exception:
            # Fallback seamlessly to subprocess venv sandbox
            pass

    sandbox = SubprocessVenvSandbox(repo_path, timeout_seconds=timeout_seconds)
    sandbox.initialize()
    return sandbox


__all__ = [
    "AbstractSandbox",
    "ExecutionResult",
    "ManifestDetector",
    "ManifestInfo",
    "SubprocessVenvSandbox",
    "DockerSandbox",
    "create_sandbox",
]
