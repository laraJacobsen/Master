// Mirrors the JSON shapes returned by backend/main.py, backend/store.py, and
// backend/aggregation.py. Kept as one shared file since all three pages talk
// to the same API.

// A data file a test case attaches for the student's program to open by name
// (backend/test_files.py). `content` comes back only from the setup page's
// endpoints; polled endpoints send name and size instead.
export interface TestFile {
  name: string;
  content?: string;
  size?: number;
}

export interface TestCase {
  stdin: string;
  expected_stdout: string;
  files?: TestFile[];
}

// A test file a student may open: the example's while the task runs, every
// test's once time is up (GET /api/lecture/status's question.files).
export interface VisibleTestFile {
  test: number; // 0 = the example
  name: string;
  size: number;
}

// GET /api/lecture/attempts -- one student's own attempts, nothing else.
export interface StudentAttempt {
  id: number;
  attempt_number: number;
  verdict: Verdict | null;
  tests_passed: number;
  tests_total: number;
  created_at: string;
  feedback: string | null;
  // Test-graded tasks: the visible tests' results and the hidden count.
  test_results?: TestRunResult[];
  hidden_tests?: HiddenTestsSummary;
}

// GET /api/questions -- student-facing, live questions only.
export interface PublicQuestion {
  id: string;
  title: string;
  prompt: string;
  language: string;
  example: TestCase | null;
  // Graded on what the program writes to this file (e.g. "result.txt") instead
  // of what it prints; null = printed output.
  output_file?: string | null;
  grading_mode?: GradingMode;
}

// GET /api/lecture/status's `question` -- same shape as PublicQuestion plus
// the timer fields the student page needs to run its countdown.
export interface LiveQuestion extends PublicQuestion {
  // The lecturer's own starter code; null = the built-in default
  // (shared/starterCode.ts). "" is a deliberate empty start.
  starter_code: string | null;
  // Its place in the lecture ("Task 2"); null when not tied to a lecture.
  number: number | null;
  files: VisibleTestFile[];
  duration_seconds: number;
  started_at: string | null;
  seconds_remaining: number;
  // Test-graded tasks: the editor's files, name and size only (contents come from
  // GET /api/lecture/questions/{id}/workspace); null for stdout tasks.
  workspace?: WorkspaceEntry[] | null;
}

// One file of a test-graded task's student workspace (backend/main._workspace).
export interface WorkspaceEntry {
  path: string;
  kind: "code" | "test" | "data";
  editable: boolean;
  size: number;
  // Code and visible tests from the workspace endpoint; data files load on demand.
  content?: string;
}

export interface WorkspaceResponse {
  files: WorkspaceEntry[];
  markers: { begin: string; end: string } | null;
}

// GET /api/lecture/status -- polled by the student page so it can
// auto-switch tasks and show the waiting/finished screens (see
// src/student/App.tsx).
export interface LectureStatus {
  finished: boolean;
  // The lecture this status describes (active, or the one that just ended).
  lecture_id: number | null;
  question: LiveQuestion | null;
  // What the lecturer is showing the class: the screen queue's current entry
  // (zero or one) -- only sent once the task's time is up. See
  // aggregation.shown_examples().
  shown_examples: SharedExample[];
  // Where that entry sits in the screen queue (0-based index), for the
  // projector's Previous/Next; null before time is up or with nothing queued.
  shown_position: { index: number; total: number } | null;
}

// One thing the lecturer queued to show the class -- a raised discussion
// point's example ("issue") or one student's attempt. Lecturer-only: it
// carries student names. See aggregation.screen_queue().
export interface ScreenQueueEntry {
  id: number;
  kind: "issue" | "attempt";
  exec_verdict: string;
  error_type: string | null;
  students: string[];
  submission_id: number;
  verdict: string | null;
  tests_passed: number | null;
  tests_total: number | null;
  // Length of the code shown, so the lecturer can tell a long one coming.
  lines: number;
  current: boolean;
}

export interface ScreenQueue {
  entries: ScreenQueueEntry[];
  // On screen once time is up (the first entry unless the lecturer moved on).
  current_entry_id: number | null;
}

