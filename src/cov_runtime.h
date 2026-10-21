// Header file for C²oBra runtime library
// Provides the cover() macro and coverage tracking functionality
//
// No system headers: instrumented files #include this first, and a preprocessed (.i) program
// already contains its own copy of glibc's types. Including <stdint.h> or <stdio.h> here again
// redefines them (e.g. typedef struct { int __val[2]; } __fsid_t: two anonymous structs are
// different types), or clashes with a program's own uint64_t. Only built-in C types are used.

#ifndef COV_RUNTIME_H
#define COV_RUNTIME_H

#ifndef MAX_BRANCHES
// Max number of branches (branch uses 2 counters (true/false), so we can track up to 32,768 branches)
#define MAX_BRANCHES 65536
#endif

// Array for storing hit counts for each branch (unsigned long long: 64 bits on ILP32 and LP64)
extern unsigned long long branch_counters[MAX_BRANCHES];

// Reports a branch id that does not fit in branch_counters (cov_runtime.c); returns 0
int __c2obra_cover_out_of_bounds(int branch_id);

// cover() macro - wraps branch conditions to track true/false paths
#define cover(expr, branch_id) \
    (((branch_id) - 1) * 2 + 1 < MAX_BRANCHES \
        ? ((expr) ? (branch_counters[((branch_id) - 1) * 2]++, 1) \
                  : (branch_counters[((branch_id) - 1) * 2 + 1]++, 0)) \
        : __c2obra_cover_out_of_bounds(branch_id))

// dump_coverage() - writes coverage data to coverage.json
void dump_coverage(void);

#endif
/* Safe defaults for SV-COMP benchmark constants */
#ifndef LARGE_INT
#define LARGE_INT 1000000
#endif
