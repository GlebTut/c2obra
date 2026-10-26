#ifdef GCOV
extern void __gcov_dump(void);
#endif

int both(int n) { int s = 0; while (n > 0) {
goto Goal_1;
Goal_1:;
 s += n; n--; } 
goto Goal_2;
Goal_2:;
return s; }
int only_exit(int n) { int s = 0; while (n > 0) {
goto Goal_3;
Goal_3:;
 s += n; n--; } 
goto Goal_4;
Goal_4:;
return s; }
int main(void) { both(0); both(2); only_exit(0); return 0; }
