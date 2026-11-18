#!/usr/bin/env python3
"""Dev/demo only: a mock class that fills whatever lecture you run from the UI.

THIS IS SYNTHETIC DATA. Every program the "students" submit is written in this file.
Keep lectures run with it out of anything reported as research data (archive them
afterwards, or give them a "[Demo]" label).

Two parts:

1. The sample questions behind the setup page's "Add sample questions" button
   (frontend/src/setup/sampleQuestions.json). A mix: two Python tasks that read
   stdin, two that read data files (one graded on a file the program writes), one
   in C and one in Java. Regenerate the JSON after changing SAMPLE_TASKS with:
       python3 mock_class.py --write-samples

2. The students. Leave this running in a terminal:
       python3 mock_class.py
   Then, in the UI: "Add sample questions" -> new lecture -> open the lobby. The
   students join one by one. Every time a task goes live they start answering it:
   heartbeats while they "type", then their submissions, spread over --spread
   seconds. Each student's program is different. Per task the class covers wrong
   answers (each bug shared by 2-3 students, written differently, so discussion
   points form), syntax/compile errors, runtime errors, timeouts, hard-coded output,
   and right answers; about half of those who start wrong fix it. When the
   lecture ends the script waits for the next one, so one run covers a whole demo.

   Tasks it doesn't know (a question you typed in yourself) get a generic mix built
   from the task's reference solution.

Needs the backend (default http://localhost:8000) and Judge0 running.

Options:
    --students 14     class size (names from seed_demo_lectures.STUDENTS, max 22)
    --spread 90       seconds over which a task's submissions arrive
    --idle 0          students who join but never submit (shown as idle)
    --solve 0.5       chance a student who starts wrong ends up fixing it
    --seed N          same class behaviour every run
"""

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import seed_demo_lectures as stdin_seed  # noqa: E402
import seed_file_lecture as file_seed  # noqa: E402

SAMPLES_JSON = REPO / "frontend" / "src" / "setup" / "sampleQuestions.json"
NAMES = stdin_seed.STUDENTS
CATEGORIES = ("correct", "wrong_answer", "syntax_error", "runtime_error", "timeout")


# =============================================================== Sample questions

def _starter(title):
    return next(t for t in file_seed.TASKS if t["title"] == title)["starter"]


C_SUM_REF = """#include <stdio.h>

int main(void) {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("%d\\n", a + b);
    return 0;
}
"""

JAVA_SUM_REF = """import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int a = sc.nextInt();
        int b = sc.nextInt();
        System.out.println(a + b);
    }
}
"""

SUM_TWO_TESTS = [("3 4\n", "7"), ("10 -2\n", "8"), ("-5 -6\n", "-11"), ("0 0\n", "0"), ("120 250\n", "370")]


def _stdin_sample(key):
    ex = stdin_seed.EXERCISES[key]
    return {
        "title": ex["title"], "language": "python", "prompt": ex["prompt"],
        "reference_solution": ex["reference"], "starter_code": None, "output_file": None,
        "duration_seconds": 600,
        "test_cases": [{"stdin": i, "expected_stdout": o, "files": []} for i, o in ex["tests"]],
    }


def _file_sample(title, rng):
    task = next(t for t in file_seed.TASKS if t["title"] == title)
    ref = file_seed.reference(task)
    tests = []
    for files in task["tests"](rng):
        expected = file_seed.run_reference(ref, files, task.get("output_file"))
        tests.append({"stdin": "", "expected_stdout": expected,
                      "files": [{"name": n, "content": c} for n, c in files.items()]})
    return {
        "title": title, "language": "python", "prompt": task["prompt"], "reference_solution": ref,
        "starter_code": task["starter"], "output_file": task.get("output_file"),
        "duration_seconds": task["duration"], "test_cases": tests,
    }


