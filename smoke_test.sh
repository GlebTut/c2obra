#!/usr/bin/env bash
# smoke_test.sh — Quick sanity check after install.
# Usage: bash smoke_test.sh
# Expected: 4 branches, 100% coverage (2 branch constructs × 2 edges each)

set -euo pipefail
TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/smoke.c" << 'EOF'
#include <stdio.h>
extern int __VERIFIER_nondet_int(void);

int main(void) {
    int x = __VERIFIER_nondet_int();
    if (x > 0) {
        printf("positive\n");
    } else {
        printf("non-positive\n");
    }

    int i = __VERIFIER_nondet_int();
    if (i % 2 == 0) {
        printf("even\n");
    } else {
        printf("odd\n");
    }
    return 0;
}
EOF

# Generate two test inputs: one positive/even, one negative/odd
mkdir -p "$TMP/suite"
cat > "$TMP/suite/test_input-1.xml" << 'EOF'
<tests><input>4</input><input>2</input></tests>
EOF
cat > "$TMP/suite/test_input-2.xml" << 'EOF'
<tests><input>-1</input><input>3</input></tests>
EOF

echo "=== Smoke Test: instrumenting smoke.c ==="
python3 "$TOOL_DIR/instrument.py" "$TMP/smoke.c" "$TMP/smoke_inst.c"

echo ""
echo "=== Compiling ==="
COUNTERS=$(grep 'BRANCH_COUNTERS=' "$TMP/smoke_inst.c" 2>/dev/null | tail -1 | cut -d= -f2 || echo 4)
gcc -o "$TMP/smoke_bin" "$TMP/smoke_inst.c" "$TOOL_DIR/cov_runtime.c" "$TOOL_DIR/verifier_stubs.c" \
    -I"$TOOL_DIR" -DMAX_BRANCHES="${COUNTERS}" -lm

echo ""
echo "=== Running tests ==="
python3 "$TOOL_DIR/run_tests.py" "$TMP/smoke_bin" "$TMP/suite" "$TMP/smoke_inst_branch_map.json"

echo ""
echo "=== Generating HTML report ==="
python3 "$TOOL_DIR/report.py" "$TMP/smoke_inst_branch_map.json" coverage_report.json smoke_report.html

echo ""
echo "✅ Smoke test passed. Open smoke_report.html to view coverage."
echo "   Expected: 4 branches, 100% coverage."
