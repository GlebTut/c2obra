#!/usr/bin/env bash
# benchmark_cobra.sh — C²oBra vs TestCoCa vs TestCov, single file, with timing
# Usage: bash benchmark_cobra.sh <file.c> <path/to/test-suite>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILE="${1:-tests/Problem_16.c}"
SUITE_DIR="${2:-/home/glebt/sikraken/sikraken_output/Problem_16/test-suite}"

TESTCOCA_PY="${HOME}/testcoca/dist/TestCoCa.py"
TESTCOV_BIN="${HOME}/test-suite-validator/bin/testcov"
TESTCOV_GOAL="${HOME}/test-suite-validator/contrib/goal_files/coverage-branches.prp"
TOOL_TIMEOUT=120

BASE=$(basename "$FILE" .c)
FILE_OUT="${SCRIPT_DIR}/output/benchmark_cobra/${BASE}"
RESULTS="${FILE_OUT}/results.txt"
mkdir -p "$FILE_OUT"

if [ -f "${SCRIPT_DIR}/venv/bin/activate" ]; then
    source "${SCRIPT_DIR}/venv/bin/activate"
fi
export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [ ! -f "$FILE" ]; then
    echo "❌ Source file not found: $FILE"
    exit 1
fi
if [ ! -d "$SUITE_DIR" ]; then
    echo "❌ Test suite not found: $SUITE_DIR"
    exit 1
fi

echo "========================================" | tee "$RESULTS"
echo " Benchmark: $BASE"                        | tee -a "$RESULTS"
echo " Suite:     $SUITE_DIR"                   | tee -a "$RESULTS"
echo " Date:      $(date)"                      | tee -a "$RESULTS"
echo "========================================" | tee -a "$RESULTS"

# ── Clean stale C²oBra outputs ────────────────────────────────────────────────
rm -f "${SCRIPT_DIR}/output/${BASE}_inst.c" \
      "${SCRIPT_DIR}/output/${BASE}_inst_branch_map.json" \
      "${SCRIPT_DIR}/output/coverage_report.json" \
      "${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"

mkdir -p "${SCRIPT_DIR}/output" "${SCRIPT_DIR}/build"

# ── Helper: millisecond timer ─────────────────────────────────────────────────
now_ms() { date +%s%3N; }

# ── Helper: proportional bar ──────────────────────────────────────────────────
make_bar() {
    local ms=$1 total=$2 char=$3 width=28
    [ "$total" -eq 0 ] && return
    local n=$(( ms * width / total ))
    local result=""
    for ((i=0; i<n; i++)); do result+="$char"; done
    echo "$result"
}

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — C²oBra (4 steps)
# ══════════════════════════════════════════════════════════════════════════════
echo "" | tee -a "$RESULTS"
echo "[ C²oBra ]" | tee -a "$RESULTS"

# Step 1: Instrument
printf "  [1/4] Instrumenting...   " | tee -a "$RESULTS"
T_INST_START=$(now_ms)

INST_OUT=$(python3 "${SCRIPT_DIR}/src/instrument.py" "$FILE" \
    "${SCRIPT_DIR}/output/${BASE}_inst.c" 2>&1)
INST_EC=$?
BRANCH_COUNTERS=$(echo "$INST_OUT" | grep '^BRANCH_COUNTERS=' | cut -d= -f2)
T_INST=$(( $(now_ms) - T_INST_START ))

if [ "$INST_EC" -ne 0 ]; then
    printf "❌ Failed (exit %s) in %sms\n" "$INST_EC" "$T_INST" | tee -a "$RESULTS"
    echo "$INST_OUT" | tee -a "$RESULTS"
    exit 1
fi
printf "✅ %sms — branches: %s\n" "$T_INST" "${BRANCH_COUNTERS:-unknown}" | tee -a "$RESULTS"

# Step 2: Compile
printf "  [2/4] Compiling...       " | tee -a "$RESULTS"
T_COMP_START=$(now_ms)

gcc "${SCRIPT_DIR}/output/${BASE}_inst.c" \
    "${SCRIPT_DIR}/src/cov_runtime.c" \
    "${SCRIPT_DIR}/src/verifier_stubs.c" \
    -o "${SCRIPT_DIR}/build/${BASE}_test" \
    -I "${SCRIPT_DIR}/src/" \
    -DMAX_BRANCHES=${BRANCH_COUNTERS:-131072} -w
