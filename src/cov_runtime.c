// Implementation of C Testing Coverage Tool runtime library
// Provides coverage data collection and JSON output generation

#include "cov_runtime.h"
#include <stdio.h>
#include <inttypes.h>
#include <signal.h>
#include <unistd.h> 
#include <stdlib.h>

// Global array that stores hit counts
uint64_t branch_counters[MAX_BRANCHES] = {0};

// Guard against double-write (e.g. SIGXCPU fires then destructor also runs)
static volatile int coverage_written = 0;

// dump_coverage() - Writes coverage data to coverage.json file
void dump_coverage(void) {
    if (coverage_written) return;
    coverage_written = 1;

    const char *out_path = getenv("COVERAGE_OUTPUT");
    if (!out_path) out_path = "coverage.json";
    FILE* f = fopen(out_path, "w");
    if (!f) {
        fprintf(stderr, "Error: Could not create %s\n", out_path);
        return;
    }

    fprintf(f, "{\n  \"branches\": [\n");

    int first = 1;
    for (int i = 0; i < MAX_BRANCHES; i += 2) {
        if (branch_counters[i] > 0 || branch_counters[i+1] > 0) {
            if (!first) fprintf(f, ",\n");
            fprintf(f, "    {\"id\": %d, \"true\": %" PRIu64 ", \"false\": %" PRIu64 "}",
                i / 2,
                branch_counters[i],
                branch_counters[i + 1]
            );
            first = 0;
        }
    }

    if (fprintf(f, "\n  ]\n}\n") < 0) {
        fprintf(stderr, "Error: Failed to write coverage.json — disk full?\n");
    }

    fclose(f);
    fprintf(stderr, "[Coverage] Wrote coverage data to %s\n", out_path);
}

// Destructor: fires on normal exit() and __VERIFIER_error → exit()
__attribute__((destructor))
void dump_coverage_destructor(void) {
    dump_coverage();
}

// Signal handler: fires on SIGXCPU (CPU limit) and SIGTERM
// Called just before the kernel sends SIGKILL — last chance to flush
static void signal_handler(int sig) {
    dump_coverage();
    _exit(1);
}

// Constructor: runs before main() — installs signal handlers
__attribute__((constructor))
void install_signal_handlers(void) {
    signal(SIGXCPU, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGABRT, signal_handler);  // ← catches abort()
}
