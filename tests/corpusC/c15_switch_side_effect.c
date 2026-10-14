/* Switch expression with a side effect: it must be evaluated exactly once. */
#include <stdio.h>
static int calls = 0;
static int next(void) { return ++calls; }
static int pick(int *i) {
  switch ((*i)++) {            // E: switch
  case 0: return 100;
  case 1: return 101;
  default: return 199;
  }
}
int main(void) {
  int r, i = 0;
  switch (next()) {            // E: switch
  case 1: r = 10; break;
  case 2: r = 20; break;
  default: r = 30; break;
  }
  int a = pick(&i), b = pick(&i), c = pick(&i);
  printf("calls=%d r=%d picks=%d,%d,%d i=%d\n", calls, r, a, b, c, i);
  return 0;
}
