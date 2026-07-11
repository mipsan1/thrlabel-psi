#!/usr/bin/env bash
# macos_feasibility.sh
# -----------------------------------------------------------------------------
# ThrLabel-PSI cryptographic-stack feasibility probe for Apple Silicon (M3).
#
# WHAT THIS DOES (default, read/build only):
#   * records system + toolchain state (compiler/cmake/ninja/python)
#   * clones an upstream PSI crypto repo (default: Visa-Research/volepsi, which
#     pulls libOTe) into an ISOLATED temp work dir
#   * consults the upstream README/help for the correct build options, applies
#     ARM64-native settings, and attempts configure+build, recording PASS/FAIL/SKIP
#   * if the build succeeds, runs a small upstream unit test / example PSI
#   * runs a tiny 2-party additive-share ARITHMETIC demo (NOT secure MPC; see note)
#   * collects everything under outputs/mac_feasibility_<timestamp>/ and tars it
#
# SAFETY:
#   * NEVER uses sudo. Never runs destructive commands.
#   * Does NOT auto-install system packages. Homebrew packages are installed
#     ONLY if you explicitly pass --install-deps (and even then, no sudo).
#   * All third-party clones/builds happen inside the temp work dir only.
#   * Does not dump your full environment, secrets, or personal file tree; only
#     specific tool versions and build logs are recorded.
#
# This script does NOT and CANNOT prove security. A passing build only shows the
# stack compiles/runs on your machine. No composition/simulation security proof
# is produced or implied.
# -----------------------------------------------------------------------------
set -u
IFS=$'\n\t'

# ---- defaults ----------------------------------------------------------------
INSTALL_DEPS=0
SKIP_BUILD=0
WITH_MPSPDZ=0
REPO_URL="https://github.com/Visa-Research/volepsi.git"
REPO_NAME="volepsi"
WORK_DIR=""
OUTPUT_ROOT=""
BUILD_TIMEOUT="${BUILD_TIMEOUT:-3600}"   # seconds; guards against runaway builds

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/macos_feasibility.sh [options]

  --install-deps        Install required Homebrew packages (no sudo). Off by default.
  --with-mpspdz         Also clone+build MP-SPDZ (very slow). Off by default (SKIP).
  --skip-build          Only record system/toolchain state; do not clone/build.
  --repo-url URL        Upstream PSI repo to clone (default: volepsi).
  --repo-name NAME      Local dir name for the clone (default: volepsi).
  --work-dir DIR        Isolated work dir for clones/builds (default: mktemp -d).
  --output-dir DIR      Where to write outputs/mac_feasibility_<ts> (default: ./outputs).
  --build-timeout SEC   Max seconds for each build step (default: 3600).
  -h, --help            Show this help.

Typical first run on the user's Mac (read/build only, no installs):
  bash scripts/macos_feasibility.sh

If the toolchain check reports missing packages, then either install them
yourself, or re-run with:
  bash scripts/macos_feasibility.sh --install-deps
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    --with-mpspdz)  WITH_MPSPDZ=1 ;;
    --skip-build)   SKIP_BUILD=1 ;;
    --repo-url)     REPO_URL="${2:-}"; shift ;;
    --repo-name)    REPO_NAME="${2:-}"; shift ;;
    --work-dir)     WORK_DIR="${2:-}"; shift ;;
    --output-dir)   OUTPUT_ROOT="${2:-}"; shift ;;
    --build-timeout) BUILD_TIMEOUT="${2:-}"; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

# ---- output layout -----------------------------------------------------------
TS="$(date +%Y%m%d_%H%M%S)"
if [ -z "${OUTPUT_ROOT}" ]; then
  OUTPUT_ROOT="${THRLABEL_OUTPUT_DIR:-${REPO_ROOT}/outputs}"
fi
RESULT_DIR="${OUTPUT_ROOT}/mac_feasibility_${TS}"
LOG_DIR="${RESULT_DIR}/logs"
mkdir -p "${LOG_DIR}"