// One anonymized submission the lecturer put on every student's screen:
// code (comments stripped) and the first test it failed, no name.
export interface SharedExample {
  source_code: string;
  // Passed every test -- the lecturer can show a correct solution too.
  correct?: boolean;
  failing_test: {
    stdin: string;
    expected_stdout: string;
    stdout: string;
    stderr: string;
    // Test-graded tasks: the first failing *visible* test.
    test_name?: string;
    message?: string;
  } | null;
  // Test-graded tasks: hidden tests as a count only.
  hidden_tests?: HiddenTestsSummary;
}

// POST /api/lecture/join -- the Kahoot-style entry gate on the student page.
export interface LectureJoinResponse {
  lecture_id: number;
  label: string;
  // The name as the lecture knows it (a rejoin keeps the original spelling).
  student_name: string;
  // Sent with every student call from now on -- see setStudentToken in api.ts.
  token: string;
}

// GET /api/lecturer/lectures/{id}/joined_count -- the lobby's live counter.
export interface JoinedCountResponse {
  joined: number;
}

export type QuestionStatus = "draft" | "live" | "closed" | "skipped";

// GET/POST/PUT /api/lecturer/questions* -- full question row (setup page +
// lecturer page title lookup).
export interface QuestionRow {
  id: string;
  created_at: string;
  title: string;
  prompt: string;
  language: string;
  test_cases: TestCase[];
  reference_solution: string | null;
  cpu_time_limit_s: number;
  memory_limit_kb: number;
  extra_packages: string[];
  line_limit: number;
  status: QuestionStatus;
  validated: boolean;
  expected_students: number | null;
  duration_seconds: number;
  // Seconds without typing before the student gets an automatic nudge; 0 = off.
  idle_nudge_seconds: number;
  started_at: string | null;
  // The lecture it ran in; null until it's started.
  lecture_id: number | null;
  output_file: string | null;
  // null = the built-in default starter (shared/starterCode.ts).
  starter_code: string | null;
  // The task's own wrong-answer hints, attempt 1 first; null = generic hints.
  hint_ladder: string[] | null;
  // "stdout": compare printed output per test case (the setup page's own tasks).
  // "tests": pytest files from an imported task folder (backend/task_format.py).
  grading_mode: GradingMode;
  // Test-graded tasks: the folder's files; null for stdout tasks.
  task_files: TaskFile[] | null;
  task_meta: TaskMeta;
}

export type GradingMode = "stdout" | "tests";

export type TaskFileRole = "starter" | "test" | "hidden_test" | "reference" | "data";

export interface TaskFile {
  path: string;
  role: TaskFileRole;
  content: string;
}

// task.yaml settings without a column of their own (backend/task_import.py).
export interface TaskMeta {
  id?: string;
  editable?: string[];
  markers?: { begin: string; end: string } | null;
  test_timeout_s?: number;
  requirements?: string[];
  // The tests the reference run found when the task was last checked.
  test_ids?: { id: string; visibility: TestVisibility }[] | null;
}

export type TestVisibility = "visible" | "hidden";

export type TestOutcome = "passed" | "failed" | "error" | "skipped";

// One test of a test-graded run as students see it (backend/main._student_test_view).
export interface TestRunResult {
  name: string;
  file: string;
  outcome: TestOutcome;
  passed: boolean;
  message: string;
  details: string;
}

// Hidden tests: only how many there are and how many failed.
export interface HiddenTestsSummary {
  total: number;
  failed: number;
}

export interface QuestionPayload {
  title: string;
  prompt: string;
  language: string;
  test_cases: TestCase[];
  reference_solution: string | null;
  cpu_time_limit_s: number;
  memory_limit_kb: number;
  extra_packages: string[];
  line_limit: number;
  expected_students: number | null;
  duration_seconds: number;
  idle_nudge_seconds: number;
  output_file?: string | null;
  // null = the built-in default starter (shared/starterCode.ts).
  starter_code?: string | null;
  hint_ladder?: string[] | null;
}

// POST /api/lecturer/hints/draft
export interface HintDraftRequest {
  prompt: string;
  language: string;
  reference_solution: string;
  starter_code: string | null;
}

export interface HintDraftResponse {
  hints: string[];
}

// POST /api/lecturer/lecture/next
export interface LectureNextResponse {
  started: QuestionRow | null;
}

// POST /api/lecturer/lecture/finish
export interface LectureFinishResponse {
  finished: boolean;
  lecture_id: number | null;
}

