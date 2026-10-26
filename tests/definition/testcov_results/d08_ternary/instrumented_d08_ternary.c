#ifdef GCOV
extern void __gcov_dump(void);
#endif

int both(int x) { return x > 0 ? ({
goto Goal_1;
Goal_1:;
1;}) : ({
goto Goal_2;
Goal_2:;
-1;}); }
int only_true(int x) { return x > 0 ? ({
goto Goal_3;
Goal_3:;
1;}) : ({
goto Goal_4;
Goal_4:;
-1;}); }
int main(void) { both(1); both(-1); only_true(1); return 0; }
