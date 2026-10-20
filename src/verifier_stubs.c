/*
 * verifier_stubs.c — Stub implementations of SV-COMP __VERIFIER_nondet_*
 * functions for local testing without a formal verifier.
 *
 * Source: adapted from the SV-COMP competition infrastructure stubs used by
 * testcov and TestCoCa tools. See:
 *   https://sv-comp.sosy-lab.org/
 *   https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks
 *
 * Every nondet stub reads the next whitespace-separated token of test_input.txt, which
 * run_tests.py writes from the <input> elements of a Sikraken test-suite XML, one value per
 * nondet call, in call order. Sikraken writes plain decimals (se_write_tests_testcomp.pl,
 * printf %w), floats in Prolog form (e.g. 6.86063887290973e+18).
 *   - signed types:   strtoll, then cast to the type
 *   - unsigned types: strtoull, then cast ("-1" gives all ones, as C conversion does)
 *   - float/double:   strtod, plus Prolog's <num>Inf, -<num>Inf, <num>NaN and inf/nan
 *   - a token that is not fully a number: warning on stderr, value 0 (the token is used up)
 *   - no more tokens (EOF), or no test_input.txt: value 0, as before
 * Which functions exist and which C type each has follows Sikraken's table
 * is_verifier_input_function/2 (SymbolicExecutor/se_symbolically_interpret.pl); the types
 * Sikraken rejects there (pointer, pchar, int128, uint128, loff_t, sector_t, pthread_t) have
 * no stub. __VERIFIER_nondet_memory is not in that table: it zero-fills and reads no input.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <unistd.h>
#include <stddef.h>

// From cov_runtime.c
extern void dump_coverage(void);

static FILE *input_file = NULL;

static void open_input() {
    if (!input_file) {
        input_file = fopen("test_input.txt", "r");
        if (!input_file) {
            fprintf(stderr, "[Stubs] Warning: no test_input.txt, using defaults\n");
        }
    }
}

// Next whitespace-separated token into buf; 0 if there is none (no file, or EOF).
static int next_token(char *buf, size_t size) {
    char fmt[16];
    open_input();
    if (!input_file) return 0;
    snprintf(fmt, sizeof fmt, "%%%zus", size - 1);
    return fscanf(input_file, fmt, buf) == 1;
}

static void bad_token(const char *fn, const char *tok) {
    fprintf(stderr, "c2obra: %s: input '%s' is not a number, using 0\n", fn, tok);
}

static long long read_signed(const char *fn) {
    char tok[128], *end;
    if (!next_token(tok, sizeof tok)) return 0;
    long long v = strtoll(tok, &end, 10);
    if (end == tok || *end != '\0') { bad_token(fn, tok); return 0; }
    return v;
}

static unsigned long long read_unsigned(const char *fn) {
    char tok[128], *end;
    if (!next_token(tok, sizeof tok)) return 0;
    unsigned long long v = strtoull(tok, &end, 10);
    if (end == tok || *end != '\0') { bad_token(fn, tok); return 0; }
    return v;
}

// Prolog prints a double with about 15 significant digits (e.g. 6.86063887290973e+18), so the
// value read here can differ in the last bits from the one Sikraken reasoned about.
static double read_floating(const char *fn) {
    char tok[128], *end;
    if (!next_token(tok, sizeof tok)) return 0.0;
    size_t n = strlen(tok);
    if (n > 3 && strcmp(tok + n - 3, "Inf") == 0)          // Prolog: 1.0Inf, -1.0Inf
        return tok[0] == '-' ? -INFINITY : INFINITY;
    if (n > 3 && strcmp(tok + n - 3, "NaN") == 0)          // Prolog: 1.5NaN
        return NAN;
    double v = strtod(tok, &end);                          // also accepts inf, nan
    if (end == tok || *end != '\0') { bad_token(fn, tok); return 0.0; }
    return v;
}

int __VERIFIER_nondet_int(void) { return (int)read_signed("__VERIFIER_nondet_int"); }

int __VERIFIER_nondet_bool(void) { return read_signed("__VERIFIER_nondet_bool") != 0; }

void __VERIFIER_error(void) {
    dump_coverage();
    exit(1);
}

void reach_error(void) {
    dump_coverage();
    exit(1);
}

void __VERIFIER_assume(int cond) {
    if (!cond) exit(0);         // ← single definition, exit cleanly
}

__attribute__((weak)) void __VERIFIER_assert(int cond) {
    if (!cond) { __VERIFIER_error(); }
}

// Loop acceleration variables (not functions!)
int __VERIFIER_LA_iterations0 = 0;
int __VERIFIER_LA_old_tmp0    = 0;
int __VERIFIER_LA_tmp0        = 0;

char __VERIFIER_nondet_char(void) { return (char)read_signed("__VERIFIER_nondet_char"); }

short __VERIFIER_nondet_short(void) { return (short)read_signed("__VERIFIER_nondet_short"); }

long __VERIFIER_nondet_long(void) { return (long)read_signed("__VERIFIER_nondet_long"); }

long long __VERIFIER_nondet_longlong(void) { return read_signed("__VERIFIER_nondet_longlong"); }

unsigned char __VERIFIER_nondet_uchar(void) {
    return (unsigned char)read_unsigned("__VERIFIER_nondet_uchar");
}

unsigned short __VERIFIER_nondet_ushort(void) {
    return (unsigned short)read_unsigned("__VERIFIER_nondet_ushort");
}

unsigned int __VERIFIER_nondet_uint(void) {
    return (unsigned int)read_unsigned("__VERIFIER_nondet_uint");
}

unsigned int __VERIFIER_nondet_unsigned(void) {
    return (unsigned int)read_unsigned("__VERIFIER_nondet_unsigned");
}

unsigned int __VERIFIER_nondet_u32(void) {
    return (unsigned int)read_unsigned("__VERIFIER_nondet_u32");
}

unsigned long __VERIFIER_nondet_ulong(void) {
    return (unsigned long)read_unsigned("__VERIFIER_nondet_ulong");
}

unsigned long long __VERIFIER_nondet_ulonglong(void) {
    return read_unsigned("__VERIFIER_nondet_ulonglong");
}

size_t __VERIFIER_nondet_size_t(void) {
    return (size_t)read_unsigned("__VERIFIER_nondet_size_t");
}

float __VERIFIER_nondet_float(void) { return (float)read_floating("__VERIFIER_nondet_float"); }

double __VERIFIER_nondet_double(void) { return read_floating("__VERIFIER_nondet_double"); }

// Not an input function for Sikraken (no <input> is written for it): zero-fill, read nothing.
void __VERIFIER_nondet_memory(void *dst, size_t size) {
    static int warned = 0;
    if (!warned) {
        fprintf(stderr, "c2obra: __VERIFIER_nondet_memory zero-filled, no input read\n");
        warned = 1;
    }
    memset(dst, 0, size);
}
