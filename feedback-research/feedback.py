"""
Verdict -> feedback layer. Step 2 of pedagogical-feedback-design-decision.md, built directly on
the tiers/ceilings drafted in hint-taxonomy-draft.md.

Tiers 1-3 are what the shipped tool ever shows a student (SHIPPED_TIER_CAP). Tier 4 (bottom-out)
exists so the simulated-student eval loop (step 3) can score it as a research-only upper bound --
hint_for_attempt()'s default (ship=True) path never returns it.

Escalation: tier = min(attempt_number, structural ceiling), further capped at SHIPPED_TIER_CAP when
shipping. attempt_number is scoped to (student_token, question_id) -- see hint-taxonomy-draft.md --
so this module never needs to reason about a student's history on any other problem.
"""

SHIPPED_TIER_CAP = 3

# Each family: structural ceiling (may exceed SHIPPED_TIER_CAP) + literal tier text, tiers[0] = tier 1.
_RUNTIME_FAMILIES = {
    "NameError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "NameError: Python doesn't recognize a name you used.",
            "Read the last line of the traceback: which name is it saying isn't defined? Is that "
            "a function you meant to write, or a typo for one you did write?",
            "You're calling a name you never defined. Define it, or fix the typo against the "
            "name you did define.",
        ],
        discussion="NameError. Check the traceback's last line for the name it flags: a typo, "
        "or a name never defined.",
    ),
    "AttributeError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "AttributeError: you called a method that doesn't exist on that object.",
            "Check the exact spelling of the method name against Python's string methods. Is it "
            "spelled exactly the way you'd find it in the docs?",
            "Fix the misspelled method name so it matches an actual method on that type.",
        ],
        discussion="AttributeError: check the exact method name against the real API. Likely "
        "a small misspelling.",
    ),
    "RecursionError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "RecursionError: your function called itself too many times without stopping.",
            "What condition should make your function return without calling itself again? Does "
            "your function currently have one?",
            "Add a base case that returns directly once the input is small enough, instead of "
            "always recursing.",
        ],
        discussion="RecursionError: check whether the function has a base case that stops the "
        "recursion.",
    ),
    "TypeError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "TypeError: an operation was used on a value of the wrong type, or a function call "
            "didn't match its definition.",
            "Look at the operation or call on the line named in the traceback. Do the types (or "
            "number of arguments) actually match what it expects?",
            "Fix the mismatched type or argument count on that line so it matches what the "
            "operation or function expects.",
        ],
        discussion="TypeError: check the types or argument count on the flagged line against "
        "what's expected.",
    ),
    "IndexError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "IndexError: you tried to access a position in a sequence that doesn't exist.",
            "Check the index you're using against the actual valid range for that sequence's "
            "length. What's the last valid index?",
            "Adjust the index so it stays inside the valid range for the sequence's length.",
        ],
        discussion="IndexError: check the index against the sequence's actual valid range.",
    ),
    "KeyError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "KeyError: you looked up a key that isn't in the dictionary.",
            "Where does that key get added to the dictionary in your code? Is that happening "
            "before you look it up?",
            "Populate the dictionary with that key before you look it up, or use a lookup that "
            "doesn't require it to already exist.",
        ],
        discussion="KeyError: check whether the key was added to the dictionary before it's "
        "looked up.",
    ),
    "ModuleNotFoundError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "ModuleNotFoundError: you imported something that isn't available.",
            "This exercise only needs the standard string operations covered in lecture. Do you "
            "need that import at all?",
            "Remove the import and rewrite the line to use only standard string operations.",
        ],
        discussion="ModuleNotFoundError: check whether the exercise actually needs that import.",
    ),
    "EOFError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "EOFError: your program tried to read input that was never there.",
            "Count how many times your program calls the input-reading function against how many "
            "lines of input it's actually given. Do they match?",
            "Remove the extra input call, or provide the extra input it's waiting for.",
        ],
        discussion="EOFError: check whether the code is reading more input than it's actually "
        "given.",
    ),

    # --- C (classify.py's _classify_c_crash: from the exit code, since C prints no exception)
    "SegmentationFault": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "Segmentation fault: your program read or wrote memory that doesn't belong to it.",
            "Check every array index against the array's size (the last valid index is size - "
            "1), and every scanf: does each variable you read into have an & in front of it?",
            "Fix the out-of-range index, or add the missing &, so every read and write goes to a "
            "variable or array element that actually exists.",
        ],
        discussion="Segmentation fault: check array indexes against the array size, and for a "
        "missing & in scanf.",
    ),
    "FloatingPointException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "Floating point exception: despite the name, this is an integer division or % by "
            "zero.",
            "Find each / and % in your code. Which one can have 0 on the right-hand side for "
            "this input?",
            "Make sure the divisor can't be 0 there: check it first, or fix the value it's "
            "computed from.",
        ],
        discussion="Integer division or % by zero. Check which divisor can be 0 for the test "
        "input.",
    ),
    "Aborted": dict(
        ceiling=3,
        tiers=[
            "Your program crashed while it was running.",
            "Aborted: your program stopped itself, usually because an assert() failed.",
            "Read the error output: which assertion failed, and what did you expect to be true "
            "at that point?",
        ],
        discussion="Aborted, usually a failed assert(). Worth reading which assertion failed.",
    ),
    "NonZeroExit": dict(
        ceiling=3,
        tiers=[
            "Your program ended with an error status, which counts as a failure even if the "
            "output looks right.",
            "A C program tells the system it succeeded by returning 0 from main.",
            "Declare main as int main(void) and end it with return 0;",
        ],
        discussion="main didn't return 0. Worth a reminder to declare int main and end it with "
        "return 0;",
    ),

    # --- Java (classify.py's _classify_java_crash: the name from `Exception in thread "main"`)
    "MainNotFound": dict(
        ceiling=2,
        tiers=[
            "Your program couldn't be started. The grader runs a class named Main and calls its "
            "main method.",
            "Name your class exactly public class Main, remove any package line at the top of "
            "the file, and keep the method as public static void main(String[] args).",
        ],
        discussion="Couldn't start: the class must be named Main, with no package line.",
    ),
    "NoSuchElementException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "NoSuchElementException: your program tried to read input that wasn't there.",
            "Count your Scanner reads (nextInt(), nextLine(), ...) against the input you're "
            "actually given. Do they match? Is your loop reading past the last value?",
            "Remove the extra read, or loop with hasNextInt()/hasNextLine() so you stop when the "
            "input runs out.",
        ],
        discussion="NoSuchElementException: the code reads more input than it's given.",
    ),
    "InputMismatchException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "InputMismatchException: Scanner read a value of a different type than you asked "
            "for.",
            "Look at the input and at the Scanner method reading it. Is there text where you "
            "call nextInt(), or a decimal number where you expect an int?",
            "Use the Scanner method that matches the input's type at that position (next(), "
            "nextDouble(), ...).",
        ],
        discussion="InputMismatchException: the Scanner method doesn't match the input's type.",
    ),
    "NumberFormatException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "NumberFormatException: you tried to turn text into a number, but it wasn't a "
            "number.",
            "Look at the exact string you pass to Integer.parseInt (or similar). Does it contain "
            "spaces, or more than one number, like a whole input line \"3 4\"?",
            "Split the line into separate numbers first (line.split(\" \")) and parse each one.",
        ],
        discussion="NumberFormatException: often parseInt on a whole line that holds several "
        "numbers.",
    ),
    "NullPointerException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "NullPointerException: you used a variable that doesn't refer to any object (it's "
            "null).",
            "The stack trace names the line. Which variable is used there, and where is it "
            "given an object (with new, or a method that returns one)?",
            "Give that variable an object before the line that uses it.",
        ],
        discussion="NullPointerException: a variable is used before it's given an object.",
    ),
    "ArithmeticException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "ArithmeticException: most likely an integer division or % by zero.",
            "Find each / and % in your code. Which one can have 0 on the right-hand side for "
            "this input?",
            "Make sure the divisor can't be 0 there: check it first, or fix the value it's "
            "computed from.",
        ],
        discussion="ArithmeticException, usually integer division by zero.",
    ),
    # Shared by every Java index exception -- see _RUNTIME_ALIASES.
    "ArrayIndexOutOfBoundsException": dict(
        ceiling=4,
        tiers=[
            "Your program crashed while it was running.",
            "{error_type}: you used a position that doesn't exist in the array, string or list.",
            "Check the index against the length: the last valid index is length - 1. Does a "
            "loop go one step too far (<= instead of <)?",
            "Adjust the index or the loop bound so it stays inside 0 .. length - 1.",
        ],
        discussion="{error_type}: check the index against the length, often <= instead of <.",
    ),
}

