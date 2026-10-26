#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int a, int b, int c) {
  if ((a && b) || c) {
goto Goal_1;
Goal_1:;
 return 1;
}
   else { 
goto Goal_2;
Goal_2:;
}return 0;
}
int main(void) { f(1, 1, 0); f(0, 0, 0); return 0; }