def build_samples():
    rng = random.Random(20261119)
    return [
        _stdin_sample("sum"),
        _file_sample("Gradebook averages", rng),
        _stdin_sample("palindrome"),
        _file_sample("Warehouse restock", rng),
        {
            "title": "Sum two numbers (C)", "language": "c",
            "prompt": "Read two integers on one line and print their sum.",
            "reference_solution": C_SUM_REF, "starter_code": None, "output_file": None,
            "duration_seconds": 600,
            "test_cases": [{"stdin": i, "expected_stdout": o, "files": []} for i, o in SUM_TWO_TESTS],
        },
        {
            "title": "Sum two numbers (Java)", "language": "java",
            "prompt": "Read two integers on one line and print their sum. Your class must be named Main.",
            "reference_solution": JAVA_SUM_REF, "starter_code": None, "output_file": None,
            "duration_seconds": 600,
            "test_cases": [{"stdin": i, "expected_stdout": o, "files": []} for i, o in SUM_TWO_TESTS],
        },
    ]


# ==================================================================== Answer bank
#
# Per task title: programs by the category they should land in. wrong_answer is a
# list of bugs, each a list of differently written programs with the same output,
# so two students with the same bug still send different code. For the file tasks
# each entry is only what the student wrote under the starter code.

GRADEBOOK_HEAD = "by_student = {}\nfor student, subject, score in scores:\n    by_student.setdefault(student, []).append(score)\n"

