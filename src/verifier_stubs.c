#include <stdio.h>
#include <stdlib.h>
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

int __VERIFIER_nondet_int(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return val;
}

int __VERIFIER_nondet_bool(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return val != 0;
}

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

// Add to verifier_stubs.c
char __VERIFIER_nondet_char(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return (char)val;
}

unsigned int __VERIFIER_nondet_uint(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return (unsigned int)val;
}

unsigned char __VERIFIER_nondet_uchar(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return (unsigned char)val;
}

short __VERIFIER_nondet_short(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return (short)val;
}

long __VERIFIER_nondet_long(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return (long)val;
}

float __VERIFIER_nondet_float(void) { return 0.0f; }
double __VERIFIER_nondet_double(void) { return 0.0; }

unsigned short __VERIFIER_nondet_ushort(void) {
    open_input();
    int val = 0;
    if (input_file) fscanf(input_file, "%d", &val);
    return (unsigned short)val;
}