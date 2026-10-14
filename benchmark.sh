#!/usr/bin/env bash
# benchmark.sh — C²oBra vs TestCoCa vs TestCov benchmark on test-comp files
# Usage: bash benchmark.sh [cpu_seconds] [memory_mb]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="${SCRIPT_DIR}/tests/test-comp_files"
OUTPUT_DIR="${SCRIPT_DIR}/output/benchmark"
SIKRAKEN_OUT="${SIKRAKEN_DIR:-$(dirname "$SCRIPT_DIR")/sikraken}/sikraken_output"
TESTCOCA_PY="${HOME}/testcoca/dist/TestCoCa.py"
TESTCOV_BIN="${HOME}/test-suite-validator/bin/testcov"
TESTCOV_GOAL="${HOME}/test-suite-validator/contrib/goal_files/coverage-branches.prp"
CSV="${SCRIPT_DIR}/benchmark_results.csv"

CPU="${1:-30}"
MEM="${2:-512}"
TOOL_TIMEOUT=120   # max seconds per tool call before killing it

if [ -f "${SCRIPT_DIR}/venv/bin/activate" ]; then
    source "${SCRIPT_DIR}/venv/bin/activate"
fi
export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

mkdir -p "$OUTPUT_DIR"

INTERRUPTED=0
trap 'echo -e "\n⚠️  Interrupted — CSV saved so far."; INTERRUPTED=1' INT

# Write CSV header only if starting fresh
if [ ! -f "$CSV" ]; then
    echo "file,c2obra_pct,testcoca_pct,testcov_pct,c2obra_covered,c2obra_total,c2obra_ms,testcoca_ms,testcov_ms,notes" > "$CSV"
fi

c2obra_sum=0; testcoca_sum=0; testcov_sum=0
c2obra_n=0;  testcoca_n=0;   testcov_n=0
c2obra_time_sum=0; testcoca_time_sum=0; testcov_time_sum=0
skipped=0

# Use bc for float addition — faster than spawning python3 per file
add_float() { echo "$1 + $2" | bc -l 2>/dev/null || echo "$1"; }

# Returns elapsed milliseconds: elapsed_ms <start_ns>
elapsed_ms() { echo "scale=0; ($EPOCHREALTIME_NOW - $1) / 1000000" | bc 2>/dev/null || echo "N/A"; }

# Cross-platform nanosecond timer — falls back to date +%s%3N (milliseconds)
now_ms() { date +%s%3N; }

total_files=$(find "$TEST_DIR" -maxdepth 1 -name "*.c" | wc -l)
echo "=== C²oBra vs TestCoCa vs TestCov Benchmark: $total_files files ==="
echo "    CPU limit : ${CPU}s  |  Memory limit : ${MEM}MB  |  Tool timeout : ${TOOL_TIMEOUT}s"
echo "    CSV       : $CSV"
echo ""