BANK = {
    "Sum of integers": {
        "correct": stdin_seed.EXERCISES["sum"]["correct"] + [
            "total = 0\nfor x in input().split():\n    total = total + int(x)\nprint(total)",
            "line = input()\nnumbers = [int(n) for n in line.split()]\nprint(sum(numbers))",
        ],
        "wrong_answer": [
            ["nums = input().split()\nprint(sum(int(n) for n in nums) + 1)",
             "total = 1\nfor n in input().split():\n    total += int(n)\nprint(total)"],
            ["nums = input().split()\nprint(sum(int(n) for n in nums[:-1]))",
             "nums = [int(x) for x in input().split()]\ntotal = 0\nfor i in range(len(nums) - 1):\n    total += nums[i]\nprint(total)"],
            ["print(''.join(input().split()))",
             "nums = input().split()\nresult = ''\nfor n in nums:\n    result += n\nprint(result)"],
            ["print(sum(abs(int(x)) for x in input().split()))",
             "total = 0\nfor x in input().split():\n    total += abs(int(x))\nprint(total)"],
            ["print(6)", "print(1 + 2 + 3)"],  # hard-coded from the example
        ],
        "syntax_error": [
            "nums = input().split(\nprint(sum(int(n) for n in nums))",
            "total = 0\nfor n in input().split()\n    total += int(n)\nprint(total)",
            "total = 0\nfor n in input().split():\ntotal += int(n)\nprint(total)",
        ],
        "runtime_error": [
            "nums = input().split()\nprint(sum(int(n) for n in num))",
            "print(int(input()) + 0)",
            "nums = input().split()\ntotal = 0\nfor n in nums:\n    total += n\nprint(total)",
        ],
        "timeout": [
            "nums = [int(x) for x in input().split()]\ntotal = 0\ni = 0\nwhile i < len(nums):\n    total += nums[i]\nprint(total)",
            "nums = input().split()\ntotal = 0\nwhile nums:\n    total += int(nums[0])\nprint(total)",
        ],
    },
    "Gradebook averages": {
        "starter": _starter("Gradebook averages"),
        "correct": [
            file_seed.TASKS[0]["solution"],
            "totals = {}\ncounts = {}\nfor name, subject, score in scores:\n    totals[name] = totals.get(name, 0) + score\n"
            "    counts[name] = counts.get(name, 0) + 1\nfor name in sorted(totals):\n"
            '    print(f"{name} {totals[name] / counts[name]:.1f}")\nall_scores = [s for _, _, s in scores]\n'
            'print(f"class {sum(all_scores) / len(all_scores):.1f}")\n',
            "names = sorted(set(s[0] for s in scores))\nfor name in names:\n"
            "    marks = [score for student, _, score in scores if student == name]\n"
            '    print(f"{name} {sum(marks) / len(marks):.1f}")\n'
            'print(f"class {sum(s[2] for s in scores) / len(scores):.1f}")\n',
        ],
        "wrong_answer": [
            [  # not sorted by name
                GRADEBOOK_HEAD + 'for student in by_student:\n    marks = by_student[student]\n'
                '    print(f"{student} {sum(marks) / len(marks):.1f}")\n'
                'print(f"class {sum(s for _, _, s in scores) / len(scores):.1f}")\n',
                "totals = {}\ncounts = {}\nfor name, subject, score in scores:\n    totals[name] = totals.get(name, 0) + score\n"
                "    counts[name] = counts.get(name, 0) + 1\nfor name in totals:\n"
                '    print(f"{name} {totals[name] / counts[name]:.1f}")\n'
                'print(f"class {sum(s for _, _, s in scores) / len(scores):.1f}")\n',
            ],
            [  # integer division
                GRADEBOOK_HEAD + 'for student in sorted(by_student):\n    marks = by_student[student]\n'
                '    print(student, sum(marks) // len(marks))\nprint("class", sum(s for _, _, s in scores) // len(scores))\n',
                "names = sorted(set(s[0] for s in scores))\nfor name in names:\n"
                "    marks = [score for student, _, score in scores if student == name]\n"
                "    print(name, sum(marks) // len(marks))\nprint('class', sum(s[2] for s in scores) // len(scores))\n",
            ],
            [  # class average = average of the student averages
                GRADEBOOK_HEAD + 'avgs = []\nfor student in sorted(by_student):\n    marks = by_student[student]\n'
                '    avgs.append(sum(marks) / len(marks))\n    print(f"{student} {avgs[-1]:.1f}")\n'
                'print(f"class {sum(avgs) / len(avgs):.1f}")\n',
                GRADEBOOK_HEAD + 'averages = {s: sum(m) / len(m) for s, m in by_student.items()}\n'
                'for s in sorted(averages):\n    print(f"{s} {averages[s]:.1f}")\n'
                'print(f"class {sum(averages.values()) / len(averages):.1f}")\n',
            ],
            [  # forgets the class line
                GRADEBOOK_HEAD + 'for student in sorted(by_student):\n    marks = by_student[student]\n'
                '    print(f"{student} {sum(marks) / len(marks):.1f}")\n',
                "names = sorted(set(s[0] for s in scores))\nfor name in names:\n"
                "    marks = [score for student, _, score in scores if student == name]\n"
                '    print(f"{name} {sum(marks) / len(marks):.1f}")\n',
            ],
        ],
        "syntax_error": [
            "by_student = {}\nfor student, subject, score in scores\n    by_student.setdefault(student, []).append(score)\n",
            GRADEBOOK_HEAD + 'for student in sorted(by_student):\n    marks = by_student[student]\n'
            '    print(f"{student} {sum(marks) / len(marks):.1f})\n',
        ],
        "runtime_error": [
            "by_student = {}\nfor student, subject, score in scores:\n    by_student[student].append(score)\n"
            'for student in sorted(by_student):\n    marks = by_student[student]\n    print(f"{student} {sum(marks) / len(marks):.1f}")\n',
            GRADEBOOK_HEAD + 'for student in sorted(by_student):\n    marks = by_student[student]\n'
            '    print(student + " " + sum(marks) / len(marks))\n',
        ],
        "timeout": [
            "total = 0\ni = 0\nwhile i < len(scores):\n    total += scores[i][2]\nprint(total / len(scores))\n",
            "names = sorted(set(s[0] for s in scores))\ni = 0\nwhile i < len(names):\n"
            "    marks = [sc for st, _, sc in scores if st == names[i]]\n",
        ],
    },
    "Palindrome check": {
        "correct": stdin_seed.EXERCISES["palindrome"]["correct"] + [
            's = input().replace(" ", "").lower()\nif s == s[::-1]:\n    print(True)\nelse:\n    print(False)',
            'text = "".join(ch.lower() for ch in input() if ch != " ")\nprint(text == text[::-1])',
        ],
        "wrong_answer": [
            ['s = input().replace(" ", "")\nprint(s == s[::-1])',
             'text = "".join(input().split())\nprint(text == text[::-1])'],
            ['s = input().lower()\nprint(s == s[::-1])',
             'word = input().lower()\nprint(word[::-1] == word)'],
            ["s = input()\nprint(s == s[::-1])", "t = input()\nprint(t[::-1] == t)"],
            ['s = input().lower().replace(" ", "")\nok = True\nfor i in range(len(s) // 2):\n'
             '    if s[i] != s[len(s) - i - 2]:\n        ok = False\nprint(ok)'],
            ['s = input().lower().replace(" ", "")\nif s == s[::-1]:\n    print("yes")\nelse:\n    print("no")',
             'x = input().lower().replace(" ", "")\nprint("yes" if x == x[::-1] else "no")'],
        ],
        "syntax_error": [
            's = input().lower().replace(" ", "")\nif s == s[::-1]\n    print(True)\nelse:\n    print(False)',
            's = input().lower().replace(" ", ""\nprint(s == s[::-1])',
        ],
        "runtime_error": [
            's = input().lower().replace(" ")\nprint(s == s[::-1])',
            's = input().lower().replace(" ", "")\nok = True\nfor i in range(len(s)):\n'
            '    if s[i] != s[len(s) - i]:\n        ok = False\nprint(ok)',
        ],
        "timeout": [
            's = input().lower().replace(" ", "")\ni = 0\nok = True\nwhile i < len(s) // 2:\n'
            '    if s[i] != s[-1 - i]:\n        ok = False\nprint(ok)',
            's = input().lower().replace(" ", "")\nleft, right = 0, len(s) - 1\nwhile left < right:\n'
            '    if s[left] != s[right]:\n        break\nprint(left >= right)',
        ],
    },
    "Warehouse restock": {
        "starter": _starter("Warehouse restock"),
        "correct": [
            file_seed.TASKS[2]["solution"],
            "left = {}\nfor item in stock:\n    left[item] = stock[item][0]\nfor item, amount in orders:\n"
            "    left[item] = left[item] - amount\nlines = []\nfor item in sorted(stock):\n    minimum = stock[item][1]\n"
            "    if left[item] < minimum:\n        lines.append(item + ' ' + str(2 * minimum - left[item]))\n"
            "if not lines:\n    lines = ['nothing to restock']\nwrite_lines('restock.txt', lines)\n",
            "ordered = {}\nfor item, amount in orders:\n    ordered[item] = ordered.get(item, 0) + amount\n"
            "with open('restock.txt', 'w') as out:\n    wrote = False\n    for item in sorted(stock):\n"
            "        quantity, minimum = stock[item]\n        now = quantity - ordered.get(item, 0)\n"
            "        if now < minimum:\n            out.write(f'{item} {2 * minimum - now}\\n')\n            wrote = True\n"
            "    if not wrote:\n        out.write('nothing to restock\\n')\n",
        ],
        "wrong_answer": [
            [  # prints instead of writing restock.txt
                'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] -= amount\n'
                'for item in sorted(stock):\n    if left[item] < stock[item][1]:\n        print(item, 2 * stock[item][1] - left[item])\n',
                "left = {}\nfor item in stock:\n    left[item] = stock[item][0]\nfor item, amount in orders:\n"
                "    left[item] = left[item] - amount\nfor item in sorted(left):\n    if left[item] < stock[item][1]:\n"
                "        print(f'{item} {2 * stock[item][1] - left[item]}')\n",
            ],
            [  # checks the shelf count from before the orders
                'lines = [f"{i} {2 * m - q}" for i, (q, m) in sorted(stock.items()) if q < m]\n'
                'write_lines("restock.txt", lines or ["nothing to restock"])\n',
                "lines = []\nfor item in sorted(stock):\n    quantity, minimum = stock[item]\n    if quantity < minimum:\n"
                "        lines.append(f'{item} {2 * minimum - quantity}')\n"
                "write_lines('restock.txt', lines or ['nothing to restock'])\n",
            ],
            [  # restocks up to the minimum, not twice it
                'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] -= amount\n'
                'lines = [f"{i} {stock[i][1] - left[i]}" for i in sorted(stock) if left[i] < stock[i][1]]\n'
                'write_lines("restock.txt", lines or ["nothing to restock"])\n',
                "left = {}\nfor item in stock:\n    left[item] = stock[item][0]\nfor item, amount in orders:\n"
                "    left[item] -= amount\nlines = []\nfor item in sorted(stock):\n    if left[item] < stock[item][1]:\n"
                "        lines.append(item + ' ' + str(stock[item][1] - left[item]))\n"
                "write_lines('restock.txt', lines or ['nothing to restock'])\n",
            ],
            [  # an item ordered twice only comes off once (= instead of -=)
                'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] = stock[item][0] - amount\n'
                'lines = [f"{i} {2 * stock[i][1] - left[i]}" for i in sorted(stock) if left[i] < stock[i][1]]\n'
                'write_lines("restock.txt", lines or ["nothing to restock"])\n',
            ],
        ],
        "syntax_error": [
            'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders\n    left[item] -= amount\n',
            'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] -= amount\n'
            'lines = [f"{i} {2 * stock[i][1] - left[i]}" for i in sorted(stock) if left[i] < stock[i][1]\n'
            'write_lines("restock.txt", lines)\n',
        ],
        "runtime_error": [
            "for item, amount in orders:\n    stock[item] -= amount\n",
            "for item, amount, extra in orders:\n    print(item, amount)\n",
        ],
        "timeout": [
            "left = {item: q for item, (q, m) in stock.items()}\ni = 0\nwhile i < len(orders):\n"
            "    item, amount = orders[i]\n    left[item] -= amount\n",
            "remaining = list(orders)\nleft = {item: q for item, (q, m) in stock.items()}\nwhile remaining:\n"
            "    item, amount = remaining[0]\n    left[item] -= amount\n",
        ],
    },
    "Sum two numbers (C)": {
        "correct": [
            C_SUM_REF,
            '#include <stdio.h>\n\nint main() {\n    int x, y;\n    scanf("%d%d", &x, &y);\n    int sum = x + y;\n'
            '    printf("%d\\n", sum);\n    return 0;\n}\n',
            '#include <stdio.h>\n\nint main(void)\n{\n    long a, b;\n    if (scanf("%ld %ld", &a, &b) != 2) return 1;\n'
            '    printf("%ld\\n", a + b);\n}\n',
        ],
        "wrong_answer": [
            ['#include <stdio.h>\n\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    printf("%d\\n", a - b);\n    return 0;\n}\n',
             '#include <stdio.h>\n\nint main() {\n    int x, y;\n    scanf("%d %d", &x, &y);\n    int result = x - y;\n    printf("%d\\n", result);\n}\n'],
            ['#include <stdio.h>\n\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    printf("%d %d\\n", a, b);\n    return 0;\n}\n',
             '#include <stdio.h>\n\nint main() {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    printf("%d", a);\n    printf(" %d\\n", b);\n}\n'],
            ['#include <stdio.h>\n\nint main(void) {\n    unsigned int a, b;\n    scanf("%u %u", &a, &b);\n    printf("%u\\n", a + b);\n    return 0;\n}\n',
             '#include <stdio.h>\n\nint main() {\n    unsigned a, b;\n    scanf("%d %d", &a, &b);\n    unsigned s = a + b;\n    printf("%u\\n", s);\n}\n'],
        ],
        "syntax_error": [
            '#include <stdio.h>\n\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b)\n    printf("%d\\n", a + b);\n    return 0;\n}\n',
            '#include <stdio.h>\n\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    printf("%d\\n", sum);\n    return 0;\n}\n',
            '#include <stdio.h>\n\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    printf("%d\\n", a + b);\n    return 0;\n',
        ],
        "runtime_error": [
            '#include <stdio.h>\n\nint main(void) {\n    int *a = NULL, b;\n    scanf("%d %d", a, &b);\n    printf("%d\\n", *a + b);\n    return 0;\n}\n',
            '#include <stdio.h>\n\nint add(int a, int b) {\n    return add(a, b);\n}\n\nint main(void) {\n    int a, b;\n'
            '    scanf("%d %d", &a, &b);\n    printf("%d\\n", add(a, b));\n    return 0;\n}\n',
        ],
        "timeout": [
            '#include <stdio.h>\n\nint main(void) {\n    int a, b, i = 0;\n    scanf("%d %d", &a, &b);\n    while (i != b) {\n'
            '        a++;\n        i++;\n    }\n    printf("%d\\n", a);\n    return 0;\n}\n',
            '#include <stdio.h>\n\nint main(void) {\n    int a, b;\n    scanf("%d %d", &a, &b);\n    int sum = a;\n'
            '    for (int i = 0; i != b; i++) sum++;\n    printf("%d\\n", sum);\n    return 0;\n}\n',
        ],
    },
    "Sum two numbers (Java)": {
        "correct": [
            JAVA_SUM_REF,
            "import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner in = new Scanner(System.in);\n        int sum = in.nextInt() + in.nextInt();\n"
            "        System.out.println(sum);\n    }\n}\n",
            "import java.io.*;\n\npublic class Main {\n    public static void main(String[] args) throws IOException {\n"
            "        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n"
            "        String[] parts = br.readLine().trim().split(\" \");\n"
            "        System.out.println(Integer.parseInt(parts[0]) + Integer.parseInt(parts[1]));\n    }\n}\n",
        ],
        "wrong_answer": [
            ["import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
             "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt();\n        int b = sc.nextInt();\n"
             "        System.out.println(a - b);\n    }\n}\n",
             "import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n"
             "        Scanner s = new Scanner(System.in);\n        int x = s.nextInt(), y = s.nextInt();\n"
             "        int diff = x - y;\n        System.out.println(diff);\n    }\n}\n"],
            ["import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
             "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt();\n        int b = sc.nextInt();\n"
             "        System.out.println(\"\" + a + b);\n    }\n}\n",
             "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
             "        Scanner sc = new Scanner(System.in);\n        String a = sc.next();\n        String b = sc.next();\n"
             "        System.out.println(a + b);\n    }\n}\n"],
            ["import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
             "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt();\n        int b = sc.nextInt();\n"
             "        System.out.println(\"Sum: \" + (a + b));\n    }\n}\n",
             "import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n"
             "        Scanner in = new Scanner(System.in);\n        int a = in.nextInt();\n        int b = in.nextInt();\n"
             "        System.out.printf(\"Sum: %d%n\", a + b);\n    }\n}\n"],
        ],
        "syntax_error": [
            "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt()\n        int b = sc.nextInt();\n"
            "        System.out.println(a + b);\n    }\n}\n",
            "public class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt();\n        int b = sc.nextInt();\n"
            "        System.out.println(a + b);\n    }\n}\n",
            "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextLine();\n        int b = sc.nextInt();\n"
            "        System.out.println(a + b);\n    }\n}\n",
        ],
        "runtime_error": [
            "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        int both = Integer.parseInt(sc.nextLine());\n"
            "        System.out.println(both);\n    }\n}\n",
            "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        String[] parts = sc.nextLine().split(\",\");\n"
            "        System.out.println(Integer.parseInt(parts[0]) + Integer.parseInt(parts[1]));\n    }\n}\n",
        ],
        "timeout": [
            "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt();\n        int b = sc.nextInt();\n"
            "        while (b != 0) {\n            a++;\n        }\n"
            "        System.out.println(a);\n    }\n}\n",
            "import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n        int a = sc.nextInt();\n        int b = sc.nextInt();\n"
            "        long sum = a;\n        for (long i = 0; i != b; i++) {\n            sum++;\n        }\n"
            "        System.out.println(sum);\n    }\n}\n",
        ],
    },
}


