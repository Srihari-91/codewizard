"""
CodeWizard AI — RQ Worker entry point.
"""

import os
import sys
import structlog
from redis import Redis
from rq import Worker, Queue

# Ensure project root is importable
sys.path.insert(0, "/app")
# Ensure `jobs.*` is importable for RQ string callables
sys.path.insert(0, "/app/worker")

from config import settings

logger = structlog.get_logger(__name__)


def main():
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

    redis_conn = Redis.from_url(settings.REDIS_URL)
    queues = [Queue("codewizard", connection=redis_conn)]

    logger.info("worker_starting", queues=["codewizard"])
    worker = Worker(queues, connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
