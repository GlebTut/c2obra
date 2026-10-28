/* Driver for c06_macro_loop_keyword.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("r(0) = %d\n", r(0));
    printf("r(3) = %d\n", r(3));
    printf("r(10) = %d\n", r(10));
    return 0;
}
