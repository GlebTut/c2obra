/* Driver for c14_short_circuit.c: a main() appended to a copy of it by tests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("z(1, 1, 0) = %d\n", z(1, 1, 0));
    printf("z(1, 0, 0) = %d\n", z(1, 0, 0));
    printf("z(0, 0, 1) = %d\n", z(0, 0, 1));
    printf("z(0, 1, 0) = %d\n", z(0, 1, 0));
    return 0;
}
