"""
Gemini 1.5 Flash provider via REST API.
"""

import json
import httpx
import structlog
from config import settings
from llm.prompts.fix_prompt import FIX_SYSTEM_PROMPT, FIX_USER_PROMPT

logger = structlog.get_logger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


class GeminiProvider:
    def generate_fix(self, issue: dict) -> dict | None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not configured")

        user_msg = FIX_USER_PROMPT.format(
            file_path=issue.get("file", "unknown"),
            severity=issue.get("severity", "MEDIUM"),
            rule_id=issue.get("rule_id", ""),
            description=issue.get("description", ""),
            content_slice=issue.get("content_slice", "")[:1500],
            patch=issue.get("patch", "")[:500],
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": FIX_SYSTEM_PROMPT + "\n\n" + user_msg}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
            },
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                GEMINI_API_URL,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        return self._parse_response(text, issue)

    def _parse_response(self, text: str, issue: dict) -> dict | None:
        try:
            # Strip markdown fences if present
            clean = text.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = "\n".join(clean.split("\n")[:-1])
            parsed = json.loads(clean)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("gemini_parse_error", error=str(e), raw=text[:200])
            return None

        return {
            **issue,
            "fix_code": parsed.get("fix_code"),
            "description": parsed.get("description", issue.get("description", "")),
            "confidence": int(parsed.get("confidence", 0)),
            "breaking_change": parsed.get("breaking_change", False),
        }
