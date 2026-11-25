"""Near-duplicate submissions (backend/code_normalize.py and the submit path):
normalisation for Python, C and Java, and what a duplicate does -- and doesn't --
do. Temporary DB only (tests/conftest.py)."""

import pytest

from backend import aggregation, main, store
from backend.code_normalize import normalize, normalize_submission, similarity, tokens
from tests.test_hint_unlock import FAILING, live, submit  # noqa: F401  (live is a fixture)

# --- normalisation -----------------------------------------------------------------

PY = "x = int(input())\nprint(x + 1)\n"


@pytest.mark.parametrize("same", [
    "x=int(input())\nprint(x+1)",                               # spacing
    "# read it\nx = int(input())  # the number\n\nprint(x + 1)\n",  # comments, blank lines
    "x = int(\n    input()\n)\nprint((x + 1))\n",                  # line breaks, redundant parens
])
def test_python_formatting_and_comments_dont_matter(same):
    assert normalize(same, "python") == normalize(PY, "python")


@pytest.mark.parametrize("changed", [
    "y = int(input())\nprint(y + 1)\n",   # a rename is a change (see the module docstring)
    "x = int(input())\nprint(x + 2)\n",
    "x = int(input())\nprint('x + 1')\n",
])
def test_python_real_changes_are_changes(changed):
    assert normalize(changed, "python") != normalize(PY, "python")


def test_python_that_doesnt_parse():
    broken = "x = (int(input())\nprint(x)\n"
    assert normalize(broken + "# note\n", "python") == normalize(broken, "python")
    assert normalize(broken, "python") != normalize(broken.replace("print(x)", "print(x + 1)"), "python")
    assert normalize(broken, "python") != normalize("", "python")


C = '#include <stdio.h>\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    printf("%d\\n", a + b);\n    return 0;\n}\n'


def test_c_comments_and_whitespace_dont_matter():
    other = ('#include <stdio.h>\n/* add two numbers */\nint main(void){int a,b; // read\n'
             'scanf("%d %d",&a,&b);printf("%d\\n",a+b);return 0;}')
    assert normalize(other, "c") == normalize(C, "c")


def test_c_string_contents_and_code_are_changes():
    assert normalize(C.replace('"%d\\n"', '"%d \\n"'), "c") != normalize(C, "c")  # space inside a literal
    assert normalize(C.replace("a + b", "a - b"), "c") != normalize(C, "c")
    assert "// not a comment" in normalize('printf("// not a comment");', "c")


JAVA = ("import java.util.Scanner;\npublic class Main {\n    public static void main(String[] args) {\n"
        "        Scanner in = new Scanner(System.in);\n        System.out.println(in.nextInt() + in.nextInt());\n"
        "    }\n}\n")


def test_java_comments_and_whitespace_dont_matter():
    other = ("import java.util.Scanner;\n/** Adds. */\npublic class Main{public static void main(String[] args){"
             "Scanner in=new Scanner(System.in); // input\nSystem.out.println(in.nextInt()+in.nextInt());}}")
    assert normalize(other, "java") == normalize(JAVA, "java")
    assert normalize(JAVA.replace("+ in.nextInt()", "* in.nextInt()"), "java") != normalize(JAVA, "java")


def test_multi_file_submissions_compare_file_by_file():
    a = {"solution.py": PY, "helpers.py": "def f():\n    return 1\n"}
    b = {"helpers.py": "def f():  # same\n    return 1\n", "solution.py": PY}
    assert normalize_submission("", a, "python") == normalize_submission("", b, "python")
    c = {**a, "helpers.py": "def f():\n    return 2\n"}
    assert normalize_submission("", a, "python") != normalize_submission("", c, "python")


def test_similarity():
    a, b = tokens(PY, "python"), tokens("x = int(input())  # same\nprint(x + 2)\n", "python")
    assert similarity(a, a) == 1.0
    assert 0.9 < similarity(a, b) < 1.0
    unrelated = tokens("import sys\nfor line in sys.stdin:\n    print(line)\n", "python")
    assert similarity(a, unrelated) < 0.5


# --- through the submit path -----------------------------------------------------------

