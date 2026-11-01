"""GitHub integration service for automated branch creation and Pull Request publishing."""

import base64
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional
import httpx


class GitHubService:
    """Manages publishing autonomous patches to GitHub repositories."""

    @staticmethod
    def publish_pull_request(
        repo_target: str,
        branch_name: str,
        pr_title: str,
        pr_body: str,
        patched_files: Dict[str, str],  # rel_path -> full new content
        github_token: Optional[str] = None,
        base_branch: str = "main",
    ) -> Dict:
        """Create a feature branch and submit a Pull Request via GitHub REST API or local git."""
        token = github_token or os.getenv("GITHUB_TOKEN")
        
        # Check if target is a GitHub repo identifier: "owner/repo" or "https://github.com/owner/repo"
        github_match = re.search(r"github\.com[/:]([^/]+)/([^/\.]+)(?:\.git)?", repo_target)
        if not github_match and "/" in repo_target and not Path(repo_target).exists():
            parts = repo_target.strip().split("/")
            if len(parts) == 2:
                owner, repo = parts[0], parts[1]
                github_match = True
        elif github_match:
            owner, repo = github_match.group(1), github_match.group(2)
        else:
            owner, repo = None, None

        # If we have GitHub owner/repo and a token, use the GitHub REST API
        if owner and repo and token:
            return GitHubService._create_github_api_pr(
                owner=owner,
                repo=repo,
                token=token,
                branch_name=branch_name,
                pr_title=pr_title,
                pr_body=pr_body,
                patched_files=patched_files,
                base_branch=base_branch,
            )

        # Fallback to local git repository operations
        local_path = Path(repo_target).resolve() if Path(repo_target).exists() else None
        if local_path and (local_path / ".git").exists():
            return GitHubService._create_local_git_branch_and_commit(
                repo_path=local_path,
                branch_name=branch_name,
                pr_title=pr_title,
                pr_body=pr_body,
                patched_files=patched_files,
            )

        # Target is a remote repository but no GitHub token was provided
        if owner and repo and not token:
            return {
                "success": False,
                "needs_token": True,
                "pr_url": "",
                "branch": branch_name,
                "message": (
                    f"GitHub Personal Access Token required: Cannot create a live Pull Request on https://github.com/{owner}/{repo} "
                    f"without authentication. Please enter your GitHub Token (classic token with 'repo' scope or fine-grained token) "
                    f"in the approval box or add GITHUB_TOKEN in your .env file."
                ),
            }

        return {
            "success": False,
            "pr_url": "",
            "branch": branch_name,
            "message": f"Cannot publish PR: '{repo_target}' is neither an accessible local git repository nor an authenticated remote GitHub repository.",
        }

    @staticmethod
    def _create_github_api_pr(
        owner: str,
        repo: str,
        token: str,
        branch_name: str,
        pr_title: str,
        pr_body: str,
        patched_files: Dict[str, str],
        base_branch: str = "main",
    ) -> Dict:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SDG-Autonomous-Repair-Pipeline",
        }

        with httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30.0) as client:
            # 0. Identify authenticated user to determine if forking is required
            auth_user = None
            try:
                user_resp = client.get("/user")
                if user_resp.status_code == 200:
                    auth_user = user_resp.json().get("login")
            except Exception:
                pass

            is_external_repo = bool(auth_user and (owner.lower() != auth_user.lower()))
            target_owner = auth_user if is_external_repo else owner

            # If targeting an external repository, automatically fork to authenticated user's account
            if is_external_repo:
                fork_check = client.get(f"/repos/{auth_user}/{repo}")
                if fork_check.status_code != 200:
                    fork_res = client.post(f"/repos/{owner}/{repo}/forks")
                    if fork_res.status_code not in (200, 202):
                        return {
                            "success": False,
                            "message": f"Failed to automatically fork {owner}/{repo} into {auth_user}/{repo}: {fork_res.text}",
                        }
                    # Wait for GitHub to provision the new fork
                    for _ in range(10):
                        time.sleep(1.5)
                        if client.get(f"/repos/{auth_user}/{repo}").status_code == 200:
                            break

            # 1. Get base branch commit SHA from upstream
            ref_resp = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
            if ref_resp.status_code != 200:
                # Try master
                ref_resp = client.get(f"/repos/{owner}/{repo}/git/ref/heads/master")
                if ref_resp.status_code == 200:
                    base_branch = "master"
                else:
                    # Query repository metadata for default branch
                    repo_meta = client.get(f"/repos/{owner}/{repo}")
                    if repo_meta.status_code == 200:
                        detected_base = repo_meta.json().get("default_branch", "main")
                        ref_resp = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{detected_base}")
                        if ref_resp.status_code == 200:
                            base_branch = detected_base
                        else:
                            return {
                                "success": False,
                                "message": f"Failed to fetch base branch reference for {owner}/{repo}: {ref_resp.text}",
                            }
                    else:
                        return {
                            "success": False,
                            "message": f"Could not access repository {owner}/{repo} (HTTP {repo_meta.status_code}). Please verify your token has 'repo' access: {repo_meta.text}",
                        }

            base_sha = ref_resp.json()["object"]["sha"]

            # 2. Create new branch on target repository (fork if external, or upstream if owned)
            create_branch_payload = {
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha,
            }
            branch_resp = client.post(f"/repos/{target_owner}/{repo}/git/refs", json=create_branch_payload)
            if branch_resp.status_code == 422:
                # Branch already exists; append unique timestamp
                branch_name = f"{branch_name}-{int(time.time())}"
                create_branch_payload["ref"] = f"refs/heads/{branch_name}"
                branch_resp = client.post(f"/repos/{target_owner}/{repo}/git/refs", json=create_branch_payload)

            if branch_resp.status_code not in (200, 201):
                return {
                    "success": False,
                    "message": f"Failed to create branch {branch_name} on {target_owner}/{repo}: {branch_resp.text}",
                }

            # 3. Commit modified files onto branch on target_owner/repo
            for file_path, content in patched_files.items():
                file_resp = client.get(
                    f"/repos/{target_owner}/{repo}/contents/{file_path}",
                    params={"ref": branch_name},
                )
                file_sha = file_resp.json().get("sha") if file_resp.status_code == 200 else None

                encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                commit_payload = {
                    "message": f"fix(repair): autonomous patch for {file_path}",
                    "content": encoded_content,
                    "branch": branch_name,
                }
                if file_sha:
                    commit_payload["sha"] = file_sha

                put_resp = client.put(f"/repos/{target_owner}/{repo}/contents/{file_path}", json=commit_payload)
                if put_resp.status_code not in (200, 201):
                    return {
                        "success": False,
                        "message": f"Failed to commit file {file_path} to {target_owner}/{repo}: {put_resp.text}",
                    }

            # Also commit PULL_REQUEST.md verification report to branch
            if pr_body:
                try:
                    encoded_md = base64.b64encode(pr_body.encode("utf-8")).decode("utf-8")
                    md_resp = client.get(
                        f"/repos/{target_owner}/{repo}/contents/PULL_REQUEST.md",
                        params={"ref": branch_name},
                    )
                    md_sha = md_resp.json().get("sha") if md_resp.status_code == 200 else None
                    md_payload = {
                        "message": "docs(audit): autonomous repair verification report",
                        "content": encoded_md,
                        "branch": branch_name,
                    }
                    if md_sha:
                        md_payload["sha"] = md_sha
                    client.put(f"/repos/{target_owner}/{repo}/contents/PULL_REQUEST.md", json=md_payload)
                except Exception:
                    pass

            # 4. Open Pull Request on upstream repository (with cross-repo head if forked)
            pr_head = f"{auth_user}:{branch_name}" if is_external_repo else branch_name
            pr_payload = {
                "title": pr_title,
                "body": pr_body,
                "head": pr_head,
                "base": base_branch,
            }
            pr_resp = client.post(f"/repos/{owner}/{repo}/pulls", json=pr_payload)
            if pr_resp.status_code in (200, 201):
                pr_data = pr_resp.json()
                return {
                    "success": True,
                    "pr_url": pr_data.get("html_url", ""),
                    "pr_number": pr_data.get("number", 0),
                    "branch": branch_name,
                    "is_simulated": False,
                    "message": f"Pull Request #{pr_data.get('number')} successfully created on GitHub!",
                }
            else:
                err_text = pr_resp.text
                try:
                    err_json = pr_resp.json()
                    err_text = err_json.get("message", err_text)
                    if "errors" in err_json:
                        err_text += " - " + "; ".join(e.get("message", str(e)) for e in err_json["errors"])
                except Exception:
                    pass
                return {
                    "success": False,
                    "message": f"GitHub API rejected Pull Request (HTTP {pr_resp.status_code}): {err_text}",
                }

    @staticmethod
    def _create_local_git_branch_and_commit(
        repo_path: Path,
        branch_name: str,
        pr_title: str,
        pr_body: str,
        patched_files: Dict[str, str],
    ) -> Dict:
        """Create and switch to a git branch on local repository and commit changes."""
        try:
            # Create and switch to new branch
            subprocess.run(
                ["git", "checkout", "-B", branch_name],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
            )

            # Write modified files
            for rel_path, content in patched_files.items():
                target = repo_path / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                subprocess.run(["git", "add", rel_path], cwd=str(repo_path), check=True)

            # Write PR description artifact
            pr_file = repo_path / "PULL_REQUEST.md"
            pr_file.write_text(pr_body, encoding="utf-8")
            subprocess.run(["git", "add", "PULL_REQUEST.md"], cwd=str(repo_path), check=True)

            # Commit
            commit_msg = f"{pr_title}\n\nAutomated patch generated by SDG-Autonomous-Repair-Pipeline"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(repo_path), check=True)

            # Check if remote origin is configured and push branch
            pushed_to_remote = False
            remote_url = ""
            try:
                rem_res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(repo_path), capture_output=True, text=True)
                if rem_res.returncode == 0 and rem_res.stdout.strip():
                    remote_url = rem_res.stdout.strip()
                    push_res = subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=str(repo_path), capture_output=True, text=True, timeout=15)
                    if push_res.returncode == 0:
                        pushed_to_remote = True
            except Exception:
                pass

            msg = (
                f"Successfully committed verified patch and pushed branch '{branch_name}' to {remote_url}."
                if pushed_to_remote
                else f"Successfully created local branch '{branch_name}' and committed verified patch."
            )

            return {
                "success": True,
                "pr_url": f"{remote_url}/tree/{branch_name}" if pushed_to_remote else f"local://{repo_path}/branches/{branch_name}",
                "branch": branch_name,
                "is_simulated": False,
                "message": msg,
            }
        except subprocess.CalledProcessError as exc:
            return {
                "success": False,
                "message": f"Local git operation failed: {exc.stderr.decode() if exc.stderr else str(exc)}",
            }
