/* Code removed by the preprocessor must not be counted as a branch. */
int k(int a) {
#if 0
  if (a == 42) return 7;
  while (a) a--;
#endif
  return a > 3 ? 1 : 0; // E: ?:
}
