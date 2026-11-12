// Implementation of C²oBra runtime library
// Provides coverage data collection and JSON output generation

#include "cov_runtime.h"
#include <stdio.h>
#include <signal.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

// Global array that stores hit counts
unsigned long long branch_counters[MAX_BRANCHES] = {0};

// Called by cover() for an id beyond MAX_BRANCHES (the header has no stdio)
// The condition was evaluated once by the caller: it is returned unchanged.
int __c2obra_cover_out_of_bounds(int branch_id, int value) {
    // once per run: a missing -DMAX_BRANCHES can hit this on every call
    static int warned = 0;
    if (!warned) {
        warned = 1;
        fprintf(stderr, "cover(): branch_id %d out of bounds (MAX_BRANCHES=%d): coverage of ids "
                        "beyond it is not recorded; compile with -DMAX_BRANCHES=<BRANCH_COUNTERS "
                        "printed by instrument.py>\n", branch_id, MAX_BRANCHES);
    }
    return value;
}

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
            fprintf(f, "    {\"id\": %d, \"true\": %llu, \"false\": %llu}",
                i / 2 + 1,
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

// Signal handler: fires on SIGTERM (soft kill)
static void signal_handler_soft(int sig) {
    dump_coverage();
    _exit(1);
}

// CPU-limit handler (SIGXCPU): dump, then die by the signal, so that run_tests.py sees a
// negative exit code (not a normal exit 1) and does not report the run as a pass
static void signal_handler_cpu(int sig) {
    dump_coverage();
    struct rlimit nocore = {0, 0};
    setrlimit(RLIMIT_CORE, &nocore);    // no core file for a resource limit
    signal(sig, SIG_DFL);
    raise(sig);
}

// Crash handler: fires on SIGSEGV, SIGABRT, SIGFPE
// Re-raises the signal after dumping so run_tests.py sees a negative exit code
static void signal_handler_crash(int sig) {
    dump_coverage();
    signal(sig, SIG_DFL);   // restore default so re-raise actually terminates
    raise(sig);             // re-raise → run_tests.py sees exit_code < 0 → "crash"
}

// Constructor: runs before main() — installs signal handlers
__attribute__((constructor))
void install_signal_handlers(void) {
    // Alternate stack: on a stack overflow the SIGSEGV handler cannot run on the full stack
    static char alt_stack[64 * 1024];
    stack_t ss;
    ss.ss_sp = alt_stack;
    ss.ss_size = sizeof alt_stack;
    ss.ss_flags = 0;
    int have_alt = (sigaltstack(&ss, NULL) == 0);

    signal(SIGXCPU, signal_handler_cpu);
    signal(SIGTERM, signal_handler_soft);
    signal(SIGABRT, signal_handler_crash);
    signal(SIGFPE,  signal_handler_crash);
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = signal_handler_crash;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = have_alt ? SA_ONSTACK : 0;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS,  &sa, NULL);
}
