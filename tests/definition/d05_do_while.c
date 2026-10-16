/* do-while: the body runs once, then the condition decides: repeat (true) or exit (false). */
int both(int n)      { do { n--; } while (n > 0); return n; }
int only_exit(int n) { do { n--; } while (n > 0); return n; }
int main(void) { both(3); only_exit(1); return 0; }
