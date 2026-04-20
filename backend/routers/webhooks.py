"""
GitHub Webhook Router — handles pull_request.opened / synchronize events.
"""
import structlog
from json import JSONDecodeError
from fastapi import APIRouter, Request, HTTPException
from redis import Redis
from rq import Queue, Retry

from config import settings
from services.rate_limiter import RateLimiter
from db.database import AsyncSessionLocal, PRRecord

logger = structlog.get_logger(__name__)
router = APIRouter()

_redis = Redis.from_url(settings.REDIS_URL)
_queue = Queue("codewizard", connection=_redis)
_rate_limiter = RateLimiter()

ALLOWED_ACTIONS = {"opened", "synchronize"}

IGNORE_PATHS = {
    "node_modules/", "dist/", "build/", "out/", "coverage/",
    ".mypy_cache/", ".pytest_cache/", "__pycache__/", ".next/",
    ".nuxt/", "target/", "venv/", ".env/", ".idea/", ".vscode/",
    ".git/", ".github/", "migrations/", "logs/", "tmp/", "temp/", ".cache/"
}

ALLOWED_EXTENSIONS = {".py"}


@router.post("/github")
async def github_webhook(request: Request):
    """Entry point for all GitHub webhook events."""
    delivery = request.headers.get("X-GitHub-Delivery")
    if not delivery:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Delivery")

    # Best-effort dedupe to prevent replay/retry storms (1 hour TTL)
    if not _redis.set(f"github_delivery:{delivery}", "1", nx=True, ex=3600):
        return {"status": "ignored", "reason": "duplicate delivery"}

    event = request.headers.get("X-GitHub-Event", "")
    try:
        payload = await request.json()
    except JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if event != "pull_request":
        return {"status": "ignored", "reason": f"event={event}"}

    action = payload.get("action", "")
    if action not in ALLOWED_ACTIONS:
        return {"status": "ignored", "reason": f"action={action}"}

    try:
        pr = payload["pull_request"]
        repo = payload["repository"]
        repo_name = repo["full_name"]
        pr_number = pr["number"]
        pr_title = pr.get("title", "")
        base_sha = pr["base"]["sha"]
        head_sha = pr["head"]["sha"]
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e.args[0]}")

    logger.info(
        "webhook_received",
        delivery=delivery,
        github_event=event,
        action=action,
        repo=repo_name,
        pr=pr_number,
    )

    # Rate limiting
    allowed, reason = await _rate_limiter.check(repo_name)
    if not allowed:
        logger.warning("rate_limited", repo=repo_name, reason=reason)
        return {"status": "rate_limited", "reason": reason}

    # GitHub's pull_request webhook payload does NOT include the full file list.
    # The worker is the source of truth and will fetch PR files via GitHub API.
    logger.info("enqueuing_pr", repo=repo_name, pr=pr_number)

    # Persist PR record
    async with AsyncSessionLocal() as session:
        record = PRRecord(
            repo_full_name=repo_name,
            pr_number=pr_number,
            pr_title=pr_title,
            status="queued",
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        record_id = record.id

    # Enqueue job
    job_payload = {
        "record_id": record_id,
        "repo_full_name": repo_name,
        "pr_number": pr_number,
        "pr_title": pr_title,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "installation_id": payload.get("installation", {}).get("id"),
    }
    # RQ's `enqueue()` expects a callable; for import-path strings use `enqueue_call`.
    job = _queue.enqueue_call(
        func="jobs.analyze_pr.run",
        args=(job_payload,),
        timeout=300,
        retry=Retry(max=1),
    )
    logger.info("enqueued", job_id=getattr(job, "id", None), repo=repo_name, pr=pr_number)

    return {"status": "queued", "pr": pr_number, "job_id": getattr(job, "id", None)}