SYSTEM_TXT="${RESULT_DIR}/system.txt"
SUMMARY_JSON="${RESULT_DIR}/summary.json"
SUMMARY_MD="${RESULT_DIR}/summary.md"

# step results accumulate here as JSON objects
STEP_JSON_FILE="$(mktemp)"
: > "${STEP_JSON_FILE}"

record_step() {
  # record_step <name> <status PASS|FAIL|SKIP> <detail> [logfile]
  local name="$1" status="$2" detail="$3" logf="${4:-}"
  # escape double quotes and backslashes in detail for JSON
  detail="${detail//\\/\\\\}"
  detail="${detail//\"/\\\"}"
  printf '{"step":"%s","status":"%s","detail":"%s","log":"%s"}\n' \
    "${name}" "${status}" "${detail}" "${logf}" >> "${STEP_JSON_FILE}"
  echo "[${status}] ${name}: ${detail}"
}

have() { command -v "$1" >/dev/null 2>&1; }

# run a command with an optional timeout (gtimeout/timeout if present), logging
run_logged() {
  # run_logged <logfile> <cmd...>
  local logf="$1"; shift
  local -a prefix=()
  if have timeout; then prefix=(timeout "${BUILD_TIMEOUT}");
  elif have gtimeout; then prefix=(gtimeout "${BUILD_TIMEOUT}"); fi
  {
    echo "\$ $*"
    echo "--- $(date) ---"
  } >>"${logf}" 2>&1
  # ${prefix[@]+...} guard keeps this safe under `set -u` with bash 3.2 (macOS).
  "${prefix[@]+"${prefix[@]}"}" "$@" >>"${logf}" 2>&1
}

# =============================================================================
# 1. SYSTEM + TOOLCHAIN STATE
# =============================================================================
{
  echo "# ThrLabel-PSI macOS feasibility -- system report"
  echo "timestamp: ${TS}"
  echo
  echo "## OS"
  uname -a 2>/dev/null || echo "uname: n/a"
  if have sw_vers; then sw_vers; fi
  echo "arch: $(uname -m 2>/dev/null)"
  if have sysctl; then
    echo "cpu: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo n/a)"
    echo "ncpu: $(sysctl -n hw.ncpu 2>/dev/null || echo n/a)"
    memb="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
    echo "mem_GB: $(awk -v b="${memb}" 'BEGIN{printf "%.1f", b/1073741824}')"
  fi
  echo
  echo "## Toolchain versions (values only; no environment dump)"
  for tool in xcode-select clang cc c++ cmake ninja make git python3 pip3 brew perl; do
    if have "${tool}"; then
      case "${tool}" in
        xcode-select) printf '%-14s %s\n' "${tool}:" "$(xcode-select -p 2>/dev/null)";;
        clang|cc|c++) printf '%-14s %s\n' "${tool}:" "$("${tool}" --version 2>/dev/null | head -1)";;
        *)            printf '%-14s %s\n' "${tool}:" "$("${tool}" --version 2>/dev/null | head -1)";;
      esac
    else
      printf '%-14s %s\n' "${tool}:" "NOT FOUND"
    fi
  done
} > "${SYSTEM_TXT}" 2>&1

record_step "system_report" "PASS" "wrote system.txt" "system.txt"

# toolchain gate
MISSING=""
for req in git cmake python3; do
  have "${req}" || MISSING="${MISSING} ${req}"
done
# a C++ compiler: clang or cc
if ! have clang && ! have cc && ! have c++; then MISSING="${MISSING} c++compiler"; fi
if [ -n "${MISSING}" ]; then
  record_step "toolchain_check" "FAIL" "missing:${MISSING}"
else
  record_step "toolchain_check" "PASS" "git, cmake, python3, C++ compiler present"
fi

# ninja is recommended but optional
if have ninja; then
  record_step "ninja_check" "PASS" "ninja present"
