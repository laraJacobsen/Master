#!/usr/bin/env python3
"""Creates a lecture of longer tasks that read their data from files:
"[Demo] Working with files".

Five Python tasks, each with an example test students can see and three graded
tests that use their own data files (generated here, deterministically). The
expected outputs come from running each task's reference solution on that test's
files, and every task then goes through the app's own validation (the reference
solution is run on Judge0 against every test) exactly as if a lecturer had
written it on the setup page -- so this needs Judge0 running (JUDGE0_BASE_URL,
default http://localhost:2358).

The lecture is left in setup: open the lobby from the lecturer pages when you're
ready to run it. Each task comes with its own starter code (the question's
starter_code, what a lecturer writes under "Starter code" on the setup page):
helper functions that read that task's files, so students start from the data
instead of from file handling.

Usage:
    python3 seed_file_lecture.py                      # backend/prototype.db
    python3 seed_file_lecture.py --finish-active      # end a running lecture first
    python3 seed_file_lecture.py --update-drafts      # the lecture exists already: update
                                                      # its tasks that haven't started
    python3 seed_file_lecture.py --db path/to/other.db

Backs the database up next to itself before touching it.
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
SEED = 20261116
LABEL = "[Demo] Working with files"

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


PATHS = ["/", "/index.html", "/login", "/api/items", "/api/items/42", "/search", "/static/app.js", "/checkout"]


def access_log(rng, n):
    lines = []
    t = rng.randint(7, 9) * 3600 + rng.randint(0, 3599)
    for _ in range(n):
        t += rng.randint(5, 900)
        h, m, s = t // 3600 % 24, t // 60 % 60, t % 60
        status = rng.choices([200, 201, 301, 304, 400, 401, 404, 500, 503], [50, 6, 4, 8, 3, 3, 9, 3, 2])[0]
        method = "POST" if rng.random() < 0.2 else "GET"
        lines.append(f"2026-11-03 {h:02d}:{m:02d}:{s:02d} {method} {rng.choice(PATHS)} {status} {rng.randint(3, 2400)}")
    return {"access.log": "\n".join(lines) + "\n"}


ITEMS = ["bolts", "brackets", "cable", "drill bits", "gloves", "hinges", "nails", "paint", "screws", "tape", "washers"]


def warehouse(rng, items, orders):
    chosen = sorted(rng.sample(ITEMS, items))
    stock = {it: rng.randint(5, 80) for it in chosen}
    lines = ["item,quantity,minimum"] + [f"{it},{q},{rng.randint(10, 40)}" for it, q in stock.items()]
    order_lines = [f"{rng.choice(chosen)};{rng.randint(1, 25)}" for _ in range(orders)]
    return {"stock.csv": "\n".join(lines) + "\n", "orders.txt": "\n".join(order_lines) + "\n"}


VOCAB = ("the a of and to in is it that data file line read loop list each value program student "
         "test output input number word count python code error string print result simple fast").split()
STOP = ["the", "a", "of", "and", "to", "in", "is", "it", "that"]


def essay(rng, sentences):
    out = []
    for _ in range(sentences):
        words = [rng.choice(VOCAB) for _ in range(rng.randint(5, 14))]
        if rng.random() < 0.3:
            words[0] = words[0].capitalize()
        sentence = " ".join(words)
        if rng.random() < 0.25:
            i = rng.randrange(1, len(words))
            sentence = sentence.replace(" " + words[i] + " ", " " + words[i].upper() + ", ", 1)
        out.append(sentence + rng.choice([".", ".", "!", "?"]))
    text = ""
    for i, s in enumerate(out):
        text += s + ("\n" if i % 3 == 2 else " ")
    return {"essay.txt": text.strip() + "\n", "stopwords.txt": "\n".join(STOP) + "\n"}


def maze(rng, rows, cols, wall_p, block=False):
    grid = [["#" if rng.random() < wall_p else "." for _ in range(cols)] for _ in range(rows)]
    grid[0][0], grid[rows - 1][cols - 1] = "S", "E"
    if block:  # a full wall column -- no way through
        c = cols // 2
        for r in range(rows):
            grid[r][c] = "#"
    return {"maze.txt": f"{rows} {cols}\n" + "\n".join("".join(r) for r in grid) + "\n"}


# ------------------------------------------------------------------ The tasks
#
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
        "title": "Server log report",
        "duration": 20 * 60,
        "prompt": """access.log is a web server's log for one day. Each line is one request:

    2026-11-03 09:14:22 GET /login 200 37

date, time, method, path, status code, and how many milliseconds the request took.

