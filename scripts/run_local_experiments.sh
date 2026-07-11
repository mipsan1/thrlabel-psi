#!/usr/bin/env bash
# run_local_experiments.sh
# -----------------------------------------------------------------------------
# Regenerate the Python simulation tables/figures and run the test suite, and
# collect all artifacts + logs under a single timestamped result folder.
#
# This runs ONLY the local Python artifact (numpy/matplotlib). It does NOT build
# or run any cryptographic code. All numbers produced are release-layer
# SIMULATION or ANALYTICAL cost-model results (see REPRODUCIBILITY.md).
#
# SAFETY: no sudo, no system package installs, no destructive commands. Writes
# only under the chosen output dir.
# -----------------------------------------------------------------------------
set -u
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUTPUT_ROOT=""
RESULT_DIR=""      # if set, attach to an existing result folder (e.g. a mac_feasibility_*)
PY="${PYTHON:-python3}"
REPS="10"
NUM_SEEDS="10"
RUN_TESTS=1

usage() {
  cat <<'EOF'
Usage: scripts/run_local_experiments.sh [options]

  --output-dir DIR    Base dir for outputs (default ./outputs or $THRLABEL_OUTPUT_DIR).
  --result-dir DIR    Attach artifacts to an EXISTING result folder instead of
                      creating a new local_run_<ts> (e.g. a mac_feasibility_<ts>).
  --reps N            Seeds averaged in experiments.py (default 10).
  --num-seeds N       Seeds in sim.py / sim_thrlabel.py (default 10).
  --no-tests          Skip the pytest suite.
  --python BIN        Python interpreter to use (default python3 / $PYTHON).
  -h, --help          Show this help.

First run on the user's Mac:
  bash scripts/run_local_experiments.sh
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --output-dir) OUTPUT_ROOT="${2:-}"; shift ;;
    --result-dir) RESULT_DIR="${2:-}"; shift ;;
    --reps)       REPS="${2:-}"; shift ;;
    --num-seeds)  NUM_SEEDS="${2:-}"; shift ;;
    --no-tests)   RUN_TESTS=0 ;;
    --python)     PY="${2:-}"; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

TS="$(date +%Y%m%d_%H%M%S)"
if [ -z "${OUTPUT_ROOT}" ]; then
  OUTPUT_ROOT="${THRLABEL_OUTPUT_DIR:-${REPO_ROOT}/outputs}"
fi
if [ -z "${RESULT_DIR}" ]; then
  RESULT_DIR="${OUTPUT_ROOT}/local_run_${TS}"
fi
ART_DIR="${RESULT_DIR}/experiment_artifacts"
LOG_DIR="${RESULT_DIR}/logs"
mkdir -p "${ART_DIR}" "${LOG_DIR}"

have() { command -v "$1" >/dev/null 2>&1; }

echo "Python: $(${PY} --version 2>&1)"
if ! ${PY} -c "import numpy, matplotlib" >/dev/null 2>&1; then
  echo "ERROR: numpy/matplotlib not importable by '${PY}'."
  echo "Install with:  ${PY} -m pip install -r ${REPO_ROOT}/requirements.txt"
  exit 1
fi

STATUS_FILE="$(mktemp)"; : > "${STATUS_FILE}"
step() {
  # step <name> <logfile> <cmd...>
  local name="$1" logf="$2"; shift 2
  echo "==> ${name}"
  ( cd "${REPO_ROOT}" && "$@" ) >"${logf}" 2>&1
  local rc=$?
  if [ ${rc} -eq 0 ]; then echo "PASS ${name}" >> "${STATUS_FILE}"; else echo "FAIL ${name} (rc=${rc})" >> "${STATUS_FILE}"; fi
  return ${rc}
}

# 1. simulations -> write straight into the artifact dir
step "sim"          "${LOG_DIR}/sim.log"          "${PY}" sim.py          --output-dir "${ART_DIR}" --num-seeds "${NUM_SEEDS}"
step "sim_thrlabel" "${LOG_DIR}/sim_thrlabel.log" "${PY}" sim_thrlabel.py --output-dir "${ART_DIR}" --num-seeds "${NUM_SEEDS}"
step "experiments"  "${LOG_DIR}/experiments.log"  "${PY}" experiments.py  --output-dir "${ART_DIR}" --reps "${REPS}"
step "make_figures" "${LOG_DIR}/make_figures.log" "${PY}" make_figures.py --output-dir "${ART_DIR}"
step "figs"         "${LOG_DIR}/figs.log"         "${PY}" figs.py          --output-dir "${ART_DIR}"

# 2. tests (optional)
if [ "${RUN_TESTS}" -eq 1 ]; then
  if ${PY} -c "import pytest" >/dev/null 2>&1; then
    step "pytest" "${LOG_DIR}/pytest.log" "${PY}" -m pytest -q
  elif have pytest; then
    step "pytest" "${LOG_DIR}/pytest.log" pytest -q
  else
    echo "SKIP pytest (not installed; ${PY} -m pip install -r requirements-dev.txt)" >> "${STATUS_FILE}"
    echo "==> pytest SKIPPED (not installed)"
  fi
fi

# 3. summary
SUMMARY_MD="${RESULT_DIR}/local_experiments_summary.md"
{
  echo "# Local experiment run ${TS}"
  echo
  echo "Python: $(${PY} --version 2>&1)"
  echo "Artifacts: ${ART_DIR}"
  echo
  echo "## Steps"
  echo '```'
  cat "${STATUS_FILE}"
  echo '```'
  echo
  echo "## Provenance reminder"
  echo "- RQ3/RQ4 and the fraud-ring tables are SIMULATION results."
  echo "- RQ1 communication is an ANALYTICAL cost-model estimate."
  echo "- No cryptographic wall-clock timing is produced by these steps."
  echo
  echo "## Key artifacts"
  ls -1 "${ART_DIR}" 2>/dev/null | sed 's/^/- /'
} > "${SUMMARY_MD}"

cat "${STATUS_FILE}"
rm -f "${STATUS_FILE}"

# 4. tarball
if have tar; then
  base="$(basename "${RESULT_DIR}")"
  ( cd "$(dirname "${RESULT_DIR}")" && tar -czf "${base}.tar.gz" "${base}" ) \
    && echo "Archive: ${RESULT_DIR}.tar.gz" || echo "tar failed (non-fatal)"
fi

echo
echo "Done. Results in: ${RESULT_DIR}"
echo "Summary:         ${SUMMARY_MD}"
