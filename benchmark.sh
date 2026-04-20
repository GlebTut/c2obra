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

if [ -f "${SCRIPT_DIR}/venv/bin/activate" ]; then
    source "${SCRIPT_DIR}/venv/bin/activate"
fi
export PATH="${SCRIPT_DIR}/venv/bin:$PATH"

mkdir -p "$OUTPUT_DIR"

INTERRUPTED=0
trap 'echo -e "\n⚠️  Interrupted — CSV saved so far."; INTERRUPTED=1' INT

# Write CSV header only if starting fresh
if [ ! -f "$CSV" ]; then
    echo "file,c2obra_pct,testcoca_pct,testcov_pct,c2obra_covered,c2obra_total,notes" > "$CSV"
fi

c2obra_sum=0; testcoca_sum=0; testcov_sum=0
c2obra_n=0;  testcoca_n=0;   testcov_n=0
skipped=0

add_float() { python3 -c "print($1 + $2)" 2>/dev/null || echo "$1"; }

total_files=$(find "$TEST_DIR" -maxdepth 1 -name "*.c" | wc -l)
echo "=== C²oBra vs TestCoCa vs TestCov Benchmark: $total_files files ==="
echo "    CPU: ${CPU}s | Memory: ${MEM}MB"
echo "    CSV: $CSV"
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

    # Resume: skip if already recorded
    if grep -q "^${BASE}\.c," "$CSV" 2>/dev/null; then
        echo "SKIP"
        skipped=$((skipped+1))
        continue
    fi

    NOTES=""
    C2OBRA_PCT="N/A"; TESTCOCA_PCT="N/A"; TESTCOV_PCT="N/A"
    COV_COVERED="N/A"; COV_TOTAL="N/A"

    # ── 1. C²oBra ─────────────────────────────────────────────────────────
    if ( cd "${SCRIPT_DIR}" && \
         bash "${SCRIPT_DIR}/c2obra.sh" "$SRC" --cpu "$CPU" --memory "$MEM" \
         > "${FILE_OUT}/c2obra.log" 2>&1 ); then
        JSON="${SCRIPT_DIR}/output/${BASE}_inst_coverage.json"
        if [ -f "$JSON" ]; then
            read C2OBRA_PCT COV_COVERED COV_TOTAL < <(python3 -c "
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
            skipped=$((skipped+1))
        fi
    else
        NOTES="c2obra:exit$?"
        skipped=$((skipped+1))
    fi

    SUITE_DIR="${SIKRAKEN_OUT}/${BASE}/test-suite"

    # ── 2. TestCoCa ───────────────────────────────────────────────────────
    TESTCOCA_OUT="${FILE_OUT}/testcoca_out"
    mkdir -p "$TESTCOCA_OUT"

    if [ -f "$TESTCOCA_PY" ] && [ -d "$SUITE_DIR" ]; then
        if python3 "$TESTCOCA_PY" \
            --input_file "$SRC" \
            --test_suite "$SUITE_DIR" \
            --output_dir "$TESTCOCA_OUT" \
            > "${FILE_OUT}/testcoca.log" 2>&1; then
            RESULT_JSON="${TESTCOCA_OUT}/result.json"
            if [ -f "$RESULT_JSON" ]; then
                TESTCOCA_PCT=$(python3 -c "
import json
try:
    d = json.load(open('$RESULT_JSON'))
    v = float(d.get('coverage', 'N/A'))
    print(round(v * 100, 1))
except:
    print('N/A')
" 2>/dev/null)
            else
                NOTES="$NOTES testcoca:no_json"
            fi
        else
            NOTES="$NOTES testcoca:exit$?"
        fi
    elif [ ! -d "$SUITE_DIR" ]; then
        NOTES="$NOTES testcoca:no_suite"
    fi

    # ── 3. TestCov ────────────────────────────────────────────────────────
    TESTCOV_OUT="${FILE_OUT}/testcov_out"
    mkdir -p "$TESTCOV_OUT"

    if [ -f "$TESTCOV_BIN" ] && [ -d "$SUITE_DIR" ]; then
        SUITE_ZIP="${FILE_OUT}/test-suite.zip"
        if [ ! -f "$SUITE_ZIP" ]; then
            (cd "$(dirname "$SUITE_DIR")" && zip -qr "$SUITE_ZIP" "$(basename "$SUITE_DIR")")
        fi
        if "$TESTCOV_BIN" \
            --no-isolation \
            --no-runexec \
            --output "$TESTCOV_OUT" \
            --goal "$TESTCOV_GOAL" \
            --test-suite "$SUITE_ZIP" \
            "$SRC" > "${FILE_OUT}/testcov.log" 2>&1; then
            TESTCOV_PCT=$(grep -oP 'Coverage:\s*\K[0-9]+(\.[0-9]+)?' "${FILE_OUT}/testcov.log" | tail -1 || echo "N/A")
        else
            NOTES="$NOTES testcov:exit$?"
        fi
    elif [ ! -d "$SUITE_DIR" ]; then
        NOTES="$NOTES testcov:no_suite"
    fi

    # ── 4. Write CSV ──────────────────────────────────────────────────────
    echo "${BASE}.c,${C2OBRA_PCT},${TESTCOCA_PCT},${TESTCOV_PCT},${COV_COVERED},${COV_TOTAL},${NOTES# }" >> "$CSV"

    # ── 5. Accumulate ─────────────────────────────────────────────────────
    if [[ "$C2OBRA_PCT"   =~ ^[0-9] ]]; then c2obra_sum=$(add_float "$c2obra_sum" "$C2OBRA_PCT"); c2obra_n=$((c2obra_n+1)); fi
    if [[ "$TESTCOCA_PCT" =~ ^[0-9] ]]; then testcoca_sum=$(add_float "$testcoca_sum" "$TESTCOCA_PCT"); testcoca_n=$((testcoca_n+1)); fi
    if [[ "$TESTCOV_PCT"  =~ ^[0-9] ]]; then testcov_sum=$(add_float "$testcov_sum" "$TESTCOV_PCT"); testcov_n=$((testcov_n+1)); fi

    printf "C²oBra:%6s%% | TestCoCa:%6s%% | TestCov:%6s%%\n" "$C2OBRA_PCT" "$TESTCOCA_PCT" "$TESTCOV_PCT"
done

# ── Averages ──────────────────────────────────────────────────────────────────
avg() { [ "$2" -gt 0 ] && python3 -c "print(round($1/$2,2))" 2>/dev/null || echo "N/A"; }
AVG_C2OBRA=$(avg   "$c2obra_sum"   "$c2obra_n")
AVG_TESTCOCA=$(avg "$testcoca_sum" "$testcoca_n")
AVG_TESTCOV=$(avg  "$testcov_sum"  "$testcov_n")

echo "AVERAGE,${AVG_C2OBRA},${AVG_TESTCOCA},${AVG_TESTCOV},,,processed=${c2obra_n} skipped=${skipped}" >> "$CSV"

echo ""
echo "========================================"
echo "=== Benchmark Complete ==="
echo "    Files processed : $c2obra_n / $total_files"
echo "    Skipped         : $skipped"
echo "    C²oBra avg      : ${AVG_C2OBRA}%"
echo "    TestCoCa avg    : ${AVG_TESTCOCA}%"
echo "    TestCov avg     : ${AVG_TESTCOV}%"
echo "========================================"
echo "✅ CSV saved → $CSV"