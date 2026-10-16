/* ?: is a decision with 2 edges. */
int both(int x)      { return x > 0 ? 1 : -1; }
int only_true(int x) { return x > 0 ? 1 : -1; }
int main(void) { both(1); both(-1); only_true(1); return 0; }
