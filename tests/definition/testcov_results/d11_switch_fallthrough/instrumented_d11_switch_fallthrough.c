#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int v) {
  int r = 0;
  switch (v) {
    case 1: 
goto Goal_1;
Goal_1:;
r += 1;
    case 2: 
goto Goal_2;
Goal_2:;
r += 2; break;
    default: 
goto Goal_3;
Goal_3:;
r = -1;
  }
  return r;
}
int main(void) { f(1); return 0; }
