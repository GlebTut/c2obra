// Header file for C Testing Coverage Tool runtime library
// Provides the cover() macro and coverage tracking functionality

#ifndef COV_RUNTIME_H
#define COV_RUNTIME_H

#include <stdint.h>

// Max number of branches (branch uses 2 counters (true/false), so we can track up to 32,768 branches)
#define MAX_BRANCHES 65536

// Array for storing hit counts for each branch
extern uint64_t branch_counters[MAX_BRANCHES];

// cover() macro - wraps branch conditions to track true/false paths
#define cover(expr, branch_id) \
    ((expr) ? (branch_counters[(branch_id) * 2]++, 1) \
            : (branch_counters[(branch_id) * 2 + 1]++, 0))

// dump_coverage() - writes coverage data to coverage.json
void dump_coverage(void);

#endif 