Print exactly four lines:
    requests <how many requests there were>
    errors <how many had a status code of 400 or more>
    busiest <the hour with the most requests, as HH:00> <its number of requests>
    slowest <the path of the slowest request> <its milliseconds>

If two hours have the same number of requests, pick the earlier one. If two requests are equally slow, pick the one that comes first in the file.

Your starter code already reads the log: requests is a list with one dictionary per request, e.g. {"time": "09:14:22", "method": "GET", "path": "/login", "status": 200, "ms": 37}.""",
        "starter": r'''def read_requests(name="access.log"):
    """Every request in the log, in order, as a dictionary with the keys
    "time" (like "09:14:22"), "method", "path", "status" (int) and "ms" (int)."""
    requests = []
    with open(name) as f:
        for line in f:
            if line.strip():
                date, time, method, path, status, ms = line.split()
                requests.append({"time": time, "method": method, "path": path,
                                 "status": int(status), "ms": int(ms)})
    return requests


requests = read_requests()

''',
        "solution": r'''per_hour = {}
for r in requests:
    hour = r["time"][:2]
    per_hour[hour] = per_hour.get(hour, 0) + 1
busiest = min(per_hour, key=lambda h: (-per_hour[h], h))
slowest = requests[0]
for r in requests:
    if r["ms"] > slowest["ms"]:
        slowest = r
print("requests", len(requests))
print("errors", sum(1 for r in requests if r["status"] >= 400))
print(f"busiest {busiest}:00 {per_hour[busiest]}")
print("slowest", slowest["path"], slowest["ms"])
''',
        "tests": lambda rng: [access_log(rng, 12), access_log(rng, 60), access_log(rng, 150), access_log(rng, 3)],
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
    {
        "title": "Most used words",
        "duration": 20 * 60,
        "prompt": """essay.txt is a short text. stopwords.txt lists words to ignore, one per line ("the", "a", ...).

Find the five most used words in the essay that aren't stop words, and print each as "<word> <count>", most used first. If two words are used equally often, put them in alphabetical order.

Words are compared in lowercase, and the punctuation . , ! ? around them doesn't count: "Data," and "data" are the same word. If there are fewer than five different words left, print them all.

Your starter code already reads both files: essay is the whole text as one string, and stop_words is a list of the words to ignore.""",
        "starter": r'''def read_text(name):
    """The whole file as one string."""
    with open(name) as f:
        return f.read()


essay = read_text("essay.txt")
stop_words = read_text("stopwords.txt").split()

''',
        "solution": r'''counts = {}
for raw in essay.split():
    word = raw.strip(".,!?").lower()
    if word and word not in stop_words:
        counts[word] = counts.get(word, 0) + 1
for word in sorted(counts, key=lambda w: (-counts[w], w))[:5]:
    print(word, counts[word])
''',
        "tests": lambda rng: [essay(rng, 4), essay(rng, 12), essay(rng, 30), essay(rng, 2)],
    },
    {
        "title": "Escape the maze",
        "duration": 25 * 60,
        "prompt": """maze.txt is a maze. The first line is its size, "rows cols". Then one line per row:

    S..#
    .#..
    ...E

S is where you start, E is the exit, # is a wall, and . is open floor. Each step moves one square up, down, left or right -- never diagonally, never through a wall, never off the edge.

Print the smallest number of steps from S to E, or "no path" if the exit can't be reached.

Your starter code already reads the file: maze is a list of strings, one per row, so maze[row][col] is the square at that position, and rows and cols are its size.