# Exception names that share another family's hints (written with {error_type}, so the
# student still sees the exact name their program raised).
_RUNTIME_ALIASES = {
    "StringIndexOutOfBoundsException": "ArrayIndexOutOfBoundsException",
    "IndexOutOfBoundsException": "ArrayIndexOutOfBoundsException",
}

# Any runtime_error exception name classify.py can emit that doesn't have a dedicated family above
# (e.g. ValueError, ZeroDivisionError, ImportError, or classify.py's "Unknown" fallback) still gets
# a usable, if more generic, hint -- structural ceiling capped at 3 since there's no specific
# bottom-out text to write without knowing the exact bug.
_RUNTIME_FALLBACK = dict(
    ceiling=3,
    tiers=[
        "Your program crashed before producing output.",
        "{error_type}: read the exception name in the traceback. It names the general kind of "
        "problem.",
        "Look at the exact line named at the bottom of the traceback. What is that line trying "
        "to do, and why might it fail for this input?",
    ],
    discussion="{error_type}. Worth reading through the traceback together to see exactly "
    "where it crashed.",
)

_OTHER_FAMILIES = {
    "wrong_answer": dict(
        ceiling=4,
        tiers=[
            "Your output didn't match on the test input for this problem.",
            "The mismatch is about how your program processes the input, not about crashing.",
            "Trace your code by hand on the exact test input, step by step. Where does the "
            "value it produces first diverge from what you'd expect?",
            "Compare your logic against the problem statement line by line and correct the step "
            "that diverges.",
        ],
        discussion="Wrong answer. Worth tracing through the test input step by step to see "
        "where the logic diverges.",
    ),
    "syntax_error": dict(
        ceiling=2,
        tiers=[
            "Your program couldn't even start running. Python found a problem before your code "
            "executed at all.",
            "Compare the line the error points to against the syntax pattern from the lecture "
            "slides for that kind of statement (a function definition, a loop, an if). Does it "
            "match exactly?",
        ],
        discussion="Syntax error. Worth comparing the flagged line against the exact pattern "
        "from the lecture slides.",
    ),
    # Compiled languages only (C, Java): Python reports its parse errors as syntax_error.
    "compile_error": dict(
        ceiling=2,
        tiers=[
            "Your program couldn't be compiled, so it never ran.",
            "Read the first error the compiler reports and the line number it gives. Later "
            "errors are often caused by the first one, so fix that one and compile again.",
        ],
        discussion="Compile error. Worth reading the compiler's first error together: the "
        "ones after it often follow from it.",
    ),
    "function_not_found": dict(
        ceiling=2,
        tiers=[
            "The grader couldn't find the function it expected to call.",
            "Check the exact function name you defined against the one the problem statement asks "
            "for.",
        ],
        discussion="Function not found. Worth double-checking the exact function name the "
        "exercise asks for.",
    ),
    # shared family: timeout / oom / output_limit_exceeded -- see hint-taxonomy-draft.md, split
    # back out only if simulated-student fix-rates diverge meaningfully across the three verdicts.
    "bounded_loop": dict(
        ceiling=4,
        tiers=[
            "Your program didn't finish. It was stopped for running too long or using too many "
            "resources.",
            "This usually means a loop that never reaches its stopping condition.",
            "Find the loop responsible and check the variable its condition depends on. Does "
            "anything inside the loop body actually change it?",
            "Add the missing update (increment, append-then-check, or similar) so the loop's "
            "condition can eventually become false.",
        ],
        discussion="Didn't finish. Worth checking what should update the loop's stopping "
        "condition.",
    ),
    "rejected": dict(
        ceiling=1,
        tiers=[
            "Your submission couldn't be graded as-is. It's empty, or over the allowed size "
            "limit.",
        ],
        discussion="Rejected submissions. Worth a reminder on what counts as a valid "
        "submission.",
    ),
}