// GET/POST /api/lecturer/lectures* -- a single lecture row.
export interface LectureRow {
  id: number;
  started_at: string;
  ended_at: string | null;
  label: string | null;
  archived: boolean;
  display_label: string;
  // Kahoot-style PIN students type into the student page to enter this
  // lecture -- a soft UX gate, not real access control (see README's "No
  // auth" known simplification). Null for lectures created before this
  // existed, or the synthetic historical rows the DB migration backfills.
  join_code: string | null;
  // Set once the lecturer clicks "Open lobby" -- null means the lecture
  // exists (questions can be authored/edited/deleted against it) but
  // nothing is joinable and no question can be started yet. See the
  // lobby-scoping-decision: this is the gate between "prepping before
  // class" and "the lobby is up, students are joining."
  lobby_opened_at: string | null;
}

// GET /api/lecturer/lectures -- history list, one entry per lecture.
export interface LectureHistoryRow extends LectureRow {
  task_count: number;
  submitted_total: number;
  verdict_counts: Partial<Record<Verdict, number>>;
}

// GET /api/lecturer/lectures/review -- one finished lecture, for the history
// page's "Needs revisiting" ranking. See aggregation.lecture_review().
export interface LectureReviewTask {
  question_id: string;
  title: string;
  // Everyone who took part in the lecture (same for every task).
  students: number;
  submitted: number;
  solved: number;
  solve_rate: number | null;
  // Most common way the unsolved students' latest submissions went wrong.
  top_issue: {
    exec_verdict: string | null;
    error_type: string | null;
    students: number;
    discussion_point: string | null;
    // Wrong answers only: the most common first failing test among them.
    example: {
      stdin: string;
      expected_stdout: string;
      stdout: string;
      students: number;
      // Test-graded tasks: the failing test and its message instead of input/output.
      test_name?: string;
      message?: string;
    } | null;
  } | null;
}

export interface LectureReview {
  lecture_id: number;
  display_label: string;
  started_at: string;
  archived: boolean;
  students: number;
  solve_rate: number | null;
  // False below MIN_STUDENTS_FOR_REVIEW students -- listed, but not ranked.
  enough_data: boolean;
  tasks: LectureReviewTask[]; // weakest first
}

// GET /api/lecturer/lectures/active
export interface ActiveLectureResponse {
  lecture: LectureRow | null;
  live_question_id: string | null;
  // Whether "Next task" would start anything -- only sent while a lecture is active.
  has_next_task?: boolean;
  // The live task's position: "Task 3 of 4" (null when nothing is live).
  task_number?: number | null;
  task_count?: number;
}

// GET /api/lecturer/stats/totals
export interface LectureTotals {
  lectures_run: number;
  total_submissions: number;
}

export interface ValidationTestResult {
  stdin: string;
  expected_stdout: string;
  passed: boolean;
  // Test-graded tasks (backend/task_runner.TestResult.to_result_dict).
  test_name?: string;
  test_file?: string;
  visibility?: TestVisibility;
  outcome?: TestOutcome;
  message?: string;
  details?: string;
  stdout?: string;
  stderr?: string;
  // C/Java only: what the compiler printed (a compile error has no stderr).
  compile_output?: string | null;
}

export interface ValidationResponse {
  validated: boolean;
  results: ValidationTestResult[];
  // Something about the lecturer's starter code: blocking (every submission
  // that keeps it would be rejected) or a heads-up (it doesn't run as it is).
  starter_problem?: StarterProblem | null;
}

export interface StarterProblem {
  blocking: boolean;
  message: string;
}

export type Verdict = "correct" | "partially_correct" | "incorrect" | "error";

// GET /api/lecturer/submissions, /api/lecturer/submissions/{id}
export interface SubmissionRow {
  id: number;
  created_at: string;
  student_name: string;
  question_id: string;
  language: string;
  source_code: string;
  attempt_number: number;
  tests_passed: number;
  tests_total: number;
  verdict: Verdict | null;
  error_type: string | null;
  exec_verdict: string | null;
  rejection_reason: string | null;
  feedback: string | null;
  discussion_point: string | null;
  raw_test_results: string; // JSON-encoded ValidationTestResult[]
  // "Same code, different names" grouping (backend/code_shape.py) -- null key
  // for non-Python or code that doesn't parse. shape_names[i] is what this
  // submission called its i-th own name; spans are [slot, start, end] offsets
  // into source_code.
  shape_key?: string | null;
  shape_names?: string[];
  shape_spans?: [number, number, number][];
}