Hint: a breadth-first search finds the shortest path. Keep a queue of squares to visit and how many steps it took to get to each, and never visit a square twice.""",
        "starter": r'''def read_maze(name="maze.txt"):
    """The maze as a list of strings, one per row: maze[row][col] is "S", "E", "#" or ".".
    The size line at the top of the file is skipped."""
    with open(name) as f:
        lines = f.read().splitlines()
    return [line for line in lines[1:] if line]


maze = read_maze()
rows, cols = len(maze), len(maze[0])

''',
        "solution": r'''from collections import deque

start = next((r, c) for r in range(rows) for c in range(cols) if maze[r][c] == "S")
seen = {start}
queue = deque([(start, 0)])
answer = "no path"
while queue:
    (r, c), steps = queue.popleft()
    if maze[r][c] == "E":
        answer = steps
        break
    for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
        if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] != "#" and (nr, nc) not in seen:
            seen.add((nr, nc))
            queue.append(((nr, nc), steps + 1))
print(answer)
''',
        "tests": lambda rng: [
            {"maze.txt": "3 4\nS..#\n.#..\n...E\n"},
            maze(rng, 8, 12, 0.22),
            maze(rng, 25, 40, 0.25),
            maze(rng, 10, 10, 0.1, block=True),
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


def check_or_exit(client, ok, question_id: str, title: str) -> None:
    """The app's own check: the reference solution against every test on Judge0,
    plus the starter code (see main._starter_problem)."""
    v = ok(client.post(f"/api/lecturer/questions/{question_id}/validate"))
    if not v["validated"] or v.get("starter_problem"):
        sys.exit(f'"{title}" failed validation: {v}')


def update_drafts(client, ok) -> None:
    """--update-drafts: gives the tasks of an existing copy of this lecture the
    starter code, task text and reference solution above -- only tasks that
    haven't started (a task that has run is history and can't be edited). Their
    tests are left as they are, so passing the check afterwards also shows the
    new reference solution still gives the old answers."""
    drafts = {q["title"]: q for q in ok(client.get("/api/lecturer/questions")) if q["status"] == "draft"}
    updated = 0
    for task in TASKS:
        q = drafts.get(task["title"])
        if not q:
            print(f'  {task["title"]}: already started or not there, left alone')
            continue
        ok(client.put(f"/api/lecturer/questions/{q['id']}", json={
            "prompt": task["prompt"],
            "starter_code": task["starter"],
            "reference_solution": reference(task),
        }))
        check_or_exit(client, ok, q["id"], task["title"])
        updated += 1
        print(f'  {task["title"]}: starter code added, validated on Judge0')
    print(f"\nUpdated {updated} task(s).")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(REPO / "backend" / "prototype.db"))
    ap.add_argument("--finish-active", action="store_true", help="finish a running lecture first")
    ap.add_argument("--update-drafts", action="store_true",
                    help="update the not-yet-started tasks of an existing copy of this lecture instead of creating it")
    args = ap.parse_args()

    db = Path(args.db)
    if db.exists():
        backup = db.with_name(f"{db.stem}-backup-{datetime.now():%Y-%m-%d-%H%M%S}.db")
        shutil.copy2(db, backup)
        print(f"Backed up {db.name} -> {backup.name}")

    rng = random.Random(SEED)
    built = []
    for task in TASKS:
        tests = []
        for files in task["tests"](rng):
            expected = run_reference(reference(task), files, task.get("output_file"))
            tests.append({"stdin": "", "expected_stdout": expected,
                          "files": [{"name": n, "content": c} for n, c in files.items()]})
        built.append((task, tests))

    os.environ["PROTOTYPE_DB_PATH"] = str(db)
    sys.path.insert(0, str(REPO))
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        def ok(r):
            assert r.status_code == 200, (r.request.url, r.status_code, r.text)
            return r.json()

        active = ok(client.get("/api/lecturer/lectures/active"))

        if args.update_drafts:
            if not active["lecture"] or active["lecture"]["label"] != LABEL:
                sys.exit(f'"{LABEL}" isn\'t the lecture in progress, so there are no tasks of it to update.')
            update_drafts(client, ok)
            return

        if any(l["label"] == LABEL and not l["archived"] for l in ok(client.get("/api/lecturer/lectures"))):
            sys.exit(f'"{LABEL}" already exists -- archive or delete it first to make a new one, '
                     "or rerun with --update-drafts to update its tasks that haven't started.")

        if active["lecture"]:
            if not args.finish_active:
                sys.exit(f'Lecture "{active["lecture"]["display_label"]}" is running. Finish it first, '
                         "or rerun with --finish-active.")
            ok(client.post("/api/lecturer/lecture/finish", json={"current_question_id": active["live_question_id"]}))
            print(f'Finished the running lecture "{active["lecture"]["display_label"]}"')

        lecture = ok(client.post("/api/lecturer/lectures", json={"label": LABEL}))
        for task, tests in built:
            q = ok(client.post("/api/lecturer/questions", json={
                "title": task["title"],
                "prompt": task["prompt"],
                "language": "python",
                "test_cases": tests,
                "reference_solution": reference(task),
                "starter_code": task["starter"],
                "output_file": task.get("output_file"),
                "expected_students": 24,
                "duration_seconds": task["duration"],
            }))
            check_or_exit(client, ok, q["id"], task["title"])
            sizes = ", ".join(f'{f["name"]} {len(f["content"])} B' for f in tests[2]["files"])
            print(f'  {task["title"]}: {len(tests)} tests, validated on Judge0 ({sizes} in the largest)')

        print(f'\nCreated "{LABEL}" (lecture #{lecture["id"]}), left in setup. Open its lobby from the '
              "lecturer pages to run it.")


if __name__ == "__main__":
    main()
