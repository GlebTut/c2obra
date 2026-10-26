#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int x) {
  if (x < 0) {
goto Goal_1;
Goal_1:;
 return -1;
  } else if (x == 0) {
goto Goal_2;
Goal_2:;
 return 0;
  } else {
goto Goal_3;
Goal_3:;
 return 1;
}
}
int main(void) { f(-5); f(0); return 0; }
