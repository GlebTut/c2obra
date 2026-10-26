#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int n) { int s = 0; for (int i = 0; i < n; i++) {
goto Goal_1;
Goal_1:;
 s += i; 
}
goto Goal_2;
Goal_2:;
return s; }
int main(void) { f(3); f(0); return 0; }
