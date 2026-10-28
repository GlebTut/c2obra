/* Driver for c10_include_header.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("v(-4) = %d\n", v(-4));
    printf("v(0) = %d\n", v(0));
    printf("v(6) = %d\n", v(6));
    return 0;
}
