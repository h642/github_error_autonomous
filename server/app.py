"""FastAPI web server providing live SSE streaming, dashboard endpoints, and GitHub PR publishing."""

import asyncio
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autonomous_repair.config import RepairConfig
from autonomous_repair.pipeline import AutonomousRepairPipeline, PipelineResult
from server.github_service import GitHubService

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(title="Autonomous Software Repair Dashboard", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared state
class RepairState:
    is_running: bool = False
    current_repo: str = ""
    pipeline_result: Optional[PipelineResult] = None
    event_queue: queue.Queue = queue.Queue()
    ready_for_approval_data: Optional[Dict] = None
    pr_published_data: Optional[Dict] = None
    patched_files: Dict[str, str] = {}

state = RepairState()


class StartRepairRequest(BaseModel):
    repo_path: str = "benchmark/repo"
    target_issue: Optional[str] = None
    provider: str = "gemini"
    model: str = "gemini-3.6-flash"
    max_iterations: int = 5
    enforce_property: bool = True
    enforce_mutation: bool = True


class ApprovePRRequest(BaseModel):
    github_token: Optional[str] = None
    branch_name: Optional[str] = None
    custom_title: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard index.html not found")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/api/config")
async def get_config():
    """Return environment status and default settings."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    github_token = os.getenv("GITHUB_TOKEN", "")

    return {
        "default_repo": str(WORKSPACE_ROOT / "benchmark" / "repo"),
        "providers": {
            "gemini": {
                "available": bool(gemini_key),
                "default_model": os.getenv("LLM_MODEL", "gemini-3.8-flash"),
            },
            "openai": {
                "available": bool(openai_key),
                "default_model": "gpt-4o",
            },
            "anthropic": {
                "available": bool(anthropic_key),
                "default_model": "claude-3-5-sonnet-20241022",
            },
            "mock": {
                "available": True,
                "default_model": "deterministic-benchmark",
            },
        },
        "has_github_token": bool(github_token),
    }


def _run_pipeline_worker(req: StartRepairRequest):
    """Background worker executing the repair pipeline and publishing events to SSE queue."""
    state.is_running = True
    state.current_repo = req.repo_path
    state.ready_for_approval_data = None
    state.pr_published_data = None

    def event_listener(event_type: str, data: dict):
        event_payload = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }
        state.event_queue.put(event_payload)
        if event_type == "ready_for_approval":
            state.ready_for_approval_data = data
            state.patched_files = data.get("patched_files", {})

    temp_clone_dir: Optional[str] = None
    try:
        raw_target = req.repo_path.strip()

        # Check if target is a remote GitHub URL or owner/repo shorthand
        is_git_remote = (
            raw_target.startswith("http://")
            or raw_target.startswith("https://")
            or raw_target.startswith("git@")
            or (bool(re.match(r"^[\w\-]+/[\w\-]+$", raw_target)) and not Path(raw_target).exists())
        )

        if is_git_remote:
            clone_url = raw_target if (raw_target.startswith("http") or raw_target.startswith("git@")) else f"https://github.com/{raw_target}.git"
            event_listener("log", {"level": "info", "message": f"Cloning remote repository {clone_url} into ephemeral sandbox..."})
            temp_clone_dir = tempfile.mkdtemp(prefix="repo_clone_")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, temp_clone_dir],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                target_path = Path(temp_clone_dir)
                event_listener("log", {"level": "success", "message": f"Repository cloned successfully into {target_path}."})
            except subprocess.CalledProcessError as cpe:
                err_msg = cpe.stderr.strip() if cpe.stderr else str(cpe)
                event_listener("log", {"level": "error", "message": f"Git clone failed: {err_msg}"})
                event_listener("pipeline_failed", {"error": f"Failed to clone {clone_url}: {err_msg}"})
                state.is_running = False
                return
            except subprocess.TimeoutExpired:
                event_listener("log", {"level": "error", "message": f"Git clone timed out after 90s for {clone_url}"})
                event_listener("pipeline_failed", {"error": "Git clone timed out."})
                state.is_running = False
                return
        else:
            target_path = Path(raw_target)
            if not target_path.is_absolute():
                target_path = (WORKSPACE_ROOT / target_path).resolve()

            if not target_path.exists():
                event_listener("log", {"level": "error", "message": f"Target repository path not found: {target_path}"})
                event_listener("pipeline_failed", {"error": f"Path not found: {target_path}"})
                state.is_running = False
                return

        config = RepairConfig(
            llm_provider=req.provider,
            llm_model=req.model,
            max_repair_iterations=req.max_iterations,
            enforce_property_gate=req.enforce_property,
            enforce_mutation_gate=req.enforce_mutation,
        )

        pipeline = AutonomousRepairPipeline(config=config, event_callback=event_listener)
        result = pipeline.run(target_path, target_issue=req.target_issue)
        state.pipeline_result = result

    except Exception as exc:
        event_listener("log", {"level": "error", "message": f"Pipeline exception: {str(exc)}"})
        event_listener("pipeline_failed", {"error": str(exc)})
    finally:
        state.is_running = False
        if temp_clone_dir and Path(temp_clone_dir).exists():
            shutil.rmtree(temp_clone_dir, ignore_errors=True)


@app.post("/api/repair/start")
async def start_repair(req: StartRepairRequest):
    """Launch the autonomous repair pipeline in the background."""
    if state.is_running:
        raise HTTPException(status_code=400, detail="A repair task is already running.")

    # Clear previous event queue
    while not state.event_queue.empty():
        try:
            state.event_queue.get_nowait()
        except Exception:
            pass

    thread = threading.Thread(target=_run_pipeline_worker, args=(req,), daemon=True)
    thread.start()

    return {"status": "started", "repo": req.repo_path, "provider": req.provider}


@app.get("/api/repair/stream")
async def stream_events(request: Request):
    """Server-Sent Events (SSE) stream delivering real-time pipeline events to the dashboard."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break

            try:
                # Check for new event in queue with a small timeout
                event = state.event_queue.get_nowait()
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                # Keep-alive heartbeat
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/repair/status")
async def get_repair_status():
    """Get current pipeline status and approval payload."""
    return {
        "is_running": state.is_running,
        "current_repo": state.current_repo,
        "ready_for_approval": state.ready_for_approval_data is not None,
        "approval_data": state.ready_for_approval_data,
        "pr_published": state.pr_published_data is not None,
        "pr_data": state.pr_published_data,
    }


