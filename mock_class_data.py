"""Fixed data for mock_class.py: the class roster and the sample tasks it builds
questions and answers from. (Kept from the old seed_demo_lectures.py and
seed_file_lecture.py scripts, which are gone.)"""

import subprocess
import sys
import tempfile
from pathlib import Path

DEMO_PREFIX = "[Demo] "

# One cohort, the same students every week (so per-student recaps make sense too).
STUDENTS = [
    "Amalie", "Bjørn", "Camilla", "Daniel", "Emma", "Filip", "Guro", "Henrik", "Ingrid",
    "Jonas", "Karoline", "Lars", "Maja", "Nikolai", "Olivia", "Petter", "Ragnhild",
    "Sindre", "Thea", "Ulrik", "Vilde", "William",
]

# Stdin exercises. "correct" lists differently written right answers.
EXERCISES = {
    "sum": {
        "title": "Sum of integers",
        "prompt": "Read a line of space-separated integers and print their sum.",
        "reference": "print(sum(int(x) for x in input().split()))",
        "tests": [("1 2 3\n", "6"), ("10 20 30 40\n", "100"), ("-5 5\n", "0"), ("7\n", "7")],
        "correct": [
            "print(sum(int(x) for x in input().split()))",
            "nums = input().split()\ntotal = 0\nfor n in nums:\n    total += int(n)\nprint(total)",
            "print(sum(map(int, input().split())))",
        ],
    },
    "palindrome": {
        "title": "Palindrome check",
        "prompt": "Read a line and print True if it reads the same backwards, ignoring case and spaces, else False.",
        "reference": 's = input().lower().replace(" ", "")\nprint(s == s[::-1])',
        "tests": [("Race car\n", "True"), ("hello\n", "False"), ("Was it a car or a cat I saw\n", "True"),
                  ("ab\n", "False")],
        "correct": [
            's = input().lower().replace(" ", "")\nprint(s == s[::-1])',
            't = "".join(input().split()).lower()\nprint(t == "".join(reversed(t)))',
        ],
    },
}


# ----------------------------------------------------------------- Data makers

FIRST_NAMES = ["Amalie", "Bjørn", "Camilla", "Daniel", "Emma", "Filip", "Guro", "Henrik", "Ingrid", "Jonas",
               "Karoline", "Lars", "Maja", "Nikolai", "Olivia", "Petter"]
SUBJECTS = ["maths", "physics", "programming", "statistics", "databases"]


def gradebook(rng, students, rows):
    names = rng.sample(FIRST_NAMES, students)
    lines = ["student,subject,score"]
    for _ in range(rows):
        lines.append(f"{rng.choice(names)},{rng.choice(SUBJECTS)},{rng.randint(35, 100)}")
    return {"grades.csv": "\n".join(lines) + "\n"}


ITEMS = ["bolts", "brackets", "cable", "drill bits", "gloves", "hinges", "nails", "paint", "screws", "tape", "washers"]


def warehouse(rng, items, orders):
    chosen = sorted(rng.sample(ITEMS, items))
    stock = {it: rng.randint(5, 80) for it in chosen}
    lines = ["item,quantity,minimum"] + [f"{it},{q},{rng.randint(10, 40)}" for it, q in stock.items()]
    order_lines = [f"{rng.choice(chosen)};{rng.randint(1, 25)}" for _ in range(orders)]
    return {"stock.csv": "\n".join(lines) + "\n", "orders.txt": "\n".join(order_lines) + "\n"}


# Each task's "starter" is what students find in their editor (the question's
# starter_code): helper functions that do the file handling for that task, and
# a line or two that call them. "solution" is the rest of a correct program.
# The reference solution is the two together -- exactly what a student could
# submit -- so validating it also proves the helpers work.