// GET /api/lecturer/clusters
export interface ClusterRow {
  exec_verdict: string;
  error_type: string | null;
  count: number;
  example_submission_id: number;
  submission_ids: number[];
  discussion_point: string | null;
  // AI rewrite of discussion_point for the dashboard: a short headline and one
  // thing for the lecturer to do. Null when there's no point or the call failed.
  title: string | null;
  action: string | null;
  // Shown to the students by the lecturer -- sorted first, gets a discussion
  // point even with a single student, and its example is on the students'
  // waiting screen. See aggregation.raise_issue().
  raised: boolean;
}

// POST /api/lecture/activity -- the student editor's heartbeat reply.
export interface ActivityResponse {
  nudge: string | null;
}

// GET /api/lecturer/questions/{id}/activity -- one row per student who
// joined the lecture or opened this task's editor.
export type ActivityStatus = "active" | "idle" | "away";
export interface StudentActivity {
  student_name: string;
  status: ActivityStatus;
  // Seconds since they last typed (or opened the task, if they never have).
  idle_seconds: number | null;
  nudged: boolean;
}

// GET /api/lecturer/questions/{id}/progress
export interface ProgressResponse {
  submitted: number;
  expected: number | null;
  not_submitted: number | null;
}

// POST /api/submit
export interface SubmitResponse {
  submission_id: number;
  tests_passed: number;
  tests_total: number;
  verdict: Verdict;
  feedback: string;
  attempt_number?: number;
  hint_tier?: number | null;
  hint_ceiling?: number | null;
  traceback?: string | null;
  // Only a hidden test crashed: no traceback (it could carry that test's data),
  // just the error type when known, e.g. "ValueError" -- see
  // main._student_error_output.
  hidden_crash?: boolean;
  hidden_error?: string | null;
  // Test-graded tasks: every visible test in full, the hidden ones as a count.
  test_results?: TestRunResult[];
  hidden_tests?: HiddenTestsSummary;
}

// POST /api/run -- one ungraded run on the student's own stdin (never stored).
// Test-graded tasks: the visible tests on the student's files (TestsRunResponse).
export type RunResponse =
  | { rejected: string }
  | TestsRunResponse
  | {
      rejected: null;
      status: string;
      accepted: boolean;
      stdout: string;
      stderr: string;
      compile_output: string;
      message: string;
      time_s: string | null;
      exit_code: number | null;
      // Tasks graded on a file: what the program wrote there (null = not created).
      output_file: string | null;
      output_file_content: string | null;
    };

export interface TestsRunResponse {
  rejected: null;
  grading_mode: "tests";
  test_results: TestRunResult[];
  hidden_tests: HiddenTestsSummary;
  // The lecturer's run only (projector).
  hidden_test_results?: TestRunResult[];
}

export function isTestsRun(res: RunResponse): res is TestsRunResponse {
  return res.rejected === null && "test_results" in res;
}

export interface ApiErrorBody {
  detail?: string;
}

// GET /api/lecturer/lecture/summary -- one entry per task in the lecture.
export interface SessionTaskSummary {
  question_id: string;
  title: string;
  submitted: number;
  expected: number | null;
  verdict_counts: Partial<Record<Verdict, number>>;
}

// GET /api/lecturer/lecture/summary -- an issue that recurred across 2+ tasks.
export interface CarryForwardPoint {
  exec_verdict: string;
  error_type: string | null;
  task_titles: string[];
  discussion_point: string;
}

// GET /api/lecturer/lecture/summary -- the STATE 2 lecturer post-lecture
// view, generalized to any lecture_id (not just the most recent one).
export interface LectureSummary {
  lecture_id: number;
  lecture_label: string;
  tasks: SessionTaskSummary[];
  carry_forward_discussion_points: CarryForwardPoint[];
}

// GET /api/lecture/recap's `results` -- this student's standing on one task.
export interface StudentRecapItem {
  question_id: string;
  title: string;
  attempted: boolean;
  verdict: Verdict | null;
}

// GET /api/lecture/recap -- the STATE 2 student personal recap (no
// class-wide comparison anywhere in this shape, by design).
export interface StudentRecap {
  attempted: number;
  total: number;
  results: StudentRecapItem[];
}
