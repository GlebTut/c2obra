/* Fall-through: f(1) selects ONLY the label "case 1"; the body of case 2 also runs, but the label case 2 was not selected. */
int f(int v) {
  int r = 0;
  switch (v) {
    case 1: r += 1;            /* falls through */
    case 2: r += 2; break;
    default: r = -1;
  }
  return r;
}
int main(void) { f(1); return 0; }