WRONG_A = "a, b = map(int, input().split())\nprint(a + b + 1)\n"
WRONG_B = "a, b = map(int, input().split())\nprint(a * b + 1)\n"


@pytest.fixture
def judge_calls(monkeypatch):
    calls = []

    def fake(source, *a, **k):
        calls.append(source)
        return [dict(r) for r in FAILING]

    monkeypatch.setattr(main, "run_test_cases", fake)
    return calls


def test_identical_code_isnt_run_counted_or_stored(live, judge_calls):
    client, qid, headers = live
    first = submit(client, qid, headers, WRONG_A)
    again = submit(client, qid, headers, "# trying again\n" + WRONG_A.replace("+ 1", "+1"))
    assert len(judge_calls) == 1  # not run again
    assert again["counted"] is False and again["not_counted_reason"] == "duplicate"
    assert again["duplicate_of"] == first["attempt_number"] == 1
    assert "Same code as your attempt #1" in again["notice"]
    assert (again["verdict"], again["tests_passed"]) == (first["verdict"], first["tests_passed"])
    assert again["hint_state"]["counted_attempts"] == 1 and again["hint_state"]["duplicates"] == 1
    assert [r["kind"] for r in store.duplicates(qid, "Ada")] == ["same"]
    assert len([r for r in store.all_submissions(qid) if r["student_name"] == "Ada"]) == 1


def test_duplicates_dont_unlock_hints(live, judge_calls):
    client, qid, headers = live  # policy: 1 free attempt, then one hint per counted attempt
    submit(client, qid, headers, WRONG_A)
    for _ in range(3):
        r = submit(client, qid, headers, WRONG_A)
    assert r["hint_state"]["level"] == 0 and r["hint_tier"] == 0
    r = submit(client, qid, headers, WRONG_B)  # a real change
    assert r["counted"] is True and r["hint_state"]["level"] == 1


def test_alternating_two_versions_is_caught(live, judge_calls):
    client, qid, headers = live
    submit(client, qid, headers, WRONG_A)
    submit(client, qid, headers, WRONG_B)
    r = submit(client, qid, headers, WRONG_A)
    assert r["not_counted_reason"] == "duplicate" and r["duplicate_of"] == 1
    assert len(judge_calls) == 2


def test_clustering_never_sees_a_duplicate(live, judge_calls):
    client, qid, headers = live
    first = submit(client, qid, headers, WRONG_A)
    submit(client, qid, headers, WRONG_A)
    ids = [i for c in aggregation.cluster_submissions(qid) for i in c["submission_ids"]]
    assert ids == [first["submission_id"]]


def test_a_crash_then_its_fix_counts_twice(live, monkeypatch):
    client, qid, headers = live
    crash = [dict(FAILING[0], passed=False, stdout="", status_id=11, status_description="Runtime Error (NZEC)",
                  exit_code=1, stderr='Traceback (most recent call last):\n  File "script.py", line 2\nNameError: name \'b\' is not defined')]
    answers = iter([crash, [dict(r) for r in FAILING]])
    monkeypatch.setattr(main, "run_test_cases", lambda *a, **k: next(answers))
    typo = submit(client, qid, headers, "a = int(input())\nprint(a + bb)\n")
    fixed = submit(client, qid, headers, "a = int(input())\nprint(a + 1)\n")
    assert typo["counted"] and fixed["counted"]
    assert fixed["hint_state"]["counted_attempts"] == 2


def test_looser_threshold_runs_but_doesnt_count(live, judge_calls):
    client, qid, headers = live
    store.update_question(qid, {"hint_policy": {"free_attempts": 1, "unlock": "attempt", "duplicate_similarity": 0.9}})
    submit(client, qid, headers, WRONG_A)
    near = submit(client, qid, headers, WRONG_A.replace("+ 1", "+ 2"))
    assert len(judge_calls) == 2  # it ran: different code may give a different result
    assert near["counted"] is False and near["not_counted_reason"] == "similar" and near["submission_id"] is None
    assert near["hint_state"]["counted_attempts"] == 1
    dup = store.duplicates(qid, "Ada")[-1]
    assert dup["kind"] == "similar" and 0.9 <= dup["similarity"] < 1 and dup["result"]
