/* Driver for c13_typedef_ambiguity.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("y(2, 1) = %d\n", y(2, 1));
    printf("y(0, 5) = %d\n", y(0, 5));
    printf("y(3, 4) = %d\n", y(3, 4));
    return 0;
}