@app.post("/api/repair/approve")
async def approve_and_push_pr(req: ApprovePRRequest):
    """Human-in-the-loop approval: create branch and push PR to GitHub."""
    if not state.ready_for_approval_data:
        raise HTTPException(status_code=400, detail="No verified repair patch is pending approval.")

    approval = state.ready_for_approval_data
    repo_target = state.current_repo or "benchmark/repo"
    branch = req.branch_name or approval.get("branch", "auto-repair/patch-1")
    title = req.custom_title or approval.get("title", "fix(repair): autonomous fault resolution")
    body = approval.get("markdown", "")

    # Extract patched file contents from state, candidate, or target path
    patched_files = dict(state.patched_files or {})
    if not patched_files and state.pipeline_result and state.pipeline_result.selected_candidate:
        from autonomous_repair.synthesis.diff_parser import parse_unified_diff
        patches = parse_unified_diff(state.pipeline_result.selected_candidate.unified_diff)
        target_path = Path(repo_target)
        if not target_path.is_absolute():
            target_path = (WORKSPACE_ROOT / target_path).resolve()

        for p in patches:
            rel = p.new_path or p.old_path
            f = target_path / rel
            if f.exists():
                patched_files[rel] = f.read_text(encoding="utf-8")

    # Publish PR via GitHub service
    result = GitHubService.publish_pull_request(
        repo_target=repo_target,
        branch_name=branch,
        pr_title=title,
        pr_body=body,
        patched_files=patched_files,
        github_token=req.github_token or os.getenv("GITHUB_TOKEN"),
    )

    state.pr_published_data = result

    # Emit event to SSE stream
    state.event_queue.put({
        "type": "pr_published",
        "data": result,
        "timestamp": time.time(),
    })

    return result
