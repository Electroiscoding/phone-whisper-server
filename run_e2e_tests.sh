#!/usr/bin/env bash
# ==============================================================================
# Cloud Phone NTA E2E Test Suite Runner
# Usage:
#   ./run_e2e_tests.sh                 # Run all tiers (Tier 1 to 4)
#   ./run_e2e_tests.sh --tier 1        # Run Tier 1 Feature Coverage (50 tests)
#   ./run_e2e_tests.sh --tier 2        # Run Tier 2 Boundary / Corner Cases (25 tests)
#   ./run_e2e_tests.sh --tier 3        # Run Tier 3 Pairwise Combinations (7 tests)
#   ./run_e2e_tests.sh --tier 4        # Run Tier 4 Real-World Workflows (6 tests)
#   ./run_e2e_tests.sh -m hardware     # Run hardware-specific tests
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Detect Python interpreter
if [[ -f "/home/soham/.global_venv/bin/python3" ]]; then
    PYTHON_EXEC="/home/soham/.global_venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="$(command -v python3)"
else
    echo "ERROR: python3 interpreter not found!" >&2
    exit 1
fi

# 2. Check for required dependencies
if ! "$PYTHON_EXEC" -c "import pytest, requests, PIL" &>/dev/null; then
    echo "ERROR: Required test dependencies missing in $PYTHON_EXEC. Please ensure pytest, requests, and pillow are installed." >&2
    exit 1
fi

# 3. Environment Variable Defaults
export GATEWAY_URL="${GATEWAY_URL:-http://192.168.29.2:8080}"
export PAGES_URL="${PAGES_URL:-https://phone-whisper-server.pages.dev}"
export ADB_DEVICE="${ADB_DEVICE:-192.168.29.2:5555}"
export APK_PATH="${APK_PATH:-/tmp/nta-4.18-release.apk}"
export GATEWAY_TIMEOUT="${GATEWAY_TIMEOUT:-10.0}"
export PAGES_TIMEOUT="${PAGES_TIMEOUT:-25.0}"
export AI_TIMEOUT="${AI_TIMEOUT:-45.0}"

echo "========================================================================"
echo " Starting Cloud Phone NTA E2E Verification Suite"
echo " Python    : $("$PYTHON_EXEC" --version)"
echo " Gateway   : $GATEWAY_URL"
echo " Pages Edge: $PAGES_URL"
echo " ADB Device: $ADB_DEVICE"
echo "========================================================================"

# 4. Execute runner script
if [[ -f "$SCRIPT_DIR/tests/e2e/runner.py" ]]; then
    exec "$PYTHON_EXEC" "$SCRIPT_DIR/tests/e2e/runner.py" "$@"
else
    # Fallback directly to pytest targeting tests/e2e
    exec "$PYTHON_EXEC" -m pytest "$SCRIPT_DIR/tests/e2e" -v --tb=short "$@"
fi