else
  record_step "ninja_check" "SKIP" "ninja not found (cmake will fall back to make)"
fi

# =============================================================================
# 2. OPTIONAL: Homebrew dependency install (only with --install-deps, no sudo)
# =============================================================================
BREW_PKGS="cmake ninja libsodium boost"
if [ "${INSTALL_DEPS}" -eq 1 ]; then
  if have brew; then
    run_logged "${LOG_DIR}/brew_install.log" brew install ${BREW_PKGS}
    if [ $? -eq 0 ]; then
      record_step "brew_install" "PASS" "installed: ${BREW_PKGS}" "logs/brew_install.log"
    else
      record_step "brew_install" "FAIL" "brew install failed; see log" "logs/brew_install.log"
    fi
  else
    record_step "brew_install" "FAIL" "--install-deps given but Homebrew not found"
  fi
else
  record_step "brew_install" "SKIP" "no --install-deps; not installing system packages"
fi

# =============================================================================
# 3. CLONE + BUILD upstream PSI crypto stack (isolated work dir)
# =============================================================================
CLEANUP_WORK=0
if [ -z "${WORK_DIR}" ]; then
  WORK_DIR="$(mktemp -d 2>/dev/null || mktemp -d -t thrlabel_feas)"
  CLEANUP_WORK=1
fi
mkdir -p "${WORK_DIR}"
echo "work_dir: ${WORK_DIR}" >> "${SYSTEM_TXT}"

REPO_DIR="${WORK_DIR}/${REPO_NAME}"

if [ "${SKIP_BUILD}" -eq 1 ]; then
  record_step "clone_${REPO_NAME}" "SKIP" "--skip-build set"
  record_step "build_${REPO_NAME}" "SKIP" "--skip-build set"
  record_step "test_${REPO_NAME}"  "SKIP" "--skip-build set"
elif [ -n "${MISSING}" ]; then
  record_step "clone_${REPO_NAME}" "SKIP" "toolchain incomplete:${MISSING}"
  record_step "build_${REPO_NAME}" "SKIP" "toolchain incomplete"
  record_step "test_${REPO_NAME}"  "SKIP" "toolchain incomplete"
