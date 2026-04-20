#!/bin/bash
# Simulate a GitHub pull_request webhook event for local testing
# Usage: ./scripts/test_webhook.sh [pr_number]

set -e

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
PR_NUMBER="${1:-1}"
REPO="${2:-your-org/your-repo}"
SECRET="${GITHUB_WEBHOOK_SECRET:-dev-secret}"

PAYLOAD=$(cat <<EOF
{
  "action": "opened",
  "number": ${PR_NUMBER},
  "pull_request": {
    "number": ${PR_NUMBER},
    "title": "Test PR: Fix SQL injection in user query",
    "head": {
      "ref": "feature/test-branch",
      "sha": "abc123def456"
    },
    "base": {
      "ref": "main",
      "sha": "000111222333"
    }
  },
  "repository": {
    "full_name": "${REPO}",
    "name": "your-repo"
  },
  "installation": {
    "id": 12345
  }
}
EOF
)

# Compute HMAC-SHA256 signature
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/.*= //')

echo "🧪 Sending test webhook to ${BACKEND_URL}..."
echo ""

curl -s -X POST "${BACKEND_URL}/webhook/github" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=${SIG}" \
  -d "$PAYLOAD" | python3 -m json.tool

echo ""
echo "✅ Webhook sent. Check worker logs: docker compose logs -f worker"
