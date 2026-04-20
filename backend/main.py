"""
CodeWizard AI — FastAPI Backend
"""

import hashlib
import hmac
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from db.database import init_db
from routers import webhooks, prs, analytics
from services.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

rate_limiter = RateLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting CodeWizard AI backend...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down CodeWizard AI backend...")


app = FastAPI(
    title="CodeWizard AI",
    description="AI-powered automated code review & fix system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(webhooks.router, prefix="/webhook", tags=["webhooks"])
app.include_router(prs.router, prefix="/api/prs", tags=["pull-requests"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])


# ─── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "codewizard-backend", "version": "1.0.0"}


# ─── Webhook Signature Verification Middleware ─────────────────────────────────
@app.middleware("http")
async def verify_github_signature(request: Request, call_next):
    if request.url.path.startswith("/webhook"):
        body = await request.body()
        sig_header = request.headers.get("X-Hub-Signature-256")
        if not sig_header:
            logger.warning(
                "webhook_rejected_missing_signature",
                path=str(request.url.path),
                event=request.headers.get("X-GitHub-Event"),
                delivery=request.headers.get("X-GitHub-Delivery"),
            )
            return JSONResponse({"error": "Missing signature"}, status_code=401)
        if not sig_header.startswith("sha256="):
            logger.warning(
                "webhook_rejected_invalid_signature_format",
                path=str(request.url.path),
                signature=sig_header,
                event=request.headers.get("X-GitHub-Event"),
                delivery=request.headers.get("X-GitHub-Delivery"),
            )
            return JSONResponse({"error": "Invalid signature format"}, status_code=401)

        expected = "sha256=" + hmac.new(
            settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            logger.warning(
                "webhook_rejected_invalid_signature",
                path=str(request.url.path),
                event=request.headers.get("X-GitHub-Event"),
                delivery=request.headers.get("X-GitHub-Delivery"),
            )
            return JSONResponse({"error": "Invalid signature"}, status_code=401)

    return await call_next(request)
