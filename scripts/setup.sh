#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# CodeWizard AI — Setup Script
# Run once to initialize environment, secrets, and services
# ─────────────────────────────────────────────────────────────────

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[CodeWizard]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "  🧙 CodeWizard AI — Setup"
echo "  ─────────────────────────────────"
echo ""

# ── 1. Prerequisites ─────────────────────────────────────────────
log "Checking prerequisites..."
command -v docker >/dev/null || err "Docker is required. Install from https://docs.docker.com/get-docker/"
command -v docker-compose >/dev/null 2>&1 || command -v docker compose >/dev/null || err "Docker Compose is required."
log "✓ Docker found: $(docker --version)"

# ── 2. .env file ─────────────────────────────────────────────────
if [ ! -f .env ]; then
  log "Creating .env from template..."
  cp .env.example .env
  warn "⚠️  Edit .env and fill in your API keys before proceeding!"
  warn "   Required: GITHUB_PAT (or App credentials), GEMINI_API_KEY, GROQ_API_KEY"
else
  log "✓ .env already exists"
fi

# ── 3. Secrets directory ─────────────────────────────────────────
mkdir -p secrets
if [ ! -f secrets/github-app.pem ]; then
  warn "secrets/github-app.pem not found."
  warn "If using GitHub App auth, place your private key at secrets/github-app.pem"
  echo "# placeholder" > secrets/github-app.pem
fi

# ── 4. Data directory ────────────────────────────────────────────
mkdir -p data
log "✓ Data directory ready"

# ── 5. Build images ──────────────────────────────────────────────
log "Building Docker images (this may take a few minutes)..."
docker compose build --parallel

# ── 6. Start services ────────────────────────────────────────────
log "Starting services..."
docker compose up -d redis neo4j qdrant

log "Waiting for Neo4j to be ready..."
timeout=60
elapsed=0
until docker compose exec neo4j neo4j status >/dev/null 2>&1 || [ $elapsed -ge $timeout ]; do
  sleep 3
  elapsed=$((elapsed + 3))
  echo -n "."
done
echo ""

if [ $elapsed -ge $timeout ]; then
  warn "Neo4j did not start within ${timeout}s. Check: docker compose logs neo4j"
else
  log "✓ Neo4j ready"
fi

# ── 7. Start all services ────────────────────────────────────────
log "Starting all CodeWizard services..."
docker compose up -d

sleep 3

# ── 8. Health check ──────────────────────────────────────────────
log "Running health check..."
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
  log "✓ Backend API: http://localhost:8000"
else
  warn "Backend not yet ready. Check: docker compose logs backend"
fi

echo ""
echo "  ─────────────────────────────────────────────────────────"
echo "  🧙 CodeWizard AI is running!"
echo ""
echo "  Dashboard:   http://localhost:3000"
echo "  Backend API: http://localhost:8000"
echo "  API Docs:    http://localhost:8000/docs"
echo "  Neo4j UI:    http://localhost:7474  (neo4j / codewizard123)"
echo "  Qdrant UI:   http://localhost:6333/dashboard"
echo ""
echo "  To expose webhook for testing:"
echo "  → ngrok http 8000"
echo "  → Set webhook URL: https://<ngrok-url>/webhook/github"
echo ""
echo "  Useful commands:"
echo "  → docker compose logs -f worker    # Watch job processing"
echo "  → docker compose logs -f backend   # Watch API logs"
echo "  → docker compose down              # Stop all services"
echo "  → ./scripts/run_tests.sh           # Run unit tests"
echo "  ─────────────────────────────────────────────────────────"
echo ""
