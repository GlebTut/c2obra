/* Stacked labels share one body; each label is its own edge. CONFIRMED 2026-10-16: implicit default counted. */
int f(int v) {
  switch (v) {
    case 1:
    case 2: return 5;
    case 3: return 6;
  }
  return 0;
}
int main(void) { f(1); f(3); return 0; }
