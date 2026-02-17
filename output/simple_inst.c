#include "cov_runtime.h"

#include <stdio.h>

/*
Simple Test file with if and for statement
*/

int main() {
    int x = 5;
    
    if (cover(x > 0, 2)) {
        printf("positive\n");
    }
    
    for (int i = 0; i < 10; i++) {
        printf("%d\n", i);
    }
    
    return 0;
}
