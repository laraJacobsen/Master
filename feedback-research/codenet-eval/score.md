# CodeNet classifier eval

3226 submissions scored.
3 C Compile Error skipped as whitespace_only (production rejects these before Judge0).
2 Java Runtime Error skipped as whitespace_only (production rejects these before Judge0).

## Agreement per language and status

| language | CodeNet status | n | agree | reproduced on sample | agree (reproduced) |
|---|---|---:|---:|---:|---:|
| C | Accepted | 200 | 98% | 100% | 98% |
| C | Wrong Answer | 200 | 68% | 70% | 98% |
| C | Runtime Error | 200 | 45% | 60% | 75% |
| C | Compile Error | 197 | 91% | 93% | 97% |
| C | Time Limit Exceeded | 200 | 26% | 75% | 35% |
| C | Memory Limit Exceeded (low n) | 1 | 0% | 0% | - |
| C | WA: Presentation Error | 200 | 67% | 100% | 67% |
| Java | Accepted | 200 | 100% | 100% | 100% |
| Java | Wrong Answer | 200 | 68% | 68% | 99% |
| Java | Runtime Error | 198 | 80% | 88% | 90% |
| Java | Compile Error | 200 | 97% | 99% | 98% |
| Java | Time Limit Exceeded | 134 | 60% | 61% | 99% |
| Java | Memory Limit Exceeded (low n) | 26 | 0% | 27% | 0% |
| Java | WA: Presentation Error | 188 | 79% | 100% | 79% |
| Python | Accepted | 200 | 100% | 100% | 100% |
| Python | Wrong Answer | 200 | 72% | 72% | 100% |
| Python | Runtime Error | 200 | 94% | 95% | 99% |
| Python | Time Limit Exceeded | 108 | 19% | 62% | 30% |
| Python | Memory Limit Exceeded (low n) | 17 | 0% | 12% | 0% |
| Python | WA: Presentation Error | 157 | 64% | 100% | 64% |

## Runtime errors with a specific error type

The agreement table only checks the verdict. A runtime_error's hint depends on its error_type, and `Unknown` gets the generic fallback hint.

| language | runtime_error | specific type | Unknown |
|---|---:|---:|---:|
| C | 99 | 100% | 0 |
| Java | 162 | 100% | 0 |
| Python | 100 | 97% | 3 |

## C: CodeNet status x production verdict

| CodeNet status | pass | wrong_answer | compile_error | runtime_error/SegmentationFault | output_limit_exceeded | timeout | runtime_error/NonZeroExit | runtime_error/FloatingPointException |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Accepted | 196 | 4 |  |  |  |  |  |  |
| Wrong Answer | 60 | 137 |  | 1 | 1 |  |  | 1 |
| Runtime Error | 80 | 27 | 2 | 72 | 1 |  | 12 | 6 |
| Compile Error | 13 | 4 | 179 |  |  | 1 |  |  |
| Time Limit Exceeded | 50 | 15 | 1 | 6 | 75 | 52 |  | 1 |
| Memory Limit Exceeded | 1 |  |  |  |  |  |  |  |
| WA: Presentation Error | 134 | 66 |  |  |  |  |  |  |

## Java: CodeNet status x production verdict

| CodeNet status | pass | compile_error | wrong_answer | timeout | runtime_error/NoSuchElementException | runtime_error/MainNotFound | runtime_error/ArrayIndexOutOfBoundsException | runtime_error/InputMismatchException | runtime_error/ArithmeticException | runtime_error/NumberFormatException | runtime_error/NullPointerException | runtime_error/IndexOutOfBoundsException | oom | runtime_error/IllegalStateException | runtime_error/StringIndexOutOfBoundsException | runtime_error/FileNotFoundException |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Accepted | 199 |  | 1 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| Wrong Answer | 63 | 1 | 136 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| Runtime Error | 23 | 3 | 10 |  | 57 | 53 | 15 | 7 | 6 | 5 | 5 | 5 | 4 | 3 | 1 | 1 |
| Compile Error | 2 | 194 | 1 |  | 2 | 1 |  |  |  |  |  |  |  |  |  |  |
| Time Limit Exceeded | 52 |  |  | 81 | 1 |  |  |  |  |  |  |  |  |  |  |  |
| Memory Limit Exceeded | 19 |  | 6 | 1 |  |  |  |  |  |  |  |  |  |  |  |  |
| WA: Presentation Error | 149 |  | 39 |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Python: CodeNet status x production verdict

| CodeNet status | pass | wrong_answer | syntax_error | output_limit_exceeded | runtime_error/NameError | runtime_error/TypeError | timeout | runtime_error/ValueError | runtime_error/AttributeError | runtime_error/EOFError | runtime_error/Unknown | runtime_error/ModuleNotFoundError | runtime_error/IndexError |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Accepted | 200 |  |  |  |  |  |  |  |  |  |  |  |  |
| Wrong Answer | 56 | 144 |  |  |  |  |  |  |  |  |  |  |  |
| Runtime Error | 10 | 1 | 89 |  | 29 | 25 |  | 18 | 16 | 5 | 3 | 2 | 2 |
| Time Limit Exceeded | 41 | 2 |  | 45 |  |  | 20 |  |  |  |  |  |  |
| Memory Limit Exceeded | 15 |  |  |  |  |  | 2 |  |  |  |  |  |  |
| WA: Presentation Error | 101 | 56 |  |  |  |  |  |  |  |  |  |  |  |

## What the classifier doesn't recognize yet

Most common last stderr/compile line (digits -> N) where production said runtime_error/Unknown, or where Judge0 reported a compilation error.


**C** (182)

- 63 x `| ^`
- 19 x `main.c:N:N: note: each undeclared identifier is reported only once for each function it appears in`
- 19 x `collectN: error: ld returned N exit status`
- 12 x `compilation terminated.`
- 10 x `| ~`
- 8 x `| ;`
- 7 x `main.c:N:N: note: include ‘<stdio.h>’ or provide a declaration of ‘printf’`
- 6 x `| ^~~~~~`
- 5 x `| )`
- 4 x `| ~~`
- 3 x `| ^~~~~`
- 3 x `| ~~~~~~`

**Java** (198)

- 123 x `N error`
- 74 x `N errors`
- 1 x `only showing the first N errors, of N total; use -Xmaxerrs if you would like to see more`

**Python** (3)

- 1 x `script.py: error: the following arguments are required: filename`
- 1 x `UnboundLocalError: local variable 'i' referenced before assignment`
- 1 x `FileNotFoundError: [Errno N] No such file or directory: 'inN.txt'`

## Judge0 exit_code values

{0: 2269, None: 380, 139: 78, 6: 3, 1: 354, 153: 77, 255: 1, 120: 43, 136: 8, 10: 3, 135: 1, 137: 4, 9: 2, 2: 1, 34: 1, 20: 1}
