#!/usr/bin/env bash
# benchmark_cobra.sh — C²oBra only
# Usage: ./benchmark_cobra.sh tests/Problem_16.c /path/to/test-suite

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILE="${1:-tests/Problem_16.c}"
SUITE_DIR="${2:-/home/glebt/sikraken/sikraken_output/Problem_16/test-suite}"

BASE=$(basename "$FILE" .c)
FILE_OUT="${SCRIPT_DIR}/output/benchmark_cobra/${BASE}"
RESULTS="${FILE_OUT}/results.txt"
mkdir -p "$FILE_OUT"

if [ -f "${SCRIPT_DIR}/venv/bin/activate" ]; then
    source "${SCRIPT_DIR}/venv/bin/activate"
fi
export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

echo "========================================" | tee "$RESULTS"
echo " C²oBra Benchmark: $BASE"                 | tee -a "$RESULTS"
echo " Suite:  $SUITE_DIR"                      | tee -a "$RESULTS"
echo " Date:   $(date)"                         | tee -a "$RESULTS"
echo "========================================" | tee -a "$RESULTS"

# ── Clean stale outputs ───────────────────────────────────────────────────────
rm -f "${SCRIPT_DIR}/output/${BASE}_inst.c" \
      "${SCRIPT_DIR}/output/${BASE}_inst_branch_map.json" \
      "${SCRIPT_DIR}/output/coverage_report.json" \
      "${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"

mkdir -p "${SCRIPT_DIR}/output" "${SCRIPT_DIR}/build"

# ── Step 1: Instrument ────────────────────────────────────────────────────────
echo "" | tee -a "$RESULTS"
echo "[1/4] Instrumenting..." | tee -a "$RESULTS"
T_INST_START=$(date +%s%N)

INST_OUT=$(python3 "${SCRIPT_DIR}/src/instrument.py" "$FILE" \
    "${SCRIPT_DIR}/output/${BASE}_inst.c" 2>&1)
INST_EC=$?
BRANCH_COUNTERS=$(echo "$INST_OUT" | grep '^BRANCH_COUNTERS=' | cut -d= -f2)

T_INST_END=$(date +%s%N)
T_INST=$(( (T_INST_END - T_INST_START) / 1000000 ))

if [ "$INST_EC" -ne 0 ]; then
    echo "❌ Instrumentation failed (exit $INST_EC)" | tee -a "$RESULTS"
    echo "$INST_OUT" | tee -a "$RESULTS"
    exit 1
fi
echo "   ✅ Done in ${T_INST}ms — branches: ${BRANCH_COUNTERS:-unknown}" | tee -a "$RESULTS"

# ── Step 2: Compile ───────────────────────────────────────────────────────────
echo "" | tee -a "$RESULTS"
echo "[2/4] Compiling..." | tee -a "$RESULTS"
T_COMP_START=$(date +%s%N)

gcc "${SCRIPT_DIR}/output/${BASE}_inst.c" \
    "${SCRIPT_DIR}/src/cov_runtime.c" \
    "${SCRIPT_DIR}/src/verifier_stubs.c" \
    -o "${SCRIPT_DIR}/build/${BASE}_test" \
    -I "${SCRIPT_DIR}/src/" \
    -DMAX_BRANCHES=${BRANCH_COUNTERS:-131072} -w
COMP_EC=$?

T_COMP_END=$(date +%s%N)
T_COMP=$(( (T_COMP_END - T_COMP_START) / 1000000 ))

if [ "$COMP_EC" -ne 0 ]; then
    echo "❌ Compilation failed (exit $COMP_EC)" | tee -a "$RESULTS"
    exit 1
fi
echo "   ✅ Done in ${T_COMP}ms" | tee -a "$RESULTS"

# ── Step 3: Run tests ─────────────────────────────────────────────────────────
echo "" | tee -a "$RESULTS"
echo "[3/4] Running tests..." | tee -a "$RESULTS"
T_RUN_START=$(date +%s%N)

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

T_RUN_END=$(date +%s%N)
T_RUN=$(( (T_RUN_END - T_RUN_START) / 1000000 ))
echo "   ✅ Done in ${T_RUN}ms (exit $RUN_EC)" | tee -a "$RESULTS"

# ── Step 4: Report ────────────────────────────────────────────────────────────
echo "" | tee -a "$RESULTS"
echo "[4/4] Generating report..." | tee -a "$RESULTS"
T_REP_START=$(date +%s%N)

python3 "${SCRIPT_DIR}/src/report.py" \
    "${SCRIPT_DIR}/output/${BASE}_inst_branch_map.json" \
    "${SCRIPT_DIR}/output/${BASE}_inst_coverage.json" \
    --output "${SCRIPT_DIR}/output/${BASE}_inst_report.html" \
    --csv    "${SCRIPT_DIR}/output/${BASE}_inst_report.csv" \
    --no-summary >> "${FILE_OUT}/c2obra.log" 2>&1

T_REP_END=$(date +%s%N)
T_REP=$(( (T_REP_END - T_REP_START) / 1000000 ))
echo "   ✅ Done in ${T_REP}ms" | tee -a "$RESULTS"

# ── Coverage result ───────────────────────────────────────────────────────────
JSON="${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"
C2OBRA_PCT="N/A"; COV_COVERED="N/A"; COV_TOTAL="N/A"
if [ -f "$JSON" ]; then
    read C2OBRA_PCT COV_COVERED COV_TOTAL < <(python3 -c "
import json
try:
    d = json.load(open('$JSON'))
    s = d.get('summary', {})
    print(s.get('branch_coverage_pct','N/A'), s.get('covered_branches','N/A'), s.get('total_branches_count','N/A'))
except:
    print('N/A N/A N/A')
" 2>/dev/null)
fi

T_TOTAL=$(( T_INST + T_COMP + T_RUN + T_REP ))

echo "" | tee -a "$RESULTS"
echo "========================================" | tee -a "$RESULTS"
echo " RESULTS: $BASE"                          | tee -a "$RESULTS"
echo "========================================" | tee -a "$RESULTS"
printf " Coverage:      %s%%\n"   "$C2OBRA_PCT"               | tee -a "$RESULTS"
printf " Branches:      %s / %s\n" "$COV_COVERED" "$COV_TOTAL" | tee -a "$RESULTS"
echo "----------------------------------------" | tee -a "$RESULTS"
printf " Instrument:    %sms\n"   "$T_INST"                    | tee -a "$RESULTS"
printf " Compile:       %sms\n"   "$T_COMP"                    | tee -a "$RESULTS"
printf " Run tests:     %sms\n"   "$T_RUN"                     | tee -a "$RESULTS"
printf " Report:        %sms\n"   "$T_REP"                     | tee -a "$RESULTS"
printf " TOTAL:         %sms\n"   "$T_TOTAL"                   | tee -a "$RESULTS"
echo "========================================" | tee -a "$RESULTS"
echo "" | tee -a "$RESULTS"
echo "Full log → ${FILE_OUT}/c2obra.log"
echo "HTML report → ${SCRIPT_DIR}/output/${BASE}_inst_report.html"