COMP_EC=$?
T_COMP=$(( $(now_ms) - T_COMP_START ))

if [ "$COMP_EC" -ne 0 ]; then
    printf "❌ Failed (exit %s) in %sms\n" "$COMP_EC" "$T_COMP" | tee -a "$RESULTS"
    exit 1
fi
printf "✅ %sms\n" "$T_COMP" | tee -a "$RESULTS"

# Step 3: Run tests
printf "  [3/4] Running tests...   " | tee -a "$RESULTS"
T_RUN_START=$(now_ms)

( cd "${SCRIPT_DIR}" && \
  python3 src/run_tests.py \
    "build/${BASE}_test" \
    "$SUITE_DIR" \
    "output/${BASE}_inst_branch_map.json" \
    > "${FILE_OUT}/c2obra.log" 2>&1 )
RUN_EC=$?

[ -f "${SCRIPT_DIR}/output/test_inputs_log.json" ] && \
    mv "${SCRIPT_DIR}/output/test_inputs_log.json" \
       "${SCRIPT_DIR}/output/${BASE}_inst_test_inputs_log.json"
[ -f "${SCRIPT_DIR}/output/coverage_report.json" ] && \
    cp "${SCRIPT_DIR}/output/coverage_report.json" \
       "${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"

T_RUN=$(( $(now_ms) - T_RUN_START ))
printf "✅ %sms (exit %s)\n" "$T_RUN" "$RUN_EC" | tee -a "$RESULTS"

# Step 4: Report
printf "  [4/4] Generating report... " | tee -a "$RESULTS"
T_REP_START=$(now_ms)

python3 "${SCRIPT_DIR}/src/report.py" \
    "${SCRIPT_DIR}/output/${BASE}_inst_branch_map.json" \
    "${SCRIPT_DIR}/output/${BASE}_inst_coverage.json" \
    --output "${SCRIPT_DIR}/output/${BASE}_inst_report.html" \
    --csv    "${SCRIPT_DIR}/output/${BASE}_inst_report.csv" \
    --no-summary >> "${FILE_OUT}/c2obra.log" 2>&1
REP_EC=$?
T_REP=$(( $(now_ms) - T_REP_START ))

if [ "$REP_EC" -ne 0 ]; then
    printf "❌ Failed (exit %s) in %sms\n" "$REP_EC" "$T_REP" | tee -a "$RESULTS"
else
    printf "✅ %sms\n" "$T_REP" | tee -a "$RESULTS"
fi

