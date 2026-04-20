"""
analyze_pr.run — Full CodeWizard AI pipeline:
  1. Fetch PR diff from GitHub
  2. Filter / validate files
  3. Update Neo4j dependency graph
  4. Compute risk scores
  5. Semgrep static analysis
  6. LLM fix generation
  7. Sandbox validation
  8. Post PR comment / create fix branch
"""

import os
import sys
import structlog

sys.path.insert(0, "/app")

from config import settings
from analyzer.diff_parser import DiffParser
from analyzer.graph.neo4j_client import Neo4jClient
from analyzer.scoring.risk_scorer import RiskScorer
from analyzer.static.semgrep_runner import SemgrepRunner
from llm.router import LLMRouter
from sandbox.executor import SandboxExecutor
from worker.utils.github_client import GitHubClient
from worker.utils.comment_builder import CommentBuilder
from db.sync_db import SyncDB

logger = structlog.get_logger(__name__)

IGNORE_PATHS = {
    "node_modules/", "dist/", "build/", "out/", "coverage/",
    ".mypy_cache/", ".pytest_cache/", "__pycache__/", ".next/",
    ".nuxt/", "target/", "venv/", ".env/", ".idea/", ".vscode/",
    ".git/", ".github/", "migrations/", "logs/", "tmp/", "temp/", ".cache/"
}

IGNORE_EXTENSIONS = {
    ".lock", ".min.js", ".min.css", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".tar",
    ".gz", ".rar", ".map", ".bundle.js", ".csv", ".jsonl",
}

ALLOWED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}


def run(payload: dict):
    """RQ job entry point — synchronous wrapper."""
    logger.info("job_started", payload=payload)

    record_id = payload["record_id"]
    repo_full_name = payload["repo_full_name"]
    pr_number = payload["pr_number"]
    installation_id = payload.get("installation_id")

    db = SyncDB()
    db.update_pr_status(record_id, "processing")

    try:
        result = _run_pipeline(payload)
        db.update_pr_status(record_id, "completed",
                            issues_found=result["issues_found"],
                            fixes_applied=result["fixes_applied"])
        logger.info("job_completed", record_id=record_id, **result)
    except Exception as e:
        logger.error("job_failed", record_id=record_id, error=str(e))
        db.update_pr_status(record_id, "failed")
        raise


def _run_pipeline(payload: dict) -> dict:
    repo_full_name = payload["repo_full_name"]
    pr_number = payload["pr_number"]
    record_id = payload["record_id"]

    # ── Step 1: Fetch PR diff ──────────────────────────────────────
    gh = GitHubClient()
    pr_files = gh.get_pr_files(repo_full_name, pr_number)

    # ── Step 2: Filter files ───────────────────────────────────────
    relevant_files = _filter_files(pr_files)
    if not relevant_files:
        logger.info("no_relevant_files", repo=repo_full_name, pr=pr_number)
        _post_skip_comment(gh, repo_full_name, pr_number)
        return {"issues_found": 0, "fixes_applied": 0}

    # Limit file count
    relevant_files = relevant_files[:settings.MAX_FILES_CHANGED]

    # ── Step 3: Parse diffs ────────────────────────────────────────
    parser = DiffParser()
    parsed_files = [parser.parse(f) for f in relevant_files]

    # ── Step 4: Update Neo4j graph ─────────────────────────────────
    neo4j = Neo4jClient()
    try:
        neo4j.update_graph(parsed_files)
        graph_scores = neo4j.compute_impact_scores([pf["path"] for pf in parsed_files])
    except Exception as e:
        logger.warning("neo4j_unavailable", error=str(e))
        graph_scores = {}
    finally:
        neo4j.close()

    # ── Step 5: Risk scoring ───────────────────────────────────────
    scorer = RiskScorer()
    scored_files = scorer.score(parsed_files, graph_scores)
    top_files = scored_files[:settings.MAX_FILES_CHANGED]

    # ── Step 6: Semgrep static analysis ───────────────────────────
    semgrep = SemgrepRunner()
    semgrep_issues = semgrep.analyze(top_files)

    if not semgrep_issues:
        _post_clean_comment(gh, repo_full_name, pr_number)
        return {"issues_found": 0, "fixes_applied": 0}

    # ── Step 7: LLM fix generation ─────────────────────────────────
    llm = LLMRouter()
    llm_results = []
    for issue in semgrep_issues[:settings.MAX_ISSUES_PER_PR]:
        fix = llm.generate_fix(issue)
        if fix:
            llm_results.append(fix)

    # ── Step 8: Sandbox validation ─────────────────────────────────
    sandbox = SandboxExecutor()
    validated_fixes = []
    for fix in llm_results:
        if fix.get("confidence", 0) < settings.MIN_CONFIDENCE:
            logger.info("low_confidence_skip", file=fix.get("file"), confidence=fix.get("confidence"))
            fix["fix_code"] = None  # explanation only
            validated_fixes.append(fix)
            continue

        passed = sandbox.validate(fix)
        if passed:
            validated_fixes.append(fix)
        else:
            fix["sandbox_failed"] = True
            fix["fix_code"] = None
            validated_fixes.append(fix)

    # ── Step 9: Apply fixes ────────────────────────────────────────
    fixes_applied = 0
    applied_fixes = []
    if settings.AUTO_CREATE_FIX_PRS:
        for fix in validated_fixes:
            if fix.get("fix_code") and not fix.get("sandbox_failed") and fixes_applied < settings.MAX_FIXES_PER_PR:
                success = gh.apply_fix(repo_full_name, pr_number, fix)
                if success:
                    fixes_applied += 1
                    applied_fixes.append(fix)
    else:
        logger.info("auto_fix_prs_disabled", repo=repo_full_name, pr=pr_number)

    # ── Step 10: Post PR comment ───────────────────────────────────
    builder = CommentBuilder()
    comment_body = builder.build(
        validated_fixes,
        applied_fixes=applied_fixes,
        files_analyzed=len(top_files),
        files_total=len(pr_files),
    )
    gh.post_or_update_comment(repo_full_name, pr_number, comment_body, record_id)

    # ── Step 11: Persist issues ────────────────────────────────────
    db = SyncDB()
    for fix in validated_fixes:
        db.insert_issue(
            pr_record_id=record_id,
            file_path=fix.get("file", ""),
            severity=fix.get("severity", "MEDIUM"),
            issue_type=fix.get("rule_id", "unknown"),
            description=fix.get("description", ""),
            confidence=fix.get("confidence", 0),
            fix_applied=fix in applied_fixes,
        )

    return {"issues_found": len(validated_fixes), "fixes_applied": fixes_applied}


def _filter_files(pr_files: list) -> list:
    result = []
    for f in pr_files:
        path = f.get("filename", "")
        ext = os.path.splitext(path)[1].lower()

        if any(path.startswith(p) or f"/{p}" in path for p in IGNORE_PATHS):
            continue
        if ext in IGNORE_EXTENSIONS:
            continue
        if ext not in ALLOWED_EXTENSIONS:
            continue
        result.append(f)
    return result


def _post_skip_comment(gh, repo, pr_number):
    body = "## 🔍 CodeWizard AI Review\n\n✅ No relevant files to analyze in this PR."
    gh.post_or_update_comment(repo, pr_number, body, None)


def _post_clean_comment(gh, repo, pr_number):
    body = "## 🔍 CodeWizard AI Review\n\n✅ No issues found — this PR looks clean!"
    gh.post_or_update_comment(repo, pr_number, body, None)
