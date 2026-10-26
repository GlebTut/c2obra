#ifdef GCOV
extern void __gcov_dump(void);
#endif

int f(int v) {
  switch (v) {
    case 1:
    
goto Goal_1;
Goal_1:;
case 2: 
goto Goal_2;
Goal_2:;
return 5;
    case 3: 
goto Goal_3;
Goal_3:;
return 6;
  }
  return 0;
}
int main(void) { f(1); f(3); return 0; }
