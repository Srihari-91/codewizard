"""
Shared config — loaded by worker, analyzer, llm, sandbox.
Re-exports from backend config if running co-located, else standalone.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GITHUB_APP_ID: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_WEBHOOK_SECRET: str = "dev-secret"
    GITHUB_PAT: str = ""
    GITHUB_APP_PRIVATE_KEY_PATH: str = "/secrets/github-app.pem"

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    REDIS_URL: str = "redis://localhost:6379"
    REDIS_PASSWORD: str = ""

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "codewizard123"

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    SQLITE_DB_PATH: str = "/data/codewizard.db"
    MAX_PRS_PER_HOUR: int = 5
    MAX_ISSUES_PER_PR: int = 3
    MAX_FILES_CHANGED: int = 20
    MAX_LINES_ANALYZED: int = 2000
    MIN_CONFIDENCE: int = 75
    MAX_FIXES_PER_PR: int = 2
    AUTO_CREATE_FIX_PRS: bool = False
    SANDBOX_TIMEOUT: int = 30
    SANDBOX_RETRY_ATTEMPTS: int = 1

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
