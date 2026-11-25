import type { ClusterRow, ProgressResponse, QuestionRow, StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import { DEFAULT_HINT_POLICY } from "../shared/hintPolicy";

// Fake data for previewing the live dashboard without a backend:
// lecturer.html?question_id=mock&mock. Nothing here is sent anywhere.

const REFERENCE = `def is_balanced(s):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack

print(is_balanced(input()))`;

const NO_MATCH = `def is_balanced(s):
    stack = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack:
                return False
            stack.pop()
    return not stack

print(is_balanced(input()))`;

const COUNTING = `def is_balanced(s):
    opens = s.count("(") + s.count("[") + s.count("{")
    closes = s.count(")") + s.count("]") + s.count("}")
    return opens == closes

print(is_balanced(input()))`;

const INDEX_ERROR = `def is_balanced(s):
    stack = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        else:
            if stack[-1] == "(" and ch == ")":
                stack.pop()
    return len(stack) == 0

print(is_balanced(input()))`;

const TIMEOUT = `def is_balanced(s):
    while "()" in s or "[]" in s:
        s.replace("()", "").replace("[]", "")
    return s == ""

print(is_balanced(input()))`;

const SYNTAX = `def is_balanced(s)
    stack = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
    return not stack

print(is_balanced(input()))`;

const NAMES = [
  "Ada", "Bjørn", "Camille", "Dev", "Emma", "Farid", "Greta", "Hiro", "Ingrid", "Jonas",
  "Kari", "Leo", "Maja", "Nils", "Olivia", "Per", "Quinn", "Rania", "Sofie", "Tobias",
  "Una", "Viktor", "Wen", "Ximena", "Yusuf", "Zara",
];

type Kind = "correct" | "no_match" | "counting" | "index_error" | "timeout" | "syntax";

const KIND: Record<Kind, { code: string; verdict: Verdict; exec: string; error_type: string | null; passed: number; stdout: string; stderr?: string }> = {
  correct: { code: REFERENCE, verdict: "correct", exec: "pass", error_type: null, passed: 5, stdout: "False" },
  no_match: { code: NO_MATCH, verdict: "partially_correct", exec: "wrong_answer", error_type: null, passed: 3, stdout: "True" },
  counting: { code: COUNTING, verdict: "partially_correct", exec: "wrong_answer", error_type: null, passed: 2, stdout: "True" },
  index_error: {
    code: INDEX_ERROR,
    verdict: "error",
    exec: "runtime_error",
    error_type: "IndexError",
    passed: 0,
    stdout: "",
    stderr: 'Traceback (most recent call last):\n  File "main.py", line 7, in is_balanced\n    if stack[-1] == "(" and ch == ")":\nIndexError: list index out of range',
  },
  syntax: {
    code: SYNTAX,
    verdict: "error",
    exec: "syntax_error",
    error_type: null,
    passed: 0,
    stdout: "",
    stderr: '  File "main.py", line 1\n    def is_balanced(s)\n                      ^\nSyntaxError: expected \':\'',
  },
  timeout: { code: TIMEOUT, verdict: "error", exec: "timeout", error_type: null, passed: 0, stdout: "" },
};

// Each student's attempts, oldest first. The last 4 haven't submitted yet.
const PLAN: Kind[][] = [
  ["correct"], ["no_match", "correct"], ["no_match"], ["counting", "no_match"], ["index_error", "no_match"],
  ["correct"], ["counting"], ["no_match"], ["index_error"], ["counting", "counting"],
  ["no_match", "no_match", "correct"], ["timeout"], ["no_match"], ["counting"], ["index_error", "index_error"],
  ["correct"], ["syntax", "no_match"], ["timeout", "counting"], ["syntax"], ["correct"],
  ["index_error"], ["syntax"],
];

function ts(minutesAgo: number): string {
  return new Date(Date.now() - minutesAgo * 60_000).toISOString().slice(0, 19).replace("T", " ");
}

// ended: the timer already ran out, to preview the "task ended" state.
export function buildMock(ended = false) {
  const subs: SubmissionRow[] = [];
  let id = 1000;
  PLAN.forEach((attempts, i) => {
    attempts.forEach((kind, n) => {
      const k = KIND[kind];
      const results = [
        { stdin: "([)]", expected_stdout: "False", passed: k.passed > 0 && kind !== "no_match", stdout: k.stdout, stderr: k.stderr ?? "" },
      ];
      subs.push({
        id: id++,
        created_at: ts(5 - n - i * 0.1),
        student_name: NAMES[i],
        question_id: "mock",
        language: "python",
        source_code: k.code,
        attempt_number: n + 1,
        tests_passed: k.passed,
        tests_total: 5,
        verdict: k.verdict,
        error_type: k.error_type,
        exec_verdict: k.exec,
        rejection_reason: null,
        feedback: null,
        discussion_point: null,
        raw_test_results: JSON.stringify(results),
      });
    });
  });

  // Latest attempt per student decides which cluster they're in.
  const latest = new Map<string, SubmissionRow>();
  for (const s of subs) latest.set(s.student_name, s);
  const idsFor = (code: string) => [...latest.values()].filter((s) => s.source_code === code).map((s) => s.id);

  const cluster = (code: string, exec: string, error_type: string | null, rest: Partial<ClusterRow>): ClusterRow => {
    const ids = idsFor(code);
    return {
      exec_verdict: exec,
      error_type,
      count: ids.length,
      example_submission_id: ids[0],
      submission_ids: ids,
      discussion_point: null,
      title: null,
      action: null,
      raised: false,
      ...rest,
    };
  };

  const clusters: ClusterRow[] = [
    cluster(NO_MATCH, "wrong_answer", null, {
      discussion_point:
        "The snippets pop from the stack on a closing bracket without comparing the popped value to the matching opening bracket, unlike the reference's stack.pop() != pairs[ch] check.",
      title: "Popping without checking the bracket type",
      action: "Trace \"([)]\" on the board and ask which line should notice the mismatch.",
      raised: true,
    }),
    cluster(COUNTING, "wrong_answer", null, {
      discussion_point:
        "The snippets compare the total count of opening brackets with the total count of closing brackets instead of tracking their order with a stack.",
      title: "Counting brackets instead of matching them",
      action: "Show \")(\" as a counterexample, then sketch the stack approach.",
    }),
    cluster(INDEX_ERROR, "runtime_error", "IndexError", {
      discussion_point: "IndexError: check the index against the sequence's actual valid range.",
      title: "Reading the top of an empty stack",
      action: "Run the code on \")\" together and read the traceback's last line.",
    }),
    cluster(SYNTAX, "syntax_error", null, {
      discussion_point: "Syntax error. Worth comparing the flagged line against the exact pattern of a def statement.",
      title: "Missing colon after the def line",
      action: "Put the flagged line next to a correct def header and ask what's different.",
    }),
    cluster(TIMEOUT, "timeout", null, {
      discussion_point: "Didn't finish. Worth checking what should update the loop's stopping condition.",
      title: "Loop never changes the string",
      action: "Point out that str.replace() returns a new string and ask where it goes.",
    }),
    cluster(REFERENCE, "pass", null, {}),
  ].filter((c) => c.count > 0);

  const question: QuestionRow = {
    id: "mock",
    created_at: ts(30),
    title: "Bracket Checker",
    prompt:
      "Read one line of input containing only the characters ()[]{}.\nPrint True if every bracket is closed by the matching bracket in the right order, otherwise False.",
    language: "python",
    test_cases: [{ stdin: "([)]", expected_stdout: "False" }],
    reference_solution: REFERENCE,
    cpu_time_limit_s: 2,
    memory_limit_kb: 128000,
    extra_packages: [],
    line_limit: 200,
    status: "live",
    validated: true,
    expected_students: 26,
    duration_seconds: 600,
    idle_nudge_seconds: 180,
    started_at: ts(ended ? 11 : 4),
    lecture_id: 1,
    output_file: null,
    starter_code: null,
    hint_ladder: null,
    hint_policy: DEFAULT_HINT_POLICY,
    grading_mode: "stdout",
    task_files: null,
    task_meta: {},
  };

  const progress: ProgressResponse = {
    submitted: latest.size,
    expected: 26,
    not_submitted: 26 - latest.size,
  };

  const activity: StudentActivity[] = NAMES.map((name, i) => ({
    student_name: name,
    status: i % 7 === 3 ? "idle" : i >= 24 ? "away" : "active",
    idle_seconds: i % 7 === 3 ? 240 : i >= 24 ? null : 10,
    nudged: i === 3,
  }));

  return {
    subs,
    clusters,
    question,
    progress,
    activity,
    joinCode: "482913",
    lectureLabel: "Introduction to Programming",
    taskNumber: 3,
    taskCount: 4,
  };
}
