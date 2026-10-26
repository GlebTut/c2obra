#ifdef GCOV
extern void __gcov_dump(void);
#endif

int both(int x) { if (x > 0) {
goto Goal_1;
Goal_1:;
 return 1; 
} else { 
goto Goal_2;
Goal_2:;
}return 0; }
int only_true(int x) { if (x > 0) {
goto Goal_3;
Goal_3:;
 return 1; 
} else { 
goto Goal_4;
Goal_4:;
}return 0; }
int main(void) { both(1); both(-1); only_true(1); return 0; }