VERDICT_TO_FAMILY = {
    "wrong_answer": "wrong_answer",
    "syntax_error": "syntax_error",
    "compile_error": "compile_error",
    "function_not_found": "function_not_found",
    "timeout": "bounded_loop",
    "oom": "bounded_loop",
    "output_limit_exceeded": "bounded_loop",
    "rejected": "rejected",
}


def _family_for(verdict, error_type):
    if verdict == "runtime_error":
        return _RUNTIME_FAMILIES.get(_RUNTIME_ALIASES.get(error_type, error_type), _RUNTIME_FALLBACK)
    key = VERDICT_TO_FAMILY.get(verdict)
    if key is None:
        return None  # e.g. "pass" -- no hint family
    return _OTHER_FAMILIES[key]


def family_key_for(verdict, error_type=None):
    """Public identifier for which hint family a (verdict, error_type) pair maps to -- e.g. groups
    timeout/oom/output_limit_exceeded under one "bounded_loop" key. Lets callers (e.g. the
    simulated-student eval loop) aggregate results across verdicts that intentionally share hint
    content, rather than only ever scoring each verdict in isolation.
    """
    if verdict == "runtime_error":
        family = _RUNTIME_ALIASES.get(error_type, error_type)
        return ("runtime_error", family if family in _RUNTIME_FAMILIES else "_fallback")
    return VERDICT_TO_FAMILY.get(verdict, verdict)