# Read C²oBra coverage result
JSON="${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"
C2OBRA_PCT="N/A"; COV_COVERED="N/A"; COV_TOTAL="N/A"
if [ -f "$JSON" ]; then
    read -r C2OBRA_PCT COV_COVERED COV_TOTAL < <(python3 -c "
import json
try:
    d = json.load(open('$JSON'))
    s = d.get('summary', {})
    total = s.get('total_branches_count', s.get('total_branches', 'N/A'))
    print(s.get('branch_coverage_pct','N/A'), s.get('covered_branches','N/A'), total)
except:
    print('N/A N/A N/A')
" 2>/dev/null)
fi
T_C2OBRA=$(( T_INST + T_COMP + T_RUN + T_REP ))

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TestCoCa
# ══════════════════════════════════════════════════════════════════════════════
echo "" | tee -a "$RESULTS"
echo "[ TestCoCa ]" | tee -a "$RESULTS"

TESTCOCA_PCT="N/A"; T_TESTCOCA="N/A"; TESTCOCA_NOTE=""
TESTCOCA_OUT="${FILE_OUT}/testcoca_out"
mkdir -p "$TESTCOCA_OUT"

if [ ! -f "$TESTCOCA_PY" ]; then
    echo "  ⚠️  Not installed — skipping" | tee -a "$RESULTS"
    TESTCOCA_NOTE="not_installed"
else
    printf "  [1/1] Running TestCoCa... " | tee -a "$RESULTS"
    T_TC_START=$(now_ms)

    if timeout "$TOOL_TIMEOUT" python3 "$TESTCOCA_PY" \
        --input_file "$FILE" \
        --test_suite "$SUITE_DIR" \
        --output_dir "$TESTCOCA_OUT" \
        > "${FILE_OUT}/testcoca.log" 2>&1; then

        T_TESTCOCA=$(( $(now_ms) - T_TC_START ))
        RESULT_JSON=$(find "$TESTCOCA_OUT" -name "*.json" | head -1)
        if [ -n "$RESULT_JSON" ] && [ -f "$RESULT_JSON" ]; then
            TESTCOCA_PCT=$(python3 -c "
import json
try:
    d = json.load(open('$RESULT_JSON'))
    v = float(d.get('coverage', 0))
    print(round(v * 100, 1))
except:
    print('N/A')
" 2>/dev/null)
            printf "✅ %sms — coverage: %s%%\n" "$T_TESTCOCA" "$TESTCOCA_PCT" | tee -a "$RESULTS"
        else
            printf "⚠️  %sms — no result JSON found\n" "$T_TESTCOCA" | tee -a "$RESULTS"
            TESTCOCA_NOTE="no_json"
        fi
    else
        EXIT_CODE=$?
        T_TESTCOCA=$(( $(now_ms) - T_TC_START ))
        if [ "$EXIT_CODE" -eq 124 ]; then
            printf "⏱️  Timed out after %sms\n" "$T_TESTCOCA" | tee -a "$RESULTS"
            TESTCOCA_NOTE="timeout"
        else
            printf "❌ Failed (exit %s) in %sms\n" "$EXIT_CODE" "$T_TESTCOCA" | tee -a "$RESULTS"
            TESTCOCA_NOTE="exit${EXIT_CODE}"
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — TestCov
# ══════════════════════════════════════════════════════════════════════════════
echo "" | tee -a "$RESULTS"
echo "[ TestCov ]" | tee -a "$RESULTS"

TESTCOV_PCT="N/A"; T_TESTCOV="N/A"; TESTCOV_NOTE=""
TESTCOV_OUT="${FILE_OUT}/testcov_out"
mkdir -p "$TESTCOV_OUT"

if [ ! -f "$TESTCOV_BIN" ]; then
    echo "  ⚠️  Not installed — skipping" | tee -a "$RESULTS"
    TESTCOV_NOTE="not_installed"
else
    printf "  [1/1] Running TestCov...  " | tee -a "$RESULTS"
    SUITE_ZIP="${FILE_OUT}/test-suite.zip"
    if [ ! -f "$SUITE_ZIP" ]; then
        (cd "$(dirname "$SUITE_DIR")" && zip -qr "$SUITE_ZIP" "$(basename "$SUITE_DIR")")
    fi

    T_TV_START=$(now_ms)
    if timeout "$TOOL_TIMEOUT" "$TESTCOV_BIN" \
        --no-isolation \
        --no-runexec \
        --output "$TESTCOV_OUT" \
        --goal "$TESTCOV_GOAL" \
        --test-suite "$SUITE_ZIP" \
        "$FILE" > "${FILE_OUT}/testcov.log" 2>&1; then

        T_TESTCOV=$(( $(now_ms) - T_TV_START ))
        TESTCOV_PCT=$(grep -oP '(?i)branch[^:]*:\s*\K[0-9]+(\.[0-9]+)?' \
            "${FILE_OUT}/testcov.log" | tail -1)
        [ -z "$TESTCOV_PCT" ] && TESTCOV_PCT=$(grep -oP 'Coverage:\s*\K[0-9]+(\.[0-9]+)?' \
            "${FILE_OUT}/testcov.log" | tail -1)
        [ -z "$TESTCOV_PCT" ] && TESTCOV_PCT="N/A"
        printf "✅ %sms — coverage: %s%%\n" "$T_TESTCOV" "$TESTCOV_PCT" | tee -a "$RESULTS"
    else
        EXIT_CODE=$?
        T_TESTCOV=$(( $(now_ms) - T_TV_START ))
        if [ "$EXIT_CODE" -eq 124 ]; then
            printf "⏱️  Timed out after %sms\n" "$T_TESTCOV" | tee -a "$RESULTS"
            TESTCOV_NOTE="timeout"
        else
            printf "❌ Failed (exit %s) in %sms\n" "$EXIT_CODE" "$T_TESTCOV" | tee -a "$RESULTS"
            TESTCOV_NOTE="exit${EXIT_CODE}"
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# FINAL COMPARISON TABLE
# ══════════════════════════════════════════════════════════════════════════════

# Build timing bars relative to slowest tool
TIMES=("$T_C2OBRA" "$T_TESTCOCA" "$T_TESTCOV")
T_MAX=0
for T in "${TIMES[@]}"; do
    [[ "$T" =~ ^[0-9]+$ ]] && [ "$T" -gt "$T_MAX" ] && T_MAX=$T
done

BAR_C2OBRA=$(  [[ "$T_C2OBRA"   =~ ^[0-9]+$ ]] && make_bar "$T_C2OBRA"   "$T_MAX" "█" || echo "")
BAR_TESTCOCA=$(  [[ "$T_TESTCOCA" =~ ^[0-9]+$ ]] && make_bar "$T_TESTCOCA" "$T_MAX" "█" || echo "")
BAR_TESTCOV=$(   [[ "$T_TESTCOV"  =~ ^[0-9]+$ ]] && make_bar "$T_TESTCOV"  "$T_MAX" "█" || echo "")

# C²oBra step bars (relative to its own total)
BAR_INST=$(make_bar "$T_INST" "$T_C2OBRA" "█")
BAR_COMP=$(make_bar "$T_COMP" "$T_C2OBRA" "▓")
BAR_RUN=$( make_bar "$T_RUN"  "$T_C2OBRA" "░")
BAR_REP=$( make_bar "$T_REP"  "$T_C2OBRA" "▒")

echo ""                                                                        | tee -a "$RESULTS"
echo "════════════════════════════════════════════"                            | tee -a "$RESULTS"
echo " COMPARISON: $BASE"                                                      | tee -a "$RESULTS"
echo "════════════════════════════════════════════"                            | tee -a "$RESULTS"
printf " %-12s  Coverage: %6s%%   Branches: %s / %s\n" \
    "C²oBra" "$C2OBRA_PCT" "$COV_COVERED" "$COV_TOTAL"                        | tee -a "$RESULTS"
printf " %-12s  Coverage: %6s%%\n" "TestCoCa" "$TESTCOCA_PCT"                 | tee -a "$RESULTS"
printf " %-12s  Coverage: %6s%%\n" "TestCov"  "$TESTCOV_PCT"                  | tee -a "$RESULTS"
echo "────────────────────────────────────────────"                            | tee -a "$RESULTS"
printf " %-12s  Total: %6sms  %s\n" "C²oBra"   "$T_C2OBRA"   "$BAR_C2OBRA"   | tee -a "$RESULTS"
printf " %-12s  Total: %6sms  %s\n" "TestCoCa" "$T_TESTCOCA" "$BAR_TESTCOCA" | tee -a "$RESULTS"
printf " %-12s  Total: %6sms  %s\n" "TestCov"  "$T_TESTCOV"  "$BAR_TESTCOV"  | tee -a "$RESULTS"
echo "────────────────────────────────────────────"                            | tee -a "$RESULTS"
echo " C²oBra step breakdown:"                                                 | tee -a "$RESULTS"
printf "   Instrument: %6sms  %s\n" "$T_INST" "$BAR_INST"                     | tee -a "$RESULTS"
printf "   Compile:    %6sms  %s\n" "$T_COMP" "$BAR_COMP"                     | tee -a "$RESULTS"
printf "   Run tests:  %6sms  %s\n" "$T_RUN"  "$BAR_RUN"                      | tee -a "$RESULTS"
printf "   Report:     %6sms  %s\n" "$T_REP"  "$BAR_REP"                      | tee -a "$RESULTS"
echo "════════════════════════════════════════════"                            | tee -a "$RESULTS"
echo " █ Instrument  ▓ Compile  ░ Run  ▒ Report"                              | tee -a "$RESULTS"
echo "════════════════════════════════════════════"                            | tee -a "$RESULTS"
echo ""                                                                        | tee -a "$RESULTS"
echo "Logs        → ${FILE_OUT}/"
echo "Results     → $RESULTS"
echo "HTML report → ${SCRIPT_DIR}/output/${BASE}_inst_report.html"