def fallback_bank(question):
    """A generic mix for a task this file doesn't know, from its reference solution."""
    ref = question.get("reference_solution") or ""
    lang = question["language"]
    if lang != "python":
        broken = ref.rstrip().rstrip("}")  # drops the last closing brace: compile error
        return {"correct": [ref], "syntax_error": [broken], "wrong_answer": [], "runtime_error": [], "timeout": []}
    starter = question.get("starter_code") or ""
    body = ref[len(starter):] if starter and ref.startswith(starter) else ref
    return {
        "starter": starter if body != ref else "",
        "correct": [body],
        "syntax_error": [body.rstrip() + "\nprint(\"done\"\n", "if True\n    pass\n" + body],
        "runtime_error": ["values = []\nprint(values[0])\n" + body, "print(undefined_name)\n" + body],
        "timeout": ["while True:\n    pass\n" + body],
        "wrong_answer": [],
    }


# ====================================================================== Planning

COMMENTS = {
    "python": ["# first try", "# I think this works", "# TODO tidy up", "# fixed?", "# try again",
               "# done", "# works on the example", "# hmm", "# second go", "# check this"],
    "c": ["// first try", "// I think this works", "// TODO tidy up", "// fixed?", "// try again",
          "// done", "// works on the example", "// hmm", "// second go", "// check this"],
}
COMMENTS["java"] = COMMENTS["c"]

