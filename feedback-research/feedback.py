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
            "NameError -- Python doesn't recognize a name you used.",
            "Read the last line of the traceback: which name is it saying isn't defined? Is that "
            "a function you meant to write, or a typo for one you did write?",
            "You're calling a name you never defined -- define it, or fix the typo against the "
            "name you did define.",
        ],
        discussion="A NameError means Python doesn't recognize a name that was used -- almost "
        "always a typo, or a variable/function referenced before it was ever defined.",
    ),
    "AttributeError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "AttributeError -- you called a method that doesn't exist on that object.",
            "Check the exact spelling of the method name against Python's string methods -- is it "
            "spelled exactly the way you'd find it in the docs?",
            "Fix the misspelled method name so it matches an actual method on that type.",
        ],
        discussion="An AttributeError means a method was called that doesn't exist on that "
        "object -- usually a small misspelling of a real method name.",
    ),
    "RecursionError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "RecursionError -- your function called itself too many times without stopping.",
            "What condition should make your function return without calling itself again? Does "
            "your function currently have one?",
            "Add a base case that returns directly once the input is small enough, instead of "
            "always recursing.",
        ],
        discussion="A RecursionError means a function kept calling itself without ever hitting a "
        "base case that stops the recursion.",
    ),
    "TypeError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "TypeError -- an operation was used on a value of the wrong type, or a function call "
            "didn't match its definition.",
            "Look at the operation or call on the line named in the traceback -- do the types (or "
            "number of arguments) actually match what it expects?",
            "Fix the mismatched type or argument count on that line so it matches what the "
            "operation or function expects.",
        ],
        discussion="A TypeError means an operation or function call didn't match the type or "
        "number of arguments it expected.",
    ),
    "IndexError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "IndexError -- you tried to access a position in a sequence that doesn't exist.",
            "Check the index you're using against the actual valid range for that sequence's "
            "length -- what's the last valid index?",
            "Adjust the index so it stays inside the valid range for the sequence's length.",
        ],
        discussion="An IndexError means the code accessed a position in a sequence that's "
        "outside its valid range.",
    ),
    "KeyError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "KeyError -- you looked up a key that isn't in the dictionary.",
            "Where does that key get added to the dictionary in your code? Is that happening "
            "before you look it up?",
            "Populate the dictionary with that key before you look it up, or use a lookup that "
            "doesn't require it to already exist.",
        ],
        discussion="A KeyError means the code looked up a dictionary key that was never added "
        "to it.",
    ),
    "ModuleNotFoundError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "ModuleNotFoundError -- you imported something that isn't available.",
            "This exercise only needs the standard string operations covered in lecture -- do you "
            "need that import at all?",
            "Remove the import and rewrite the line to use only standard string operations.",
        ],
        discussion="A ModuleNotFoundError means an import was used that isn't available -- worth "
        "checking whether the exercise actually needs it.",
    ),
    "EOFError": dict(
        ceiling=4,
        tiers=[
            "Your program crashed before producing output.",
            "EOFError -- your program tried to read input that was never there.",
            "Count how many times your program calls the input-reading function against how many "
            "lines of input it's actually given -- do they match?",
            "Remove the extra input call, or provide the extra input it's waiting for.",
        ],
        discussion="An EOFError means the code tried to read more input than was actually "
        "given to it.",
    ),
}

# Any runtime_error exception name classify.py can emit that doesn't have a dedicated family above
# (e.g. ValueError, ZeroDivisionError, ImportError, or classify.py's "Unknown" fallback) still gets
# a usable, if more generic, hint -- structural ceiling capped at 3 since there's no specific
# bottom-out text to write without knowing the exact bug.
_RUNTIME_FALLBACK = dict(
    ceiling=3,
    tiers=[
        "Your program crashed before producing output.",
        "{error_type} -- read the exception name in the traceback; it names the general kind of "
        "problem.",
        "Look at the exact line named at the bottom of the traceback -- what is that line trying "
        "to do, and why might it fail for this input?",
    ],
    discussion="A {error_type} means something crashed -- worth reading together where exactly "
    "the traceback points and what that exception generally signals.",
)

_OTHER_FAMILIES = {
    "wrong_answer": dict(
        ceiling=4,
        tiers=[
            "Your output didn't match on the test input for this problem.",
            "The mismatch is about how your program processes the input, not about crashing.",
            "Trace your code by hand on the exact test input, step by step -- where does the "
            "value it produces first diverge from what you'd expect?",
            "Compare your logic against the problem statement line by line and correct the step "
            "that diverges.",
        ],
        discussion="The code ran without crashing but produced the wrong output -- worth tracing "
        "through the test input step by step to see where the logic diverges from what's "
        "expected.",
    ),
    "syntax_error": dict(
        ceiling=2,
        tiers=[
            "Your program couldn't even start running -- Python found a problem before your code "
            "executed at all.",
            "Compare the line the error points to against the syntax pattern from the lecture "
            "slides for that kind of statement (a function definition, a loop, an if) -- does it "
            "match exactly?",
        ],
        discussion="The code had a syntax error -- worth comparing the flagged line against the "
        "exact pattern from the lecture slides for that kind of statement.",
    ),
    "function_not_found": dict(
        ceiling=2,
        tiers=[
            "The grader couldn't find the function it expected to call.",
            "Check the exact function name you defined against the one the problem statement asks "
            "for.",
        ],
        discussion="The grader couldn't find the expected function -- worth double-checking the "
        "exact function name the exercise asks for.",
    ),
    # shared family: timeout / oom / output_limit_exceeded -- see hint-taxonomy-draft.md, split
    # back out only if simulated-student fix-rates diverge meaningfully across the three verdicts.
    "bounded_loop": dict(
        ceiling=4,
        tiers=[
            "Your program didn't finish -- it was stopped for running too long or using too many "
            "resources.",
            "This usually means a loop that never reaches its stopping condition.",
            "Find the loop responsible and check the variable its condition depends on -- does "
            "anything inside the loop body actually change it?",
            "Add the missing update (increment, append-then-check, or similar) so the loop's "
            "condition can eventually become false.",
        ],
        discussion="The program didn't finish -- usually a loop whose stopping condition never "
        "actually becomes true, worth checking what should update it.",
    ),
    "rejected": dict(
        ceiling=1,
        tiers=[
            "Your submission couldn't be graded as-is -- it's empty, or over the allowed size "
            "limit.",
        ],
        discussion="Some submissions came in empty or over the size limit -- worth a reminder on "
        "what counts as a valid submission.",
    ),
}

VERDICT_TO_FAMILY = {
    "wrong_answer": "wrong_answer",
    "syntax_error": "syntax_error",
    "function_not_found": "function_not_found",
    "timeout": "bounded_loop",
    "oom": "bounded_loop",
    "output_limit_exceeded": "bounded_loop",
    "rejected": "rejected",
}


def _family_for(verdict, error_type):
    if verdict == "runtime_error":
        return _RUNTIME_FAMILIES.get(error_type, _RUNTIME_FALLBACK)
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
        return ("runtime_error", error_type if error_type in _RUNTIME_FAMILIES else "_fallback")
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
    """Just the curated 'what this category actually means' sentence -- the reviewed
    text that already backs the student-facing hints (same family lookup as get_hint()),
    with no framing or student count attached. This is the one piece of a lecturer
    discussion point that must never be dropped: see discussion_point_for() and, for how
    it's meant to be composed with an optional model-written lead-in,
    backend/aggregation.py.

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
    """Deterministic lecturer talking-point sentence for a cluster of students who hit
    the same (verdict, error_type) issue -- same curated-template approach as
    hint_for_attempt(), and for the same reason: an LLM judge was tried for this role
    and dropped. Even handed the exact correct classification, it fabricated causes
    that didn't match the actual bug (see pedagogical-feedback-design-decision.md), so
    this reuses the same reviewed mechanism_for() text that already backs the
    student-facing hints instead of asking a model to improvise one.

    Returns None for verdict == "pass" (nothing to discuss) or an unrecognized
    (verdict, error_type) pair (nothing safe to say) -- callers should treat that as
    "no discussion point available", not an error.
    """
    mechanism = mechanism_for(verdict, error_type)
    if mechanism is None:
        return None
    plural = "student" if student_count == 1 else "students"
    return f"{student_count} {plural} hit this: {mechanism}"
