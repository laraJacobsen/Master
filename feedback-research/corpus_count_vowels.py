# 17-case corpus for the count_vowels lecture question -- second exercise added to grow the
# eval corpus beyond is_palindrome alone (see hint-taxonomy-draft.md open question 4). Hand-written
# the same way corpus.py was, prioritizing the verdict/error_type cells that showed real signal in
# the 2026-09-15 simulated-student runs: wrong_answer, AttributeError, IndexError,
# ModuleNotFoundError, TypeError, and the bounded_loop family (timeout/oom/output_limit_exceeded).
# NameError, RecursionError, EOFError, KeyError, and rejected are deliberately NOT re-covered here
# -- they weren't priorities and don't arise naturally from this problem's shape.
#
# Reference correct behavior: count_vowels(s) -> number of vowels (a/e/i/o/u, case-insensitive) in
# s. 'y' is not a vowel.
#
# Test input chosen (2026-09-15) to actually trip all three wrong_answer bugs below -- verified by
# hand: has an uppercase vowel ('I', trips the forgot-.lower() bug), has a 'y' (trips the
# y-counted-as-vowel bug), and ends on a vowel ('e', trips the off-by-one-skips-last-char bug).
# "Hello World" was considered first and rejected: no uppercase vowel, no 'y', doesn't end on a
# vowel -- all three bugs would have silently passed instead of failing as intended.

TEST_INPUT = "Ivy is Cute"
EXPECTED_OUTPUT = "4"
EXPECTED_FUNCTION_NAME = "count_vowels"
PROBLEM_STATEMENT = (
    "Write a function count_vowels(s) that returns the number of vowels (a, e, i, o, u, "
    "case-insensitive) in s. 'y' is not a vowel. Read one line from stdin, call count_vowels on "
    "it, and print the result."
)

CASES = [
    dict(
        id="01_correct_clean",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="02_correct_with_debug_prints",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def count_vowels(s):
    t = s.lower()
    print("DEBUG: normalized =", t)
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    print("DEBUG: count so far =", count)
    return count

s = input()
result = count_vowels(s)
print("DEBUG: result computed")
print(result)
''',
    ),
    dict(
        id="03_wrong_case_sensitive",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def count_vowels(s):
    vowels = "aeiou"  # forgot to lowercase s first
    count = 0
    for ch in s:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="04_wrong_y_counted",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiouy"  # bug: y isn't a vowel
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="05_wrong_off_by_one",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for i in range(len(t) - 1):  # off-by-one: skips the last character
        if t[i] in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="06_syntax_error",
        expected_verdict="syntax_error",
        expected_error_type=None,
        code='''def count_vowels(s)
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="07_function_not_found",
        expected_verdict="function_not_found",
        expected_error_type=None,
        code='''def vowel_count(s):  # wrong function name
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="08_attribute_error_typo",
        expected_verdict="runtime_error",
        expected_error_type="AttributeError",
        code='''def count_vowels(s):
    t = s.lowerr()  # typo'd method name
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="09_attribute_error_bogus_method",
        expected_verdict="runtime_error",
        expected_error_type="AttributeError",
        code='''def count_vowels(s):
    return s.strip().Vowels()  # no such method on str

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="10_index_error_read_ahead",
        expected_verdict="runtime_error",
        expected_error_type="IndexError",
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for i in range(len(t)):
        if t[i + 1] in vowels:  # reads one index ahead, overruns at the end
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="11_index_error_extra_iteration",
        expected_verdict="runtime_error",
        expected_error_type="IndexError",
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for i in range(len(t) + 1):  # one extra iteration past the last valid index
        if t[i] in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="12_type_error_str_int",
        expected_verdict="runtime_error",
        expected_error_type="TypeError",
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = "0"  # bug: string instead of int
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="13_wrong_signature",
        expected_verdict="runtime_error",
        expected_error_type="TypeError",
        code='''def count_vowels(s, min_length):  # extra required arg
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))  # missing required positional arg
''',
    ),
    dict(
        id="14_disallowed_import",
        expected_verdict="runtime_error",
        expected_error_type="ModuleNotFoundError",
        code='''from textblob import TextBlob  # not part of the taught standard library

def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="15_timeout_missing_increment",
        expected_verdict="timeout",
        expected_error_type=None,
        code='''def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    i = 0
    while i < len(t):
        if t[i] in vowels:
            count += 1
        # forgot i += 1 -> infinite loop
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="16_oom_growing_loop",
        expected_verdict="oom",
        expected_error_type=None,
        code='''def count_vowels(s):
    debug_log = []
    while True:
        debug_log.append("x" * 1000000)  # unbounded growth, never breaks
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
    dict(
        id="17_output_flood",
        expected_verdict="output_limit_exceeded",
        expected_error_type=None,
        code='''def count_vowels(s):
    while True:
        print("checking...")  # debug print left in an unbounded loop
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))
''',
    ),
]
