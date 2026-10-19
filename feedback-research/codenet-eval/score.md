# CodeNet classifier eval

3226 submissions scored.
3 C Compile Error skipped as whitespace_only (production rejects these before Judge0).
2 Java Runtime Error skipped as whitespace_only (production rejects these before Judge0).

## Agreement per language and status

| language | CodeNet status | n | agree | reproduced on sample | agree (reproduced) |
|---|---|---:|---:|---:|---:|
| C | Accepted | 200 | 98% | 100% | 98% |
| C | Wrong Answer | 200 | 66% | 68% | 96% |
| C | Runtime Error | 200 | 40% | 60% | 66% |
| C | Compile Error | 197 | 0% | 93% | 0% |
| C | Time Limit Exceeded | 200 | 26% | 74% | 35% |
| C | Memory Limit Exceeded (low n) | 1 | 0% | 0% | - |
| C | WA: Presentation Error | 200 | 67% | 100% | 67% |
| Java | Accepted | 200 | 100% | 100% | 100% |
| Java | Wrong Answer | 200 | 65% | 68% | 95% |
| Java | Runtime Error | 198 | 80% | 88% | 90% |
| Java | Compile Error | 200 | 0% | 99% | 0% |
| Java | Time Limit Exceeded | 134 | 60% | 61% | 99% |
| Java | Memory Limit Exceeded (low n) | 26 | 0% | 27% | 0% |
| Java | WA: Presentation Error | 188 | 80% | 100% | 80% |
| Python | Accepted | 200 | 100% | 100% | 100% |
| Python | Wrong Answer | 200 | 68% | 72% | 94% |
| Python | Runtime Error | 200 | 94% | 95% | 99% |
| Python | Time Limit Exceeded | 108 | 19% | 62% | 30% |
| Python | Memory Limit Exceeded (low n) | 17 | 0% | 12% | 0% |
| Python | WA: Presentation Error | 157 | 64% | 100% | 64% |

## C: CodeNet status x production verdict

| CodeNet status | pass | wrong_answer | runtime_error/Unknown | timeout |
|---|---:|---:|---:|---:|
| Accepted | 196 | 4 |  |  |
| Wrong Answer | 66 | 131 | 3 |  |
| Runtime Error | 84 | 37 | 79 |  |
| Compile Error | 14 | 182 |  | 1 |
| Time Limit Exceeded | 51 | 14 | 83 | 52 |
| Memory Limit Exceeded | 1 |  |  |  |
| WA: Presentation Error | 134 | 66 |  |  |

## Java: CodeNet status x production verdict

| CodeNet status | pass | wrong_answer | runtime_error/Unknown | timeout | oom |
|---|---:|---:|---:|---:|---:|
| Accepted | 199 | 1 |  |  |  |
| Wrong Answer | 70 | 130 |  |  |  |
| Runtime Error | 23 | 13 | 158 |  | 4 |
| Compile Error | 2 | 195 | 3 |  |  |
| Time Limit Exceeded | 52 |  | 1 | 81 |  |
| Memory Limit Exceeded | 19 | 6 |  | 1 |  |
| WA: Presentation Error | 150 | 38 |  |  |  |

## Python: CodeNet status x production verdict

| CodeNet status | pass | wrong_answer | syntax_error | output_limit_exceeded | runtime_error/NameError | runtime_error/TypeError | timeout | runtime_error/ValueError | runtime_error/AttributeError | runtime_error/EOFError | runtime_error/Unknown | runtime_error/ModuleNotFoundError | runtime_error/IndexError |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Accepted | 200 |  |  |  |  |  |  |  |  |  |  |  |  |
| Wrong Answer | 64 | 136 |  |  |  |  |  |  |  |  |  |  |  |
| Runtime Error | 10 | 1 | 89 |  | 29 | 25 |  | 18 | 16 | 5 | 3 | 2 | 2 |
| Time Limit Exceeded | 41 | 2 |  | 45 |  |  | 20 |  |  |  |  |  |  |
| Memory Limit Exceeded | 15 |  |  |  |  |  | 2 |  |  |  |  |  |  |
| WA: Presentation Error | 101 | 56 |  |  |  |  |  |  |  |  |  |  |  |

## What the classifier doesn't recognize yet

Most common last stderr/compile line (digits -> N) where production said runtime_error/Unknown, or where Judge0 reported a compilation error.


**C** (347)

- 69 x `run: line N: N File size limit exceeded(core dumped) ./a.out`
- 66 x `| ^`
- 64 x `run: line N: N Segmentation fault (core dumped) ./a.out`
- 19 x `main.c:N:N: note: each undeclared identifier is reported only once for each function it appears in`
- 19 x `collectN: error: ld returned N exit status`
- 15 x `main.c:N:N: note: include ‘<stdio.h>’ or provide a declaration of ‘printf’`
- 12 x `compilation terminated.`
- 10 x `| ~`
- 8 x `| ;`
- 7 x `| ^~~~`
- 7 x `run: line N: N Floating point exception(core dumped) ./a.out`
- 6 x `| ^~~~~~`

**Java** (360)

- 123 x `N error`
- 106 x `at Main.main(Main.java:N)`
- 74 x `N errors`
- 24 x `Caused by: java.lang.ClassNotFoundException: Main`
- 4 x `Caused by: java.lang.NoClassDefFoundError: pN/Main (wrong name: Main)`
- 3 x `Note: Recompile with -Xlint:unchecked for details.`
- 3 x `Caused by: java.lang.NoClassDefFoundError: practice/Main (wrong name: Main)`
- 3 x `or a JavaFX application class must extend javafx.application.Application`
- 2 x `Caused by: java.lang.NoClassDefFoundError: lesson/Main (wrong name: Main)`
- 1 x `Caused by: java.lang.NoClassDefFoundError: progA/Main (wrong name: Main)`
- 1 x `Caused by: java.lang.NoClassDefFoundError: javaN/Main (wrong name: Main)`
- 1 x `Caused by: java.lang.NoClassDefFoundError: javaprogramming_Class/Main (wrong name: Main)`

**Python** (3)

- 1 x `script.py: error: the following arguments are required: filename`
- 1 x `UnboundLocalError: local variable 'i' referenced before assignment`
- 1 x `FileNotFoundError: [Errno N] No such file or directory: 'inN.txt'`

## Judge0 exit_code values

{None: 3226}
