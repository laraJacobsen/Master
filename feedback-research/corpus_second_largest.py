# 17-case corpus for the second_largest lecture question -- third exercise added to grow the eval
# corpus beyond is_palindrome/count_vowels (see hint-taxonomy-draft.md open question 4). Hand-written
# the same way corpus.py was, prioritizing the verdict/error_type cells that showed real signal in
# the 2026-09-15 simulated-student runs: wrong_answer, AttributeError, IndexError,
# ModuleNotFoundError, TypeError, and the bounded_loop family (timeout/oom/output_limit_exceeded).
# NameError, RecursionError, EOFError, KeyError, and rejected are deliberately NOT re-covered here
# -- they weren't priorities and don't arise naturally from this problem's shape.
#
# Reference correct behavior: second_largest(nums) -> the second-largest DISTINCT value in nums.
#
# Test input chosen deliberately to expose a no-dedup bug: 9 appears twice, so a solution that
# doesn't deduplicate before picking the second element will return 9 (the duplicate), not 7 (the
# true second-largest distinct value).

TEST_INPUT = "4 1 7 7 3 9 9 2"
EXPECTED_OUTPUT = "7"
EXPECTED_FUNCTION_NAME = "second_largest"
PROBLEM_STATEMENT = (
    "Write a function second_largest(nums) that takes a list of integers and returns the "
    "second-largest distinct value in nums. Read a line of space-separated integers from stdin, "
    "convert them to a list of integers, call second_largest on it, and print the result."
)

CASES = [
    dict(
        id="01_correct_clean",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def second_largest(nums):
    distinct = sorted(set(nums), reverse=True)
    return distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="02_correct_with_debug_prints",
        expected_verdict="pass",
        expected_error_type=None,
        code='''def second_largest(nums):
    distinct = sorted(set(nums), reverse=True)
    print("DEBUG: distinct sorted =", distinct)
    return distinct[1]

nums = [int(x) for x in input().split()]
result = second_largest(nums)
print("DEBUG: result computed")
print(result)
''',
    ),
    dict(
        id="03_wrong_no_dedup",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def second_largest(nums):
    s = sorted(nums, reverse=True)  # no dedup: picks second position, not second distinct value
    return s[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="04_wrong_ascending_confusion",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def second_largest(nums):
    s = sorted(set(nums))  # ascending, not descending
    return s[1]  # grabs second-smallest distinct instead of second-largest

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="05_wrong_flipped_comparison",
        expected_verdict="wrong_answer",
        expected_error_type=None,
        code='''def second_largest(nums):
    largest = max(nums)
    second = None
    for n in nums:
        if n != largest:
            if second is None or n < second:  # bug: should be n > second
                second = n
    return second

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="06_syntax_error",
        expected_verdict="syntax_error",
        expected_error_type=None,
        code='''def second_largest(nums)
    distinct = sorted(set(nums), reverse=True)
    return distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="07_function_not_found",
        expected_verdict="function_not_found",
        expected_error_type=None,
        code='''def find_second_largest(nums):  # wrong function name
    distinct = sorted(set(nums), reverse=True)
    return distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="08_attribute_error_no_max_method",
        expected_verdict="runtime_error",
        expected_error_type="AttributeError",
        code='''def second_largest(nums):
    return nums.max()  # lists have no .max() method; should be max(nums)

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="09_attribute_error_typo",
        expected_verdict="runtime_error",
        expected_error_type="AttributeError",
        code='''def second_largest(nums):
    nums.srot(reverse=True)  # typo'd method name
    return nums[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="10_index_error_off_the_end",
        expected_verdict="runtime_error",
        expected_error_type="IndexError",
        code='''def second_largest(nums):
    distinct = sorted(set(nums), reverse=True)
    return distinct[len(distinct)]  # off-the-end index, should be distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="11_index_error_adjacent_scan",
        expected_verdict="runtime_error",
        expected_error_type="IndexError",
        code='''def second_largest(nums):
    largest = max(nums)
    second = min(nums)
    for i in range(len(nums)):
        if nums[i] != largest and nums[i + 1] > second:  # reads one index ahead, overruns at the end
            second = nums[i + 1]
    return second

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="12_type_error_never_converted",
        expected_verdict="runtime_error",
        expected_error_type="TypeError",
        code='''def second_largest(nums):
    s = sorted(nums, reverse=True)
    return s[1] - 1  # str - int: nums was never converted from strings to ints

nums = input().split()  # bug: forgot int() conversion
print(second_largest(nums))
''',
    ),
    dict(
        id="13_wrong_signature",
        expected_verdict="runtime_error",
        expected_error_type="TypeError",
        code='''def second_largest(nums, k):  # extra required arg
    distinct = sorted(set(nums), reverse=True)
    return distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))  # missing required positional arg
''',
    ),
    dict(
        id="14_disallowed_import",
        expected_verdict="runtime_error",
        expected_error_type="ModuleNotFoundError",
        code='''import pandas as pd  # not part of the taught standard library

def second_largest(nums):
    s = pd.Series(nums).sort_values(ascending=False)
    return s.unique()[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="15_timeout_missing_increment",
        expected_verdict="timeout",
        expected_error_type=None,
        code='''def second_largest(nums):
    largest = max(nums)
    second = min(nums)
    i = 0
    while i < len(nums):
        if nums[i] != largest and nums[i] > second:
            second = nums[i]
        # forgot i += 1 -> infinite loop
    return second

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="16_oom_direct_allocation",
        expected_verdict="oom",
        expected_error_type=None,
        code='''def second_largest(nums):
    big = bytearray(1024 * 1024 * 1024)  # 1GB direct allocation
    distinct = sorted(set(nums), reverse=True)
    return distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
    dict(
        id="17_output_flood",
        expected_verdict="output_limit_exceeded",
        expected_error_type=None,
        code='''def second_largest(nums):
    while True:
        print("scanning...")  # debug print left in an unbounded loop
    distinct = sorted(set(nums), reverse=True)
    return distinct[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))
''',
    ),
]
