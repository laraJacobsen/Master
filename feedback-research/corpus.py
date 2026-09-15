# Reconstructed 25-submission corpus for the is_palindrome lecture question.
#
# NOTE: this is a rebuild from the documented spec in lecture-simulation-test-run-findings.md
# and submission-format-and-error-taxonomy.md, not the original corpus.py file (which wasn't
# accessible from this session). It targets the same categories in the same rough proportions.
#
# Reference correct behavior: is_palindrome(s) -> True if s reads the same forwards and
# backwards, ignoring case and spaces. Test input used for every case: "Race car" -> True.

TEST_INPUT = "Race car"
EXPECTED_OUTPUT = "True"
EXPECTED_FUNCTION_NAME = "is_palindrome"
PROBLEM_STATEMENT = (
    "Write a function is_palindrome(s) that returns True if s reads the same forwards and "
    "backwards, ignoring case and spaces, and False otherwise. Read one line from stdin, call "
    "is_palindrome on it, and print the result."
)

# Each entry: id, code (full program: defines is_palindrome, reads stdin, prints result),
# expected_verdict, expected_error_type (None unless verdict == runtime_error)
CASES = [
    dict(
        id="01_correct_clean",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def is_palindrome(s):
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="02_correct_with_debug_prints",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def is_palindrome(s):
    t = s.lower().replace(" ", "")
    print("DEBUG: normalized =", t)
    return t == t[::-1]

s = input()
result = is_palindrome(s)
print("DEBUG: result computed")
print(result)
''',
    ),
    dict(
        id="03_wrong_case_sensitive",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def is_palindrome(s):
    t = s.replace(" ", "")  # forgot to lowercase
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="04_wrong_unstripped_spaces",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def is_palindrome(s):
    t = s.lower()  # forgot to strip spaces
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="05_wrong_off_by_one",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def is_palindrome(s):
    t = s.lower().replace(" ", "")
    n = len(t)
    for i in range(n // 2):
        if t[i] != t[n - i - 2]:  # off-by-one: should be n - i - 1
            return False
    return True

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="06_syntax_error",
        expected_verdict="syntax_error",
        expected_error_type=None,
        code='''def is_palindrome(s)
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="07_indentation_error",
        expected_verdict="syntax_error",
        expected_error_type=None,
        code='''def is_palindrome(s):
t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="08_name_error",
        expected_verdict="runtime_error",
        expected_error_type="NameError",
        code='''def is_palindrome(s):
    t = normalize(s)  # normalize() was never defined
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="09_type_error_str_int",
        expected_verdict="runtime_error",
        expected_error_type="TypeError",
        code='''def is_palindrome(s):
    t = s.lower().replace(" ", "") + 1  # str + int
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="10_index_error",
        expected_verdict="runtime_error",
        expected_error_type="IndexError",
        code='''def is_palindrome(s):
    t = s.lower().replace(" ", "")
    return t[len(t)] == t[0]  # off-the-end index

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="11_attribute_error",
        expected_verdict="runtime_error",
        expected_error_type="AttributeError",
        code='''def is_palindrome(s):
    t = s.lowerr().replace(" ", "")  # typo'd method name
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="12_recursion_error",
        expected_verdict="runtime_error",
        expected_error_type="RecursionError",
        code='''def is_palindrome(s):
    return is_palindrome(s)  # infinite recursion, no base case

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="13_wrong_signature",
        expected_verdict="runtime_error",
        expected_error_type="TypeError",
        code='''def is_palindrome(s, extra_required_arg):
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))  # missing required positional arg
''',
    ),
    dict(
        id="14_function_not_found",
        expected_verdict="function_not_found",
        expected_error_type=None,
        code='''def check_palindrome(s):  # wrong function name
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="15_timeout_missing_increment",
        expected_verdict="timeout",
        expected_error_type=None,
        code='''def is_palindrome(s):
    i = 0
    while i < len(s):
        pass  # forgot to increment i -> infinite loop
    return True

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        # Confirmed against real Judge0: this hits Judge0's own stdout-size cap
        # (OSError: [Errno 27] File too large) and gets killed outright, rather than
        # running until the wall-clock timeout. Originally predicted "timeout" to match
        # the Sep 2 stand-in's 4KB-truncation behavior -- real Judge0 behaves differently,
        # which is exactly the kind of transfer gap this whole exercise was meant to find.
        id="16_output_flood",
        expected_verdict="output_limit_exceeded",
        expected_error_type=None,
        code='''def is_palindrome(s):
    while True:
        print("x" * 1000)
    return True

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        # Per run-judge0-locally.md's own troubleshooting notes: a stray input() call only
        # "hangs until timeout" if stdin is left open-but-unwritten. Feeding stdin via a
        # simple pipe (as both this local test and most Judge0 clients do) closes it after
        # writing, so this becomes an immediate EOFError instead of a hang -- exactly the
        # ambiguity that doc flagged as needing live confirmation against real Judge0.
        id="17_blocking_input_eof",
        expected_verdict="runtime_error",
        expected_error_type="EOFError",
        code='''def is_palindrome(s):
    extra = input()  # a second input() the student didn't mean to call
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="18_oom_direct_allocation",
        expected_verdict="oom",
        expected_error_type=None,
        code='''def is_palindrome(s):
    big = bytearray(1024 * 1024 * 1024)  # 1GB direct allocation
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="19_oom_growing_loop",
        expected_verdict="oom",
        expected_error_type=None,
        code='''def is_palindrome(s):
    buf = ""
    while True:
        buf += "x" * 1000000  # doubling-ish growth via repeated concat
    return True

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="20_empty_submission",
        expected_verdict="rejected",
        expected_error_type=None,
        code="",
    ),
    dict(
        id="21_whitespace_only",
        expected_verdict="rejected",
        expected_error_type=None,
        code="   \n\n   \n",
    ),
    dict(
        id="22_oversized_submission",
        expected_verdict="rejected",
        expected_error_type=None,
        code="def is_palindrome(s):\n" + ("    # filler line\n" * 250) + "    return s == s[::-1]\n",
    ),
    dict(
        id="23_unicode_content",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def is_palindrome(s):
    # kommentar med norske tegn: æøå \U0001F600
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="24_disallowed_import",
        expected_verdict="runtime_error",
        expected_error_type="ModuleNotFoundError",
        code='''import numpy  # not part of the taught standard library

def is_palindrome(s):
    t = s.lower().replace(" ", "")
    return t == t[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
    dict(
        id="25_key_error",
        expected_verdict="runtime_error",
        expected_error_type="KeyError",
        code='''def is_palindrome(s):
    cache = {}
    normalized = cache["precomputed"]  # never populated
    return normalized == normalized[::-1]

s = input()
print(is_palindrome(s))
''',
    ),
]