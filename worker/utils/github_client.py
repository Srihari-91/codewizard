"""
GitHub API client — wraps PyGithub for PR operations.
"""

import os
import structlog
import httpx
from github import Github, GithubIntegration
from config import settings

logger = structlog.get_logger(__name__)


class GitHubClient:
    def __init__(self):
        self._pat = settings.GITHUB_PAT
        self._gh = Github(self._pat) if self._pat else None

    def get_pr_files(self, repo_full_name: str, pr_number: int) -> list:
        """Returns list of changed files with patch/diff data."""
        try:
            repo = self._gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            files = []
            for f in pr.get_files():
                files.append({
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "patch": f.patch or "",
                    "blob_url": f.blob_url,
                    "raw_url": f.raw_url,
                })
            return files
        except Exception as e:
            logger.error("github_get_files_failed", error=str(e))
            return []

    def get_file_content(self, repo_full_name: str, path: str, ref: str) -> str:
        """Fetch raw file content at a specific ref."""
        try:
            repo = self._gh.get_repo(repo_full_name)
            content = repo.get_contents(path, ref=ref)
            return content.decoded_content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("github_get_content_failed", path=path, error=str(e))
            return ""

    def apply_fix(self, repo_full_name: str, pr_number: int, fix: dict) -> bool:
        """
        Creates a new branch with the fix applied and opens a PR.
        Returns True on success.
        """
        try:
            repo = self._gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            head_ref = pr.head.ref
            head_sha = pr.head.sha

            # Create fix branch
            fix_branch = f"codewizard/fix-{pr_number}-{fix['rule_id'][:20]}"
            try:
                repo.create_git_ref(f"refs/heads/{fix_branch}", head_sha)
            except Exception:
                # Branch may already exist
                pass

            # Update file
            file_path = fix["file"]
            try:
                existing = repo.get_contents(file_path, ref=fix_branch)
                repo.update_file(
                    file_path,
                    f"fix({fix['rule_id']}): {fix['description'][:60]}",
                    fix["fix_code"],
                    existing.sha,
                    branch=fix_branch,
                )
            except Exception as e:
                logger.error("apply_fix_file_update_failed", error=str(e))
                return False

            # Create PR
            repo.create_pull(
                title=f"[CodeWizard] Fix: {fix['description'][:60]}",
                body=f"Automated fix for {fix['severity']} issue in `{file_path}`.\n\n"
                     f"Rule: `{fix['rule_id']}`\nConfidence: {fix['confidence']}%",
                head=fix_branch,
                base=head_ref,
            )
            return True
        except Exception as e:
            logger.error("apply_fix_failed", error=str(e))
            return False

    def post_or_update_comment(
        self, repo_full_name: str, pr_number: int, body: str, record_id
    ):
        """Post a new PR comment or update the existing CodeWizard comment."""
        try:
            repo = self._gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)

            # Look for existing CodeWizard comment
            for comment in pr.get_issue_comments():
                if "CodeWizard AI Review" in comment.body:
                    comment.edit(body)
                    logger.info("comment_updated", pr=pr_number)
                    return

            # Create new
            pr.create_issue_comment(body)
            logger.info("comment_posted", pr=pr_number)
        except Exception as e:
            logger.error("post_comment_failed", error=str(e))
