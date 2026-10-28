/* Driver for c12_splices_comments.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("x(0) = %d\n", x(0));
    printf("x(1) = %d\n", x(1));
    printf("x(5) = %d\n", x(5));
    return 0;
}
