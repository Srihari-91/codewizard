"""
Groq provider (LLaMA 3) — fallback LLM.
"""

import json
import httpx
import structlog
from config import settings
from llm.prompts.fix_prompt import FIX_SYSTEM_PROMPT, FIX_USER_PROMPT

logger = structlog.get_logger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"


class GroqProvider:
    def generate_fix(self, issue: dict) -> dict | None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured")

        user_msg = FIX_USER_PROMPT.format(
            file_path=issue.get("file", "unknown"),
            severity=issue.get("severity", "MEDIUM"),
            rule_id=issue.get("rule_id", ""),
            description=issue.get("description", ""),
            content_slice=issue.get("content_slice", "")[:1500],
            patch=issue.get("patch", "")[:500],
        )

        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": FIX_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        return self._parse_response(text, issue)

    def _parse_response(self, text: str, issue: dict) -> dict | None:
        try:
            clean = text.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = "\n".join(clean.split("\n")[:-1])
            parsed = json.loads(clean)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("groq_parse_error", error=str(e), raw=text[:200])
            return None

        return {
            **issue,
            "fix_code": parsed.get("fix_code"),
            "description": parsed.get("description", issue.get("description", "")),
            "confidence": int(parsed.get("confidence", 0)),
            "breaking_change": parsed.get("breaking_change", False),
        }