idx=0
for SRC in "$TEST_DIR"/*.c; do
    [ -f "$SRC" ] || continue
    [ "$INTERRUPTED" -eq 1 ] && break

    idx=$((idx + 1))
    BASE=$(basename "$SRC" .c)
    FILE_OUT="${OUTPUT_DIR}/${BASE}"
    mkdir -p "$FILE_OUT"

    printf "[%3d/%d] %-45s " "$idx" "$total_files" "$BASE"

    # Resume: skip if already recorded in CSV
    if grep -q "^${BASE}\.c," "$CSV" 2>/dev/null; then
        echo "SKIP"
        skipped=$((skipped+1))
        continue
    fi

    NOTES=""
    C2OBRA_PCT="N/A"; TESTCOCA_PCT="N/A"; TESTCOV_PCT="N/A"
    COV_COVERED="N/A"; COV_TOTAL="N/A"
    C2OBRA_MS="N/A";  TESTCOCA_MS="N/A"; TESTCOV_MS="N/A"

    # ── 1. C²oBra ──────────────────────────────────────────────────────────
    T_START=$(now_ms)
    if ( ulimit -t "$CPU" -v $((MEM * 1024)) 2>/dev/null
         cd "${SCRIPT_DIR}"
         timeout "$TOOL_TIMEOUT" bash "${SCRIPT_DIR}/c2obra.sh" "$SRC" \
         > "${FILE_OUT}/c2obra.log" 2>&1 ); then
        C2OBRA_MS=$(( $(now_ms) - T_START ))
        JSON="${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"
        if [ -f "$JSON" ]; then
            read -r C2OBRA_PCT COV_COVERED COV_TOTAL < <(python3 -c "
import json
try:
    d = json.load(open('$JSON'))
    s = d.get('summary', {})
    print(s.get('branch_coverage_pct','N/A'), s.get('covered_branches','N/A'), s.get('total_branches','N/A'))
except:
    print('N/A N/A N/A')
" 2>/dev/null)
            cp "$JSON" "${FILE_OUT}/" 2>/dev/null || true
        else
            NOTES="c2obra:no_json"
        fi
    else
        EXIT_CODE=$?
        C2OBRA_MS=$(( $(now_ms) - T_START ))
        if [ $EXIT_CODE -eq 124 ]; then
            NOTES="c2obra:tool_timeout"
        else
            NOTES="c2obra:exit${EXIT_CODE}"
        fi
    fi

    SUITE_DIR="${SIKRAKEN_OUT}/${BASE}/test-suite"

    # ── 2. TestCoCa ────────────────────────────────────────────────────────
    TESTCOCA_OUT="${FILE_OUT}/testcoca_out"
    mkdir -p "$TESTCOCA_OUT"

    if [ -f "$TESTCOCA_PY" ] && [ -d "$SUITE_DIR" ]; then
        T_START=$(now_ms)
        if timeout "$TOOL_TIMEOUT" python3 "$TESTCOCA_PY" \
            --input_file "$SRC" \
            --test_suite "$SUITE_DIR" \
            --output_dir "$TESTCOCA_OUT" \
            > "${FILE_OUT}/testcoca.log" 2>&1; then
            TESTCOCA_MS=$(( $(now_ms) - T_START ))
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
            else
                NOTES="${NOTES:+$NOTES }testcoca:no_json"
            fi
        else
            EXIT_CODE=$?
            TESTCOCA_MS=$(( $(now_ms) - T_START ))
            if [ $EXIT_CODE -eq 124 ]; then
                NOTES="${NOTES:+$NOTES }testcoca:tool_timeout"
            else
                NOTES="${NOTES:+$NOTES }testcoca:exit${EXIT_CODE}"
            fi
        fi
    elif [ ! -d "$SUITE_DIR" ]; then
        NOTES="${NOTES:+$NOTES }testcoca:no_suite"
    else
        NOTES="${NOTES:+$NOTES }testcoca:not_installed"
    fi

    # ── 3. TestCov ─────────────────────────────────────────────────────────
    TESTCOV_OUT="${FILE_OUT}/testcov_out"
    mkdir -p "$TESTCOV_OUT"

    if [ -f "$TESTCOV_BIN" ] && [ -d "$SUITE_DIR" ]; then
        SUITE_ZIP="${FILE_OUT}/test-suite.zip"
        if [ ! -f "$SUITE_ZIP" ]; then
            (cd "$(dirname "$SUITE_DIR")" && zip -qr "$SUITE_ZIP" "$(basename "$SUITE_DIR")")
        fi
        T_START=$(now_ms)
        if timeout "$TOOL_TIMEOUT" "$TESTCOV_BIN" \
            --no-isolation \
            --no-runexec \
            --output "$TESTCOV_OUT" \
            --goal "$TESTCOV_GOAL" \
            --test-suite "$SUITE_ZIP" \
            "$SRC" > "${FILE_OUT}/testcov.log" 2>&1; then
            TESTCOV_MS=$(( $(now_ms) - T_START ))
            TESTCOV_PCT=$(grep -oP '(?i)branch[^:]*:\s*\K[0-9]+(\.[0-9]+)?' \
                "${FILE_OUT}/testcov.log" | tail -1)
            if [ -z "$TESTCOV_PCT" ]; then
                TESTCOV_PCT=$(grep -oP 'Coverage:\s*\K[0-9]+(\.[0-9]+)?' \
                    "${FILE_OUT}/testcov.log" | tail -1)
            fi
            [ -z "$TESTCOV_PCT" ] && TESTCOV_PCT="N/A"
        else
            EXIT_CODE=$?
            TESTCOV_MS=$(( $(now_ms) - T_START ))
            if [ $EXIT_CODE -eq 124 ]; then
                NOTES="${NOTES:+$NOTES }testcov:tool_timeout"
            else
                NOTES="${NOTES:+$NOTES }testcov:exit${EXIT_CODE}"
            fi
        fi
    elif [ ! -d "$SUITE_DIR" ]; then
        NOTES="${NOTES:+$NOTES }testcov:no_suite"
    else
        NOTES="${NOTES:+$NOTES }testcov:not_installed"
    fi

    # ── 4. Write CSV row ───────────────────────────────────────────────────
    echo "${BASE}.c,${C2OBRA_PCT},${TESTCOCA_PCT},${TESTCOV_PCT},${COV_COVERED},${COV_TOTAL},${C2OBRA_MS},${TESTCOCA_MS},${TESTCOV_MS},${NOTES# }" >> "$CSV"

    # ── 5. Accumulate averages ─────────────────────────────────────────────
    if [[ "$C2OBRA_PCT"   =~ ^[0-9] ]]; then c2obra_sum=$(add_float "$c2obra_sum" "$C2OBRA_PCT"); c2obra_n=$((c2obra_n+1)); fi
    if [[ "$TESTCOCA_PCT" =~ ^[0-9] ]]; then testcoca_sum=$(add_float "$testcoca_sum" "$TESTCOCA_PCT"); testcoca_n=$((testcoca_n+1)); fi
    if [[ "$TESTCOV_PCT"  =~ ^[0-9] ]]; then testcov_sum=$(add_float "$testcov_sum" "$TESTCOV_PCT"); testcov_n=$((testcov_n+1)); fi
    if [[ "$C2OBRA_MS"   =~ ^[0-9] ]]; then c2obra_time_sum=$(add_float "$c2obra_time_sum" "$C2OBRA_MS"); fi
    if [[ "$TESTCOCA_MS" =~ ^[0-9] ]]; then testcoca_time_sum=$(add_float "$testcoca_time_sum" "$TESTCOCA_MS"); fi
    if [[ "$TESTCOV_MS"  =~ ^[0-9] ]]; then testcov_time_sum=$(add_float "$testcov_time_sum" "$TESTCOV_MS"); fi

    printf "C²oBra:%6s%% (%5sms) | TestCoCa:%6s%% (%5sms) | TestCov:%6s%% (%5sms)\n" \
        "$C2OBRA_PCT" "$C2OBRA_MS" "$TESTCOCA_PCT" "$TESTCOCA_MS" "$TESTCOV_PCT" "$TESTCOV_MS"
done

# ── Final averages ─────────────────────────────────────────────────────────────
avg()     { [ "$2" -gt 0 ] && echo "scale=2; $1 / $2" | bc -l 2>/dev/null || echo "N/A"; }
avg_ms()  { [ "$2" -gt 0 ] && echo "scale=0; $1 / $2" | bc -l 2>/dev/null || echo "N/A"; }

AVG_C2OBRA=$(avg   "$c2obra_sum"   "$c2obra_n")
AVG_TESTCOCA=$(avg "$testcoca_sum" "$testcoca_n")
AVG_TESTCOV=$(avg  "$testcov_sum"  "$testcov_n")

AVG_C2OBRA_MS=$(avg_ms   "$c2obra_time_sum"   "$c2obra_n")
AVG_TESTCOCA_MS=$(avg_ms "$testcoca_time_sum" "$testcoca_n")
AVG_TESTCOV_MS=$(avg_ms  "$testcov_time_sum"  "$testcov_n")

echo "AVERAGE,${AVG_C2OBRA},${AVG_TESTCOCA},${AVG_TESTCOV},,,${AVG_C2OBRA_MS},${AVG_TESTCOCA_MS},${AVG_TESTCOV_MS},processed=${c2obra_n} skipped=${skipped}" >> "$CSV"

echo ""
echo "========================================================"
echo "=== Benchmark Complete ==="
echo "    Files processed : $c2obra_n / $total_files"
echo "    Skipped         : $skipped"
printf "    %-12s  avg coverage: %6s%%  avg time: %6sms\n" "C²oBra"   "$AVG_C2OBRA"   "$AVG_C2OBRA_MS"
printf "    %-12s  avg coverage: %6s%%  avg time: %6sms\n" "TestCoCa"  "$AVG_TESTCOCA" "$AVG_TESTCOCA_MS"
printf "    %-12s  avg coverage: %6s%%  avg time: %6sms\n" "TestCov"   "$AVG_TESTCOV"  "$AVG_TESTCOV_MS"
echo "========================================================"
echo "✅ CSV saved → $CSV"