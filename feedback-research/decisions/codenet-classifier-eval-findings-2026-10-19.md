# CodeNet classifier eval: findings and the fixes they led to (2026-10-19)

*Written by Claude Code while running the CodeNet evaluation of production's Judge0-result
classifier (`backend/hints.classify_submission()` → `feedback-research/classify.py`), as
the first step towards supporting C and Java alongside Python. Scripts, sample and full
results are in `feedback-research/codenet-eval/`; `score.md` there is the current report.*

## What was run

[IBM Project CodeNet](https://github.com/IBM/Project_CodeNet) has ~14M submissions to
~4,000 judge problems, each labelled with the judge's status. From it:

- **10 AIZU problems**, chosen by `select_problems.py`: intro-course exercises (Print Test
  Cases, Reversing Numbers, GCD, Swapping Two Numbers, ...) with a median accepted Python 3
  solution of ≤300 bytes, and enough submissions in every status. Two data-structure
  problems (Dictionary, Priority Queue) were dropped by hand: their timeouts only happen on
  large hidden inputs.
- **3,231 submissions**: up to 20 per problem × language (C, Java, Python 3) × status
  (Accepted, Wrong Answer, Runtime Error, Compile Error, Time Limit Exceeded, Memory Limit
  Exceeded, Presentation Error), fixed seed (`sample_submissions.py`). AIZU's bare "Python"
  is Python 2 (84% of its accepted submissions fail to compile under Python 3, vs 0% for
  "Python3") and is excluded.
- Each run once through the local Judge0 via production's own `run_test_cases()`, on the
  problem's sample input, with the problem's own limits (`run_judge0.py`), then classified
  exactly as production classifies a graded submission (`score.py`). 5 empty submissions
  were skipped: Judge0 refuses blank source, and production rejects it before Judge0 anyway.

**Main limit of the data:** CodeNet ships only the sample I/O from the problem statement,
not the judges' hidden tests. About a third of Wrong Answer and TLE submissions pass the
sample, because the input that broke them isn't available. `score.py` therefore also
reports agreement over only the submissions whose failure *reproduced* on the sample; that
column is the one that measures the classifier. Memory Limit Exceeded almost never
reproduces (0–27%) and is low-n, so OOM detection is not evaluated by this.

These are competitive-judge submissions, not lecture-hall novices: good for checking the
pipeline across languages, not for claims about what students get wrong.

## Results

Agreement over reproduced submissions, before → after the fixes below:

| | C | Java | Python |
|---|---:|---:|---:|
| Accepted | 98% | 100% | 100% |
| Wrong Answer | 96% → 98% | 95% → 99% | 94% → 100% |
| Runtime Error | 66% | 90% | 99% |
| Compile Error | **0% → 97%** | **0% → 98%** | — (none: Python syntax errors are filed as Runtime Error, and classify as `syntax_error`) |
| Time Limit Exceeded | 35% | 99% | 30% |
| Presentation Error | 67% | 79% | 64% |

Python, the only language the app ships today, agrees with the judge wherever the failure
is visible on the sample. Python's TLE row is mostly `output_limit_exceeded` (45): output
floods that AIZU stopped on time and Judge0 stopped on output size; both are reasonable.

## Fixed (this branch)

1. **Compile errors were graded `wrong_answer`.** `classify.py` reads only stdout/stderr;
   a C/Java compile error is in `compile_output`, with Judge0 status 6. A student would
   have been told their output didn't match. Now `classify_submission()` returns
   `compile_error` for status 6, with its own hint family in `feedback.py` ("read the
   compiler's first error"), and the student's error-output box shows the compiler output.
2. **A failing test could be classified `pass`** (23 cases, all three languages).
   `classify.py` compares only the last printed line, to tolerate debug prints, while
   `run_test_cases()` compares the whole output. A program that printed an extra line
   failed the test but got verdict `pass`: the student saw "0/N tests passed" with no
   hint, and the lecturer dashboard grouped it under **Passing**. The test result is the
   grade, so a failing test is now never `pass` (it becomes `wrong_answer`). Verified in
   the running app: `print("debug")` before a correct solution now gets the wrong-answer
   hint and appears under "Wrong answer" on the dashboard. Note this means classify.py's
   debug-print tolerance never helped in production: the test comparison already failed
   those submissions.
3. **`exit_code` was never requested from Judge0.** Judge0 leaves it out of its default
   response fields, so it was `None` on every result and `classify.py`'s
   `exit_code == 137` OOM check was dead code. `smoke_test.py`'s fake Judge0 returned it
   unasked, which is how this went unnoticed. `judge0_client` now asks for it. Measured
   effect on agreement: none on this sample (the few memory kills also print "Killed",
   which was already caught), but every result now carries a real exit code.

## Still open

- **Presentation Error: only 64–79% pass.** The test comparison strips only the ends of
  the whole output, so a trailing space on any line fails (e.g. `5 4 3 2 1 ` vs
  `5 4 3 2 1`). Whether to ignore trailing whitespace per line is a grading-policy
  decision, not yet taken.
- **C runtime errors → `runtime_error/Unknown`.** The exit codes now available identify
  them without parsing stderr text: 139 segfault (78 here), 153 output file size limit
  (77), 136 floating-point exception (8), 137 killed (4). `classify.py` also only knows
  Python's wording of the output-limit error.
- **Java exceptions → `runtime_error/Unknown`** (158). The exception name is on the
  *first* stderr line (`Exception in thread "main" java.lang.X`); `classify.py` reads the
  last. Separately, ~36 failed only because the class wasn't named `Main` or was in a
  `package`: Java's counterpart to `function_not_found`, worth its own hint.
- **Java needs ≥ ~3 s CPU on this Judge0.** JVM startup alone measured 1.2–2.1 s (CPU
  time is summed across the JVM's threads) and up to ~140 MB, so at AIZU's 1 s / 128 MB
  every Java submission timed out. The eval gives Java +3 s and 256 MB; a Java question
  in the app needs the same headroom.
- **Undefined behaviour in C:** two C submissions gave different output on identical
  runs. A C student can pass on one submission and fail the next with the same code.

C and Java should not be offered in the setup page's language list until the runtime
error items above are done, or their students get generic hints.
