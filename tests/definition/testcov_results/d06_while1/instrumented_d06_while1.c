#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int x) {
  int i = 0;
  while (1) {
goto Goal_1;
Goal_1:;

    if (++i > x) {
goto Goal_3;
Goal_3:;
 break;
}
   else { 
goto Goal_4;
Goal_4:;
}}
  
goto Goal_2;
Goal_2:;
return i;
}
int main(void) { f(2); f(0); return 0; }
