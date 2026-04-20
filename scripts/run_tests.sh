#!/bin/bash
# Run CodeWizard AI unit tests

set -e
cd "$(dirname "$0")/.."

echo "🧪 Running CodeWizard AI tests..."
echo ""

pip install pytest --quiet

pytest tests/ -v --tb=short "$@"

echo ""
echo "✅ All tests passed!"