def ceiling_for(verdict, error_type=None):
    """Structural ceiling: how many distinct tiers this verdict/error_type actually has.

    A thin wrapper so an instructor-override layer (deferred, see hint-taxonomy-draft.md) can wrap
    this lookup later without touching callers.
    """
    family = _family_for(verdict, error_type)
    if family is None:
        raise ValueError(
            f"no hint family for verdict={verdict!r} (did you mean to call this on a 'pass'?)"
        )
    return family["ceiling"]


def get_hint(verdict, error_type, tier):
    """Literal tier text. tier must be within 1..ceiling_for(verdict, error_type).

    Low-level accessor the simulated-student eval loop (step 3) uses to score every (verdict,
    tier) cell, including tier 4 -- which hint_for_attempt() never returns by default.
    """
    family = _family_for(verdict, error_type)
    if family is None:
        raise ValueError(f"no hint family for verdict={verdict!r}")
    ceiling = family["ceiling"]
    if not (1 <= tier <= ceiling):
        raise ValueError(
            f"tier {tier} out of range 1..{ceiling} for verdict={verdict!r} "
            f"error_type={error_type!r}"
        )
    text = family["tiers"][tier - 1]
    return text.format(error_type=error_type) if "{error_type}" in text else text


def hint_for_attempt(verdict, error_type, attempt_number, ship=True):
    """Escalation entry point.

    tier = min(attempt_number, structural ceiling), further capped at SHIPPED_TIER_CAP when
    ship=True (live-tool policy: tier 4/bottom-out is never shown to a student). Pass ship=False
    only from the eval harness, which deliberately wants the full curve.

    Returns None for verdict == "pass" (nothing to hint about).
    """
    if verdict == "pass":
        return None
    ceiling = ceiling_for(verdict, error_type)
    tier = min(attempt_number, ceiling)
    if ship:
        tier = min(tier, SHIPPED_TIER_CAP)
    return get_hint(verdict, error_type, tier)


def mechanism_for(verdict, error_type=None):
    """The curated lecturer-facing line for this category: a short label plus one
    actionable clause -- the same family lookup as get_hint() uses for the
    student-facing hints, but written for the lecturer's own dashboard, not the
    student. This is the entire lecturer discussion point now; see
    discussion_point_for().

    Returns None for verdict == "pass" or an unrecognized (verdict, error_type) pair.
    """
    if verdict == "pass":
        return None
    family = _family_for(verdict, error_type)
    if family is None:
        return None
    mechanism = family["discussion"]
    if "{error_type}" in mechanism:
        mechanism = mechanism.format(error_type=error_type)
    return mechanism


def discussion_point_for(verdict, error_type=None, student_count=1):
    """Deterministic lecturer talking-point for a cluster of students who hit the same
    (verdict, error_type) issue -- same curated-template approach as hint_for_attempt(),
    and for the same reason: an LLM judge was tried for this role and dropped. Even
    handed the exact correct classification, it fabricated causes that didn't match the
    actual bug, then (once forbidden from explaining the cause) added nothing but
    content-free filler, then addressed the student instead of the lecturer -- see
    pedagogical-feedback-design-decision.md. Once trimmed down to a short, actionable
    line with no count and no definition to embellish, there was nothing left for a
    model to usefully add, so this is just mechanism_for()'s curated text, verbatim.

    student_count is accepted (callers already have it, for the
    MIN_STUDENTS_FOR_DISCUSSION gate before this is ever called) but no longer appears
    in the text itself -- the count is shown separately, as the cluster's own field.

    Returns None for verdict == "pass" (nothing to discuss) or an unrecognized
    (verdict, error_type) pair (nothing safe to say) -- callers should treat that as
    "no discussion point available", not an error.
    """
    return mechanism_for(verdict, error_type)
