/* if without else: 2 decisions x 2 edges (true, false/implicit else). */
int both(int x)      { if (x > 0) return 1; return 0; }   /* decision 1 */
int only_true(int x) { if (x > 0) return 1; return 0; }   /* decision 2 */
int main(void) { both(1); both(-1); only_true(1); return 0; }
