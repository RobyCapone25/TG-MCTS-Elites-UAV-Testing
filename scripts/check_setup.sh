#!/usr/bin/env bash

# Verify the host environment without launching a PX4 simulation.

set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

FAILURES=0

pass() {
    printf '[OK]   %s\n' "$1"
}

fail() {
    printf '[FAIL] %s\n' "$1"
    FAILURES=$((FAILURES + 1))
}

note() {
    printf '[INFO] %s\n' "$1"
}

echo "============================================================"
echo "TG-MCTS-Elites setup verification"
echo "Repository: $PROJECT_ROOT"
echo "============================================================"

# ------------------------------------------------------------
# Operating system
# ------------------------------------------------------------

if [[ "$(uname -s)" == "Linux" ]]; then
    pass "Linux operating system detected"
else
    fail "This project is primarily supported on Linux"
fi

if command -v lsb_release >/dev/null 2>&1; then
    note "Distribution: $(lsb_release -ds 2>/dev/null || true)"
fi

# ------------------------------------------------------------
# Conda environment
# ------------------------------------------------------------

if [[ "${CONDA_DEFAULT_ENV:-}" == "uav" ]]; then
    pass "Conda environment 'uav' is active"
else
    fail "Activate the environment first: conda activate uav"
fi

# ------------------------------------------------------------
# Python
# ------------------------------------------------------------

if command -v python >/dev/null 2>&1; then
    pass "Python executable found: $(command -v python)"

    PYTHON_VERSION="$(
        python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
    )"

    if [[ "$PYTHON_VERSION" == "3.10" ]]; then
        pass "Python 3.10 detected"
    else
        fail "Python 3.10 required; detected Python $PYTHON_VERSION"
    fi
else
    fail "Python was not found"
fi

# ------------------------------------------------------------
# Python packages
# ------------------------------------------------------------

if python - <<'PY'
import importlib

modules = {
    "aerialist": "Aerialist",
    "decouple": "python-decouple",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pandas": "pandas",
    "yaml": "PyYAML",
    "munch": "munch",
    "pyparsing": "pyparsing",
}

missing = []

for module_name, package_name in modules.items():
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        missing.append(f"{package_name}: {type(exc).__name__}: {exc}")

if missing:
    print("Missing or broken Python packages:")
    for item in missing:
        print(f"  - {item}")
    raise SystemExit(1)

print("All required Python packages can be imported.")
PY
then
    pass "Required Python packages are available"
else
    fail "Python dependencies are incomplete"
fi

# ------------------------------------------------------------
# Docker
# ------------------------------------------------------------

if command -v docker >/dev/null 2>&1; then
    pass "Docker executable found"

    if docker info >/dev/null 2>&1; then
        pass "Docker can be used without sudo"
    else
        fail "Docker is unavailable or requires sudo"
    fi

    if docker image inspect skhatiri/aerialist:2.0 >/dev/null 2>&1; then
        pass "Docker image skhatiri/aerialist:2.0 is installed"
    else
        fail "Pull the required image: docker pull skhatiri/aerialist:2.0"
    fi
else
    fail "Docker was not found"
fi

# ------------------------------------------------------------
# Runtime configuration
# ------------------------------------------------------------

if [[ -f .env ]]; then
    pass ".env file exists"

    grep -qxF 'AGENT=docker' .env \
        && pass ".env uses AGENT=docker" \
        || fail ".env should contain AGENT=docker"

    grep -qxF 'DOCKER_IMG=skhatiri/aerialist:2.0' .env \
        && pass ".env uses skhatiri/aerialist:2.0" \
        || fail ".env should contain DOCKER_IMG=skhatiri/aerialist:2.0"

    grep -qxF 'SIMULATOR=ros' .env \
        && pass ".env uses SIMULATOR=ros" \
        || fail ".env should contain SIMULATOR=ros"

    grep -qxF 'ROBOT=px4_ros' .env \
        && pass ".env uses ROBOT=px4_ros" \
        || fail ".env should contain ROBOT=px4_ros"
else
    fail ".env is missing; create it with: cp .env.example .env"
fi

# ------------------------------------------------------------
# Required project files
# ------------------------------------------------------------

REQUIRED_FILES=(
    "cli.py"
    "src/__init__.py"
    "src/cli.py"
    "src/random_generator.py"
    "src/testcase.py"
    "case_studies/mission1.yaml"
    "case_studies/mission2.yaml"
    "case_studies/mission3.yaml"
    "case_studies/mission1.plan"
    "case_studies/mission2.plan"
    "case_studies/mission3.plan"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$file" ]]; then
        pass "Found $file"
    else
        fail "Missing $file"
    fi
done

# ------------------------------------------------------------
# Syntax checks
# ------------------------------------------------------------

if python -m py_compile \
    cli.py \
    src/cli.py \
    src/random_generator.py \
    src/testcase.py
then
    pass "Python syntax checks passed"
else
    fail "Python syntax checks failed"
fi

if bash -n scripts/run_all_100.sh scripts/check_setup.sh; then
    pass "Shell syntax checks passed"
else
    fail "Shell syntax checks failed"
fi

# ------------------------------------------------------------
# Result
# ------------------------------------------------------------

echo "============================================================"

if [[ "$FAILURES" -eq 0 ]]; then
    echo "SETUP CHECK PASSED"
    echo
    echo "Quick test:"
    echo "  TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 1"
    exit 0
fi

echo "SETUP CHECK FAILED: $FAILURES problem(s) found"
echo
echo "Review docs/SETUP.md and correct the failed checks."
exit 1