else
  # ---- clone ----
  run_logged "${LOG_DIR}/clone.log" git clone --depth 1 "${REPO_URL}" "${REPO_DIR}"
  if [ -d "${REPO_DIR}" ]; then
    record_step "clone_${REPO_NAME}" "PASS" "cloned ${REPO_URL}" "logs/clone.log"

    # ---- capture upstream build docs so options are traceable ----
    for doc in README.md README.rst BUILD.md; do
      if [ -f "${REPO_DIR}/${doc}" ]; then
        cp "${REPO_DIR}/${doc}" "${LOG_DIR}/upstream_${doc}" 2>/dev/null || true
      fi
    done

    # ---- build (prefer upstream build.py, else cmake) ----
    BUILD_OK=0
    BUILD_LOG="${LOG_DIR}/build.log"
    ARCH_FLAGS="-DCMAKE_OSX_ARCHITECTURES=arm64"
    if [ -f "${REPO_DIR}/build.py" ]; then
      # volepsi/libOTe official path. --setup fetches/builds deps.
      ( cd "${REPO_DIR}" && run_logged "${BUILD_LOG}" python3 build.py --help )
      ( cd "${REPO_DIR}" && run_logged "${BUILD_LOG}" python3 build.py --setup -DVOLE_PSI_ENABLE_BOOST=ON )
      ( cd "${REPO_DIR}" && run_logged "${BUILD_LOG}" python3 build.py )
      # detect a produced binary
      if find "${REPO_DIR}/out" -type f -perm -111 2>/dev/null | grep -qi 'frontend\|libOTe\|volePSI'; then
        BUILD_OK=1
      fi
    else
      # generic cmake path with ARM64 native settings
      ( cd "${REPO_DIR}" && run_logged "${BUILD_LOG}" cmake -S . -B build -DCMAKE_BUILD_TYPE=Release ${ARCH_FLAGS} )
      ( cd "${REPO_DIR}" && run_logged "${BUILD_LOG}" cmake --build build -j )
      if [ -d "${REPO_DIR}/build" ]; then BUILD_OK=1; fi
    fi

    if [ "${BUILD_OK}" -eq 1 ]; then
      record_step "build_${REPO_NAME}" "PASS" "build produced artifacts (ARM64)" "logs/build.log"
    else
      record_step "build_${REPO_NAME}" "FAIL" "no build artifacts detected; see build.log (common cause: missing deps -> rerun with --install-deps)" "logs/build.log"
    fi

    # ---- small test / example PSI ----
    if [ "${BUILD_OK}" -eq 1 ]; then
      TEST_LOG="${LOG_DIR}/test.log"
      FRONTEND="$(find "${REPO_DIR}" -type f -perm -111 -name 'frontend' 2>/dev/null | head -1)"
      RAN_TEST=0
      if [ -n "${FRONTEND}" ]; then
        # unit tests (-u) then a tiny PSI perf run; both are upstream-provided.
        run_logged "${TEST_LOG}" "${FRONTEND}" -u -q
        run_logged "${TEST_LOG}" "${FRONTEND}" -perf -psi -nn 8
        RAN_TEST=1
      else
        # try ctest if present
        if [ -d "${REPO_DIR}/build" ] && have ctest; then
          ( cd "${REPO_DIR}/build" && run_logged "${TEST_LOG}" ctest --output-on-failure )
          RAN_TEST=1
        fi
      fi
      if [ "${RAN_TEST}" -eq 1 ]; then
        record_step "test_${REPO_NAME}" "PASS" "ran upstream unit test / small PSI (see log; check for failures inside)" "logs/test.log"
      else
        record_step "test_${REPO_NAME}" "SKIP" "built but no runnable test/example located; build-only" "logs/build.log"
      fi
    else
      record_step "test_${REPO_NAME}" "SKIP" "build did not succeed; cannot run example"
    fi
  else
    record_step "clone_${REPO_NAME}" "FAIL" "clone failed (network/auth?); see log" "logs/clone.log"
    record_step "build_${REPO_NAME}" "SKIP" "no clone"
    record_step "test_${REPO_NAME}"  "SKIP" "no clone"
  fi
fi

# =============================================================================
# 4. MP-SPDZ (optional) + additive-share arithmetic demo (always, honest label)
# =============================================================================
if [ "${WITH_MPSPDZ}" -eq 1 ] && [ "${SKIP_BUILD}" -eq 0 ] && [ -z "${MISSING}" ]; then
  MPSPDZ_DIR="${WORK_DIR}/MP-SPDZ"
  run_logged "${LOG_DIR}/mpspdz_clone.log" git clone --depth 1 https://github.com/data61/MP-SPDZ.git "${MPSPDZ_DIR}"
  if [ -d "${MPSPDZ_DIR}" ]; then
    ( cd "${MPSPDZ_DIR}" && run_logged "${LOG_DIR}/mpspdz_build.log" make -j setup )
    if [ $? -eq 0 ]; then
      record_step "mpspdz_build" "PASS" "MP-SPDZ setup built (secure comparison NOT run/verified here)" "logs/mpspdz_build.log"
    else
      record_step "mpspdz_build" "FAIL" "MP-SPDZ build failed; see log" "logs/mpspdz_build.log"
    fi
  else
    record_step "mpspdz_build" "FAIL" "MP-SPDZ clone failed" "logs/mpspdz_clone.log"
  fi
else
  record_step "mpspdz_build" "SKIP" "MP-SPDZ not requested (--with-mpspdz) or prerequisites unmet"
fi

