"""GitHub Issue Fetcher: Retrieves issue title, description, and metadata via GitHub API."""

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple
import httpx


@dataclass
class IssueContext:
    """Represents a target issue or bug report."""
    owner: str
    repo: str
    issue_number: Optional[int]
    title: str
    description: str
    url: str
    is_github_issue: bool = True


class IssueFetcher:
    """Fetches issue details from GitHub or wraps freeform bug descriptions."""

    @staticmethod
    def parse_issue_url(input_str: str) -> Optional[Tuple[str, str, int]]:
        """Extract (owner, repo, issue_number) from various GitHub URL / shorthand formats."""
        # Standard: https://github.com/owner/repo/issues/123
        match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", input_str)
        if match:
            return match.group(1), match.group(2), int(match.group(3))

        # Shorthand: owner/repo#123
        match_short = re.search(r"^([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)#(\d+)$", input_str.strip())
        if match_short:
            return match_short.group(1), match_short.group(2), int(match_short.group(3))

        return None

    @classmethod
    def resolve_issue(cls, issue_input: str, github_token: Optional[str] = None) -> IssueContext:
        """Fetch issue from GitHub or create custom IssueContext from description."""
        cleaned = issue_input.strip()
        parsed = cls.parse_issue_url(cleaned)

        if parsed:
            owner, repo, issue_num = parsed
            token = github_token or os.getenv("GITHUB_TOKEN")
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "SDG-Autonomous-Repair-Pipeline",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}"

            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(api_url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        return IssueContext(
                            owner=owner,
                            repo=repo,
                            issue_number=issue_num,
                            title=data.get("title", f"Issue #{issue_num}"),
                            description=data.get("body", "") or "No description provided.",
                            url=data.get("html_url", cleaned),
                            is_github_issue=True,
                        )
                    else:
                        # Fallback if API rate limited or private
                        return IssueContext(
                            owner=owner,
                            repo=repo,
                            issue_number=issue_num,
                            title=f"GitHub Issue #{issue_num}",
                            description=f"Issue #{issue_num} on {owner}/{repo}",
                            url=cleaned,
                            is_github_issue=True,
                        )
            except Exception:
                return IssueContext(
                    owner=owner,
                    repo=repo,
                    issue_number=issue_num,
                    title=f"GitHub Issue #{issue_num}",
                    description=f"Targeting issue #{issue_num} from {cleaned}",
                    url=cleaned,
                    is_github_issue=True,
                )

        # Freeform text / bug report description
        first_line = cleaned.splitlines()[0][:80] if cleaned else "Custom Bug Report"
        return IssueContext(
            owner="",
            repo="",
            issue_number=None,
            title=first_line,
            description=cleaned,
            url="",
            is_github_issue=False,
        )