# The first-attempt mix, cycled for bigger classes: 14 students -> 5 wrong answers,
# 2 syntax, 2 runtime, 2 timeouts, 3 right first time.
FIRST_MIX = ["wrong_answer", "syntax_error", "runtime_error", "correct", "wrong_answer", "timeout",
             "wrong_answer", "runtime_error", "syntax_error", "correct", "wrong_answer", "timeout",
             "correct", "wrong_answer"]


class Picker:
    """Hands out programs for one task so no two submissions have the same text."""

    def __init__(self, bank, language, rng):
        self.bank, self.rng = bank, rng
        self.starter = bank.get("starter") or ""
        self.comments = COMMENTS.get(language, COMMENTS["python"])
        self.used = set()
        self.next_variant = {}
        self.bugs = [b for b in bank["wrong_answer"] if b]
        rng.shuffle(self.bugs)

    def has(self, category):
        return bool(self.bugs) if category == "wrong_answer" else bool(self.bank.get(category))

    def _unique(self, body):
        code = self.starter + body
        extra = 0
        while code in self.used:
            note = self.comments[extra % len(self.comments)]
            if extra >= len(self.comments):
                note += f" ({extra // len(self.comments) + 1})"
            code = self.starter + body.rstrip("\n") + "\n" + note + "\n"
            extra += 1
        self.used.add(code)
        return code

    def program(self, category, bug_index=None):
        if category == "wrong_answer":
            options = self.bugs[bug_index % len(self.bugs)]
            key = ("bug", bug_index % len(self.bugs))
        else:
            options = self.bank[category]
            key = category
        i = self.next_variant.get(key, self.rng.randrange(len(options)))
        self.next_variant[key] = i + 1
        return self._unique(options[i % len(options)])


