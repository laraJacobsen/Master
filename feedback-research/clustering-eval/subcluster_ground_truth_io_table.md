# Wrong-answer sub-clustering: input/output reading aid

Companion to `subcluster_ground_truth_sample.csv`/`.md` -- same 29 submissions, same ids. Each cell is the literal stdout each submission's code actually produced when run against that input (or `ERROR: <ExceptionType>`/`ERROR: Timeout` if it crashed or hung). Nothing here is interpreted or grouped -- compare a row against the **expected** row to spot mismatches, then fill in `bug_group` in the CSV yourself.

## sum-ints

Reference solution: `print(sum(int(x) for x in input().split()))`

| submission_id | input 1: `'1 2 3\n'` | input 2: `'10 20 30 40\n'` | input 3: `'-5 5\n'` | input 4: `'1000000 2000000\n'` |
|---|---|---|---|---|
| **expected** | **6** | **100** | **0** | **3000000** |
| SI-01 | 3 | 60 | -5 | 1000000 |
| SI-02 | 6 | 240000 | -25 | 2000000000000 |
| SI-03 | 5 | 90 | 5 | 2000000 |
| SI-04 | 5 | 99 | -1 | 2999999 |
| SI-05 | 6 | 240000 | -25 | 2000000000000 |
| SI-06 | 1 | 10 | -5 | 1000000 |
| SI-07 | 5 | 99 | -1 | 2999999 |
| SI-08 | 7 | 101 | 1 | 3000001 |
| SI-09 | 3 | 60 | -5 | 1000000 |
| SI-10 | 7 | 101 | 1 | 3000001 |
| SI-11 | 7 | 101 | 1 | 3000001 |
| SI-12 | 1 | 10 | -5 | 1000000 |
| SI-13 | 7 | 101 | 1 | 3000001 |
| SI-14 | 7 | 101 | 1 | 3000001 |
| SI-15 | 3 | 60 | -5 | 1000000 |

## double-it

Reference solution: `print(int(input()) * 2)`

| submission_id | input 1: `'4\n'` | input 2: `'3\n'` | input 3: `'10\n'` |
|---|---|---|---|
| **expected** | **8** | **6** | **20** |
| DI-01 | 44 | 33 | 1010 |
| DI-02 | 44 | 33 | 1010 |
| DI-03 | 6 | 5 | 12 |
| DI-04 | 6 | 5 | 12 |
| DI-05 | 44 | 33 | 1010 |
| DI-06 | 6 | 5 | 12 |
| DI-07 | 44 | 33 | 1010 |
| DI-08 | 6 | 5 | 12 |
| DI-09 | 6 | 5 | 12 |
| DI-10 | 6 | 5 | 12 |
| DI-11 | 9 | 7 | 21 |

## is_palindrome

Reference solution: `def is_palindrome(s):
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
`

| submission_id | input 1: `'Race car\n'` |
|---|---|
| **expected** | **True** |
| PAL-01 | False |
| PAL-02 | False |
| PAL-03 | False |
