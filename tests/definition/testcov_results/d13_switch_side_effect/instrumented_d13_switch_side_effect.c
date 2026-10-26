#ifdef GCOV
extern void __gcov_dump(void);
#endif

int main(void) {
  int i = 0;
  switch (i++) {
    case 0: 
goto Goal_1;
Goal_1:;
break;
    case 1: 
goto Goal_2;
Goal_2:;
break;
  }
  return i;
}
