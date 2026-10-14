/* Ternaries that only exist after macro expansion, two on one line. */
#define MAX(a, b) ((a) > (b) ? (a) : (b))
int t(int a, int b, int c) {
  int x = MAX(MAX(a, b), c);   // E: ?: ?: ?:  (inner MAX is pasted into both arms: 3 decisions after expansion)
  int y = MAX(a, 0);           // E: ?:
  return x + y;
}