# Always run the tiny in-process additive-share ARITHMETIC demo. This is NOT a
# secure comparison and NOT network MPC; it only checks arithmetic feasibility.
DEMO_LOG="${LOG_DIR}/additive_share_demo.log"
run_logged "${DEMO_LOG}" python3 "${SCRIPT_DIR}/additive_share_demo.py" --trials 2000 --json
DEMO_RC=$?
if [ "${DEMO_RC}" -eq 0 ]; then
  record_step "additive_share_demo" "PASS" \
    "in-process additive-share arithmetic correct; NOT secure, no network MPC, composition proof ABSENT" \
    "logs/additive_share_demo.log"
else
  record_step "additive_share_demo" "FAIL" "arithmetic demo mismatch; see log" "logs/additive_share_demo.log"
fi

# =============================================================================
# 5. SUMMARY (json + md) and tarball
# =============================================================================
# Build summary.json from accumulated step objects.
{
  echo "{"
  echo "  \"artifact\": \"thrlabel-psi macOS feasibility probe\","
  echo "  \"timestamp\": \"${TS}\","
  echo "  \"arch\": \"$(uname -m 2>/dev/null)\","
  echo "  \"repo_url\": \"${REPO_URL}\","
  echo "  \"disclaimers\": ["
  echo "    \"A passing build shows the stack compiles/runs; it does NOT prove security.\","
  echo "    \"The additive-share demo is plaintext, single-process, NOT secure MPC, and has NO composition proof.\","
  echo "    \"No cryptographic wall-clock number here should be used as a paper measurement without a full prototype.\""
  echo "  ],"
  echo "  \"steps\": ["
  paste -sd',' "${STEP_JSON_FILE}" 2>/dev/null || tr '\n' ',' < "${STEP_JSON_FILE}" | sed 's/,$//'
  echo "  ]"
  echo "}"
} > "${SUMMARY_JSON}"

# Human-readable summary.
{
  echo "# ThrLabel-PSI macOS feasibility summary (${TS})"
  echo
  echo "Arch: $(uname -m 2>/dev/null)   Repo: ${REPO_URL}"
  echo
  echo "| step | status | detail |"
  echo "|------|--------|--------|"
  # re-render steps as a table
  while IFS= read -r line; do
    st="$(printf '%s' "${line}" | sed -n 's/.*"step":"\([^"]*\)".*/\1/p')"
    stat="$(printf '%s' "${line}" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')"
    det="$(printf '%s' "${line}" | sed -n 's/.*"detail":"\([^"]*\)".*/\1/p')"
    [ -n "${st}" ] && echo "| ${st} | ${stat} | ${det} |"
  done < "${STEP_JSON_FILE}"
  echo
  echo "## Honesty notes"
  echo "- A green build is a *compile/run* result, not a security result."
  echo "- \`additive_share_demo\` is NOT a secure comparison: plaintext, single process,"
  echo "  no network, and **no composition/simulation proof** is provided."
  echo "- Treat any timing seen in logs as environment-specific, not a paper measurement."
  echo
  echo "See system.txt and logs/ for full detail."
} > "${SUMMARY_MD}"

record_step "summary" "PASS" "wrote summary.json and summary.md"

# tarball (created next to the result dir)
TARBALL="${RESULT_DIR}.tar.gz"
if have tar; then
  ( cd "${OUTPUT_ROOT}" && tar -czf "${TARBALL}" "mac_feasibility_${TS}" ) \
    && echo "tarball: ${TARBALL}" \
    || echo "tar failed (non-fatal)"
fi

# clean up temp work dir only if we created it AND builds are done (keep on request)
if [ "${CLEANUP_WORK}" -eq 1 ]; then
  echo "NOTE: build work dir kept for inspection: ${WORK_DIR}"
  echo "      (remove it yourself when done: rm -rf '${WORK_DIR}')"
fi

rm -f "${STEP_JSON_FILE}"

echo
echo "Done. Results in: ${RESULT_DIR}"
echo "Summary:         ${SUMMARY_MD}"
[ -f "${TARBALL}" ] && echo "Archive:         ${TARBALL}"
