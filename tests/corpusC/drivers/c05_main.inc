/* Driver for c05_flag_dependent.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("m(-1) = %d\n", m(-1));
    printf("m(0) = %d\n", m(0));
    printf("m(5) = %d\n", m(5));
    return 0;
}
