/* while(1): a constant condition. The false edge can never be taken. */
int f(int x) {
  int i = 0;
  while (1) {                  /* decision 1: false edge infeasible */
    if (++i > x) break;        /* decision 2 */
  }
  return i;
}
int main(void) { f(2); f(0); return 0; }
