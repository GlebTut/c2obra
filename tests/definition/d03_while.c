/* while: edges = body entered (true), loop exits (false). */
int both(int n)      { int s = 0; while (n > 0) { s += n; n--; } return s; }
int only_exit(int n) { int s = 0; while (n > 0) { s += n; n--; } return s; }
int main(void) { both(0); both(2); only_exit(0); return 0; }
