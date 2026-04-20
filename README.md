# 🧙 CodeWizard AI

**AI-powered automated code review & fix system for GitHub pull requests.**

CodeWizard AI listens for GitHub PR events, runs a 12-stage analysis pipeline,
and automatically posts structured code review comments — complete with suggested
fixes validated in an isolated Docker sandbox.

---

## 🏗️ Architecture

```
GitHub PR Event
       │
       ▼
┌─────────────────┐     ┌───────────────┐
│  FastAPI Backend│────▶│  Redis + RQ   │
│  (Webhook Entry)│     │  (Task Queue) │
└─────────────────┘     └──────┬────────┘
                                │
                         ┌──────▼────────────────────────────────┐
                         │              RQ Worker                 │
                         │                                        │
                         │  1. Fetch PR diff (GitHub API)         │
                         │  2. Filter files (.py only)            │
                         │  3. Update Neo4j dependency graph      │
                         │  4. Compute graph impact scores        │
                         │  5. Risk-score & rank files            │
                         │  6. Semgrep static analysis            │
                         │  7. LLM fix generation (Gemini→Groq)  │
                         │  8. Docker sandbox validation          │
                         │  9. Post PR comment                    │
                         │  10. Create fix branch + PR            │
                         └───────────────────────────────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
         Neo4j DB           Qdrant DB          SQLite DB
      (Dep. Graph)      (Issue Vectors)     (PR Records)
```

---

## 📦 Services


| Service   | Port      | Description                         |
| --------- | --------- | ----------------------------------- |
| Backend   | 8000      | FastAPI webhook receiver + REST API |
| Dashboard | 3000      | Simple monitoring UI                |
| Redis     | 6379      | Task queue broker                   |
| Neo4j     | 7474/7687 | Code dependency graph               |
| Qdrant    | 6333      | Vector DB for issue similarity      |
| Worker    | —         | RQ job processor                    |
| Sandbox   | —         | Docker-isolated code validation     |


---

## 🚀 Quick Start

### 1. Prerequisites

- Docker + Docker Compose
- 8 GB RAM, 4 CPU cores
- ngrok (for local webhook testing)

### 2. Setup

```bash
git clone <your-repo>
cd codewizard-ai
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### 3. Configure `.env`

```bash
cp .env.example .env
# Fill in:
#   GITHUB_PAT          — Personal Access Token with repo + PR permissions
#   GEMINI_API_KEY      — Google AI Studio API key
#   GROQ_API_KEY        — Groq API key (fallback LLM)
#   GITHUB_WEBHOOK_SECRET — Any random string, must match GitHub App config
```

### 4. Expose webhook with ngrok

```bash
ngrok http 8000
# Copy the HTTPS URL → set as GitHub webhook:
# https://<ngrok-url>/webhook/github
# Content-Type: application/json
# Events: Pull requests
```

### 5. Test locally

```bash
./scripts/test_webhook.sh 1 your-org/your-repo
```

---

## 🔧 Pipeline Details

### Trigger Events

- `pull_request.opened`
- `pull_request.synchronize`

### File Filtering

**Allowed:** `.py`, `.js`, `.jsx`, `.ts`, `.tsx`

**Ignored paths:** `node_modules/`, `dist/`, `build/`, `venv/`, `.git/`, `migrations/`, etc.

**Ignored types:** `*.lock`, `*.min.js`, `*.png`, `*.zip`, `*.csv`, etc.

### Risk Score Formula

```
Risk Score = Change Size
           + Critical Path Score
           + Security Sensitivity
           + Graph Impact Score
```

### Severity Tiers


| Level    | Examples                                                |
| -------- | ------------------------------------------------------- |
| CRITICAL | SQL injection, RCE, hardcoded secrets, auth bypass      |
| HIGH     | Unhandled exceptions, insecure deps (Trivy), data leaks |
| MEDIUM   | Missing input validation, deprecated APIs, rate limits  |
| LOW      | Code style, unused imports, missing docstrings          |


### Fix Rules

- Minimum confidence: **75%**
- Max fixes per PR: **2**
- Skip risky fixes: **Yes**
- If confidence < 75%: explanation only, no auto-fix

### Sandbox Policy

- Timeout: **30 seconds**
- Retry attempts: **1**
- If tests fail: comment "Fix did not pass tests", no branch created

---

## 🕸️ Neo4j Graph Schema

```
Nodes:
  (:File  {path})
  (:Function {name, file_path})

