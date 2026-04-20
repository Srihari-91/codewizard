"""
QdrantStore — stores code embeddings for semantic similarity search.
Used to find related historical issues across PRs.

NOTE: Embedding generation uses a simple hash-based placeholder.
      Swap in a real embedding model (e.g. sentence-transformers) for production.
"""

import hashlib
import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)
from config import settings

logger = structlog.get_logger(__name__)

COLLECTION = "codewizard_issues"
VECTOR_SIZE = 128  # Placeholder dim; replace with actual embedding size


class QdrantStore:
    def __init__(self):
        try:
            self._client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
            self._ensure_collection()
        except Exception as e:
            logger.warning("qdrant_unavailable", error=str(e))
            self._client = None

    def _ensure_collection(self):
        collections = [c.name for c in self._client.get_collections().collections]
        if COLLECTION not in collections:
            self._client.create_collection(
                COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    def store_issue(self, issue_id: int, issue: dict):
        """Store an issue embedding for future similarity lookups."""
        if not self._client:
            return
        try:
            vec = self._embed(issue.get("description", "") + " " + issue.get("file", ""))
            self._client.upsert(COLLECTION, points=[
                PointStruct(
                    id=issue_id,
                    vector=vec,
                    payload={
                        "file": issue.get("file", ""),
                        "severity": issue.get("severity", ""),
                        "rule_id": issue.get("rule_id", ""),
                        "description": issue.get("description", ""),
                    },
                )
            ])
        except Exception as e:
            logger.warning("qdrant_store_error", error=str(e))

    def find_similar(self, description: str, top_k: int = 3) -> list[dict]:
        """Find historically similar issues."""
        if not self._client:
            return []
        try:
            vec = self._embed(description)
            results = self._client.search(COLLECTION, query_vector=vec, limit=top_k)
            return [{"score": r.score, **r.payload} for r in results]
        except Exception as e:
            logger.warning("qdrant_search_error", error=str(e))
            return []

    @staticmethod
    def _embed(text: str) -> list[float]:
        """
        Deterministic placeholder embedding via SHA-256 hash.
        Replace with a real embedding model for semantic accuracy.
        """
        digest = hashlib.sha256(text.encode()).digest()
        # Expand 32 bytes to VECTOR_SIZE floats in [0, 1]
        base = [b / 255.0 for b in digest]
        # Tile to fill VECTOR_SIZE
        result = (base * ((VECTOR_SIZE // len(base)) + 1))[:VECTOR_SIZE]
        return result
