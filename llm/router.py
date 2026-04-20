"""
LLMRouter — routes fix generation requests to Gemini 1.5 Flash,
falling back to Groq (LLaMA) on error/unavailability.
"""

import structlog
from llm.providers.gemini import GeminiProvider
from llm.providers.groq import GroqProvider

logger = structlog.get_logger(__name__)


class LLMRouter:
    def __init__(self):
        self._primary = GeminiProvider()
        self._fallback = GroqProvider()

    def generate_fix(self, issue: dict) -> dict | None:
        """
        Attempt fix generation via Gemini → fallback to Groq.
        Returns enriched issue dict with 'fix_code', or None on total failure.
        """
        try:
            result = self._primary.generate_fix(issue)
            if result:
                logger.info("llm_fix_generated", provider="gemini", file=issue.get("file"))
                return result
        except Exception as e:
            logger.warning("gemini_failed", error=str(e))

        try:
            result = self._fallback.generate_fix(issue)
            if result:
                logger.info("llm_fix_generated", provider="groq", file=issue.get("file"))
                return result
        except Exception as e:
            logger.warning("groq_failed", error=str(e))

        logger.error("all_llm_providers_failed", file=issue.get("file"))
        return None
