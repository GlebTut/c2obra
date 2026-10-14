/* One decision, three conditions: matters for gcov/LLVM branch counts and MC/DC. */
int z(int a, int b, int c) {
  if ((a && b) || c)   // E: if
    return 1;
  return 0;
}
