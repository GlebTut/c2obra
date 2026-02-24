#include <stdio.h>
#include <stdlib.h>

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