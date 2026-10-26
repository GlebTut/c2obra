#ifdef GCOV
extern void __gcov_dump(void);
#endif

int both(int n) { do { n--; } while (n > 0);
goto Goal_1;
Goal_1:;
 return n; }
int only_exit(int n) { do { n--; } while (n > 0);
goto Goal_2;
Goal_2:;
 return n; }
int main(void) { both(3); only_exit(1); return 0; }
