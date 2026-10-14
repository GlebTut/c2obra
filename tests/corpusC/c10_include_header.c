/* Constructs defined in a header: macro used here counts, inline fn in header does not. */
#include "c10_header.h"
int v(int a) {
  if (sgn(a) < 0)   // E: if
    return ABS(a);  // E: ?:
  return a;
}
