/* if / else if / else: each "if" is its own decision (2 decisions). */
int f(int x) {
  if (x < 0) return -1;        /* decision 1 */
  else if (x == 0) return 0;   /* decision 2 */
  else return 1;
}
int main(void) { f(-5); f(0); return 0; }