TASKS = [
    {
        "title": "Gradebook averages",
        "duration": 15 * 60,
        "prompt": """grades.csv holds every score from this term, one per line, after a header line:

    student,subject,score
    Emma,maths,78

A student can have many scores, in any order, across any subjects.

Print one line per student, sorted by name: the name and their average score with one decimal, e.g. "Emma 81.5". Then a last line "class" followed by the average of every score in the file, also with one decimal.

Your starter code already reads the file: scores is a list of (student, subject, score), with the header skipped and each score as a number. Round the usual way with an f-string, e.g. f"{avg:.1f}".""",
        "starter": r'''def read_scores(name="grades.csv"):
    """Every score in the file as (student, subject, score).
    The header line is skipped and score is an int."""
    rows = []
    with open(name) as f:
        next(f)  # the header line
        for line in f:
            if line.strip():
                student, subject, score = line.strip().split(",")
                rows.append((student, subject, int(score)))
    return rows


scores = read_scores()

''',
        "solution": r'''by_student = {}
for student, subject, score in scores:
    by_student.setdefault(student, []).append(score)
for student in sorted(by_student):
    marks = by_student[student]
    print(f"{student} {sum(marks) / len(marks):.1f}")
print(f"class {sum(score for _, _, score in scores) / len(scores):.1f}")
''',
        "tests": lambda rng: [gradebook(rng, 3, 7), gradebook(rng, 6, 30), gradebook(rng, 10, 80), gradebook(rng, 1, 4)],
    },
    {
        "title": "Warehouse restock",
        "duration": 20 * 60,
        "output_file": "restock.txt",
        "prompt": """A warehouse needs to know what to reorder. Two files:

stock.csv -- what's on the shelves, after a header line:
    item,quantity,minimum
    bolts,40,25

orders.txt -- today's orders, one per line, as item;amount:
    bolts;12

Take every order off the stock (an item can be ordered many times). Then every item whose quantity is now below its minimum needs restocking up to twice its minimum: for those, write "<item> <how many to order>" to restock.txt, one per line, sorted by item name. Item names can contain spaces.

If nothing needs restocking, write the single line "nothing to restock".

restock.txt is what's checked, not what your program prints -- print as much as you like while you work.

Your starter code already reads both files: stock is a dictionary {item: (quantity, minimum)} and orders is a list of (item, amount). It also gives you write_lines("restock.txt", lines) to write a list of strings to the file, one per line.""",
        "starter": r'''def read_stock(name="stock.csv"):
    """What's on the shelves, as {item: (quantity, minimum)}. The header line is skipped."""
    stock = {}
    with open(name) as f:
        next(f)  # the header line
        for line in f:
            if line.strip():
                item, quantity, minimum = line.strip().split(",")
                stock[item] = (int(quantity), int(minimum))
    return stock


def read_orders(name="orders.txt"):
    """Today's orders as (item, amount), in the order they came in."""
    orders = []
    with open(name) as f:
        for line in f:
            if line.strip():
                item, amount = line.strip().split(";")
                orders.append((item, int(amount)))
    return orders


def write_lines(name, lines):
    """Writes each string in lines to the file, one per line."""
    with open(name, "w") as f:
        for line in lines:
            f.write(line + "\n")


stock = read_stock()
orders = read_orders()

''',
        "solution": r'''left = {item: quantity for item, (quantity, minimum) in stock.items()}
for item, amount in orders:
    left[item] -= amount
lines = [f"{item} {2 * stock[item][1] - left[item]}" for item in sorted(stock) if left[item] < stock[item][1]]
write_lines("restock.txt", lines or ["nothing to restock"])
''',
        "tests": lambda rng: [
            {  # The example students see: written out so every rule shows up in it.
                "stock.csv": "item,quantity,minimum\nbolts,40,25\ncable,12,15\nscrews,60,20\ntape,30,10\n",
                "orders.txt": "bolts;12\nscrews;45\nbolts;9\ntape;4\n",
            },
            warehouse(rng, 7, 20),
            warehouse(rng, 11, 45),
            warehouse(rng, 3, 0),
        ],
    },
]


def reference(task: dict) -> str:
    return task["starter"] + task["solution"]


# ----------------------------------------------------------------------- Run

def run_reference(source: str, files: dict, output_file: str | None) -> str:
    """The reference solution's answer on one test's files (stdout, or the output file)."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            Path(tmp, name).write_text(content)
        proc = subprocess.run([sys.executable, "-c", source], cwd=tmp, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(f"reference solution failed:\n{proc.stderr}")
        return Path(tmp, output_file).read_text() if output_file else proc.stdout