Relationships:
  (File)-[:CONTAINS]->(Function)
  (Function)-[:CALLS]->(Function)
  (File)-[:IMPORTS]->(File)
```

Impact Score per file = `(incoming CALLS × 3) + (importers × 2) + degree`

---

## 📋 PR Comment Format

```markdown
## 🔍 CodeWizard AI Review

### 🧠 Analysis Scope
- Files analyzed: 3 / 12
- Strategy: Risk-based prioritization · Diff-aware slicing

---

### 🚨 Issue 1 (CRITICAL)
- File: `app/db.py`
- Problem: SQL injection via string formatting
- Rule: `python.lang.security.audit.formatted-sql-query`
- Confidence: 88%

### ✅ Suggested Fix
```diff
- cursor.execute("SELECT * FROM users WHERE id=%s" % uid)
+ cursor.execute("SELECT * FROM users WHERE id=%s", (uid,))
```

### 🧪 Validation

- Tests Passed: ✅
- Fix branch created and PR opened automatically

```

---

## 🛠️ Development

### Run tests
```bash
./scripts/run_tests.sh
# or: pytest tests/ -v
```

### View logs

```bash
docker compose logs -f worker    # Job processing
docker compose logs -f backend   # API + webhook events
docker compose logs -f neo4j     # Graph DB
```

### Stop all services

```bash
docker compose down
```

### Reset data

```bash
docker compose down -v   # ⚠️ Deletes all persistent volumes
```

---

## 📁 Project Structure

```
codewizard-ai/
├── backend/          # FastAPI app (webhook + REST API)
│   ├── routers/      # webhooks.py, prs.py, analytics.py
│   ├── services/     # rate_limiter.py
│   └── db/           # SQLAlchemy models + async DB
├── worker/           # RQ worker + job definitions
│   ├── jobs/         # analyze_pr.py (main pipeline)
│   └── utils/        # github_client.py, comment_builder.py
├── analyzer/         # Analysis modules
│   ├── diff_parser.py
│   ├── graph/        # neo4j_client.py
│   ├── static/       # semgrep_runner.py, trivy_scanner.py
│   └── scoring/      # risk_scorer.py
├── llm/              # LLM providers
│   ├── router.py     # Gemini → Groq fallback
│   ├── providers/    # gemini.py, groq.py
│   └── prompts/      # fix_prompt.py
├── sandbox/          # Docker-isolated validation
├── db/               # Shared DB helpers (sync_db.py, qdrant_store.py)
├── dashboard/        # Monitoring UI (HTML/CSS/JS + FastAPI server)
├── tests/            # Unit tests
├── scripts/          # setup.sh, run_tests.sh, test_webhook.sh
├── config.py         # Shared pydantic settings
├── docker-compose.yml
└── .env.example
```

---

## ⚙️ Configuration Reference


| Variable                | Default         | Description                     |
| ----------------------- | --------------- | ------------------------------- |
| `GITHUB_PAT`            | —               | GitHub Personal Access Token    |
| `GEMINI_API_KEY`        | —               | Google Gemini API key           |
| `GROQ_API_KEY`          | —               | Groq API key (LLaMA fallback)   |
| `GITHUB_WEBHOOK_SECRET` | `dev-secret`    | Webhook HMAC secret             |
| `MAX_PRS_PER_HOUR`      | `5`             | Rate limit per repo             |
| `MAX_ISSUES_PER_PR`     | `3`             | Max issues reported per PR      |
| `MAX_FIXES_PER_PR`      | `2`             | Max auto-fixes per PR           |
| `MIN_CONFIDENCE`        | `75`            | Min LLM confidence to apply fix |
| `SANDBOX_TIMEOUT`       | `30`            | Sandbox execution timeout (s)   |
| `NEO4J_PASSWORD`        | `codewizard123` | Neo4j auth password             |


---

## 🔒 Security Notes

- Webhook signatures are verified via HMAC-SHA256
- Sandbox runs in network-disabled, memory-limited Docker containers
- No code is stored beyond processing (cleared after job completes)
- API keys are loaded from environment — never hardcoded

---

## 📈 Scaling

- Swap SQLite → PostgreSQL by changing `DATABASE_URL` in config
- Add more RQ workers: `docker compose up -d --scale worker=3`
- Deploy behind nginx reverse proxy for production
- Set `ENVIRONMENT=production` to disable reload mode

