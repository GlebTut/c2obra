/* Typedef-name vs identifier ambiguity, which a grammar without a symbol table must guess. */
typedef int T;
int y(int a, int b) {
  int T2 = 0;
  if ((T)(a) > b) T2++;          // E: if
  return (T2) ? (T)(b) : a * b;  // E: ?:
}