def plan_class(students, picker, rng, idle, solve=0.5):
    """{student: [program, ...]} for one task. First attempts follow FIRST_MIX (with
    categories the task has no programs for swapped for wrong answers); wrong answers
    go out two students per bug, so each bug forms a discussion point."""
    order = list(students)
    rng.shuffle(order)
    idle_students = set(order[:idle])
    working = order[idle:]
    firsts = [FIRST_MIX[i % len(FIRST_MIX)] for i in range(len(working))]
    firsts = [c if picker.has(c) else ("wrong_answer" if picker.has("wrong_answer") else "correct") for c in firsts]
    rng.shuffle(firsts)

    plans, wrong_seen = {s: [] for s in idle_students}, 0
    for student, first in zip(working, firsts):
        attempts = []
        if first == "wrong_answer":
            attempts.append(picker.program("wrong_answer", wrong_seen // 2))
            wrong_seen += 1
        else:
            attempts.append(picker.program(first))
        if first != "correct":
            # A second mistake for some (usually one of the common bugs), then most fix it.
            if rng.random() < 0.4 and picker.has("wrong_answer"):
                attempts.append(picker.program("wrong_answer", rng.randrange(max(1, (wrong_seen + 1) // 2))))
            if rng.random() < solve:
                attempts.append(picker.program("correct"))
        plans[student] = attempts
    return plans


# ===================================================================== Running it

class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def __call__(self, method, path, **kw):
        r = requests.request(method, self.base + path, timeout=120, **kw)
        if r.status_code != 200:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def student_works(api, qid, name, attempts, spread, rng, stop, results):
    """One student on one task: heartbeats every 10 s while working, submissions spread out."""
    t = rng.uniform(8, max(10, spread * 0.55))
    times = []
    for _ in attempts:
        times.append(min(t, spread))
        t += rng.uniform(15, 40)
    pending = list(zip(times, attempts))
    start = time.monotonic()
    last_beat = -10.0
    while not stop.is_set():
        now = time.monotonic() - start
        if now - last_beat >= 10:
            last_beat = now
            try:
                api("POST", "/api/lecture/activity", json={
                    "student_name": name, "question_id": qid, "edited": bool(pending) and rng.random() < 0.8})
            except Exception:
                pass
        if pending and now >= pending[0][0]:
            _, code = pending.pop(0)
            try:
                r = api("POST", "/api/submit", json={"student_name": name, "question_id": qid, "source_code": code})
                detail = api("GET", f"/api/lecturer/submissions/{r['submission_id']}")
                results.append((name, detail.get("exec_verdict") or r.get("verdict")))
            except RuntimeError as e:
                if "409" in str(e):
                    return  # the task closed
                log(f"  {name}: submit failed: {e}")
        if attempts and not pending and now - last_beat >= 9:
            return  # done; stop heartbeating once the last one is through
        stop.wait(1)


def join_students(api, lecture, students, gap):
    code = lecture["join_code"]
    for name in students:
        try:
            api("POST", "/api/lecture/join", json={"code": code, "student_name": name})
        except RuntimeError as e:
            log(f"  {name} couldn't join: {e}")
            return
        time.sleep(gap * random.uniform(0.4, 1.6))
    log(f'All {len(students)} students are in "{lecture.get("display_label") or lecture.get("label")}"')


def run(api, args, rng):
    students = rng.sample(NAMES, min(args.students, len(NAMES)))
    joined_lecture, current_q, stop = None, None, threading.Event()
    log(f"Waiting for a lecture to open its lobby ({len(students)} students ready). Ctrl-C to stop.")
    while True:
        try:
            active = api("GET", "/api/lecturer/lectures/active")
            status = api("GET", "/api/lecture/status")
        except Exception as e:
            log(f"Backend not reachable ({e}); retrying")
            time.sleep(5)
            continue

        lecture = active.get("lecture")
        if lecture and lecture.get("lobby_opened_at") and lecture["id"] != joined_lecture:
            joined_lecture = lecture["id"]
            current_q = None
            log(f'Lobby open for lecture #{lecture["id"]} (code {lecture["join_code"]}): students joining')
            threading.Thread(target=join_students, args=(api, lecture, students, args.join_gap), daemon=True).start()
        if not lecture and joined_lecture is not None:
            stop.set()
            log("Lecture finished. Waiting for the next one.")
            joined_lecture, current_q = None, None

        q = status.get("question")
        live_id = q["id"] if q and q.get("seconds_remaining", 0) > 0 and joined_lecture else None
        if live_id != current_q:
            stop.set()
            stop = threading.Event()
            current_q = live_id
            if live_id:
                start_task(api, live_id, students, args, rng, stop)
        time.sleep(2)


def start_task(api, qid, students, args, rng, stop):
    question = api("GET", f"/api/lecturer/questions/{qid}")
    bank = BANK.get(question["title"])
    known = bank is not None
    bank = bank or fallback_bank(question)
    picker = Picker(bank, question["language"], random.Random(rng.random()))
    plans = plan_class(students, picker, random.Random(rng.random()), args.idle, args.solve)
    n_sub = sum(len(p) for p in plans.values())
    log(f'"{question["title"]}" is live: {n_sub} submissions coming from {len(students)} students'
        + ("" if known else " (unknown task: generic mix)"))
    results = []
    threads = []
    for name, attempts in plans.items():
        th = threading.Thread(target=student_works, daemon=True, args=(
            api, qid, name, attempts, args.spread, random.Random(rng.random()), stop, results))
        th.start()
        threads.append(th)

    def report():
        for th in threads:
            th.join()
        if results and not stop.is_set():
            counts = {}
            for _, v in results:
                counts[v] = counts.get(v, 0) + 1
            log(f'  "{question["title"]}": all submitted -- ' + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    threading.Thread(target=report, daemon=True).start()


def write_samples():
    samples = build_samples()
    SAMPLES_JSON.write_text(json.dumps(samples, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(samples)} sample questions to {SAMPLES_JSON.relative_to(REPO)}")
    missing = [s["title"] for s in samples if s["title"] not in BANK]
    if missing:
        print("No answer bank for:", ", ".join(missing))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--students", type=int, default=14)
    ap.add_argument("--spread", type=float, default=90, help="seconds over which a task's submissions arrive")
    ap.add_argument("--idle", type=int, default=0, help="students who join but never submit")
    ap.add_argument("--solve", type=float, default=0.5,
                    help="chance a student who starts wrong fixes it (3 in 14 are right first time anyway)")
    ap.add_argument("--join-gap", type=float, default=0.8, help="average seconds between two students joining")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--write-samples", action="store_true", help="regenerate the setup page's sample questions")
    args = ap.parse_args()
    if args.write_samples:
        write_samples()
        return
    try:
        run(Api(args.base), args, random.Random(args.seed))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
