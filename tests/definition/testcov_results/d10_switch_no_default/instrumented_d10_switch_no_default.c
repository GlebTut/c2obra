#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int v) {
  switch (v) {
    case 1: 
goto Goal_1;
Goal_1:;
return 10;
    case 2: 
goto Goal_2;
Goal_2:;
return 20;
  }
  return 0;
}
int main(void) { f(1); f(2); return 0; }
