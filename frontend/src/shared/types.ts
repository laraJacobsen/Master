// Mirrors the JSON shapes returned by backend/main.py, backend/store.py, and
// backend/aggregation.py. Kept as one shared file since all three pages talk
// to the same API.

export interface TestCase {
  stdin: string;
  expected_stdout: string;
}

// GET /api/questions -- student-facing, live questions only.
export interface PublicQuestion {
  id: string;
  title: string;
  prompt: string;
  language: string;
  example: TestCase | null;
}

// GET /api/lecture/status's `question` -- same shape as PublicQuestion plus
// the timer fields the student page needs to run its countdown.
export interface LiveQuestion extends PublicQuestion {
  duration_seconds: number;
  started_at: string | null;
  seconds_remaining: number;
}

// GET /api/lecture/status -- polled by the student page so it can
// auto-switch tasks and show the waiting/finished screens (see
// src/student/App.tsx).
export interface LectureStatus {
  finished: boolean;
  // The lecture this status describes (active, or the one that just ended).
  lecture_id: number | null;
  question: LiveQuestion | null;
  // Examples the lecturer is showing the class -- only sent once the task's
  // time is up. See aggregation.raise_issue() / shown_examples().
  shown_examples: SharedExample[];
}

// One anonymized submission the lecturer put on every student's screen:
// code (comments stripped) and the first test it failed, no name.
export interface SharedExample {
  source_code: string;
  failing_test: {
    stdin: string;
    expected_stdout: string;
    stdout: string;
    stderr: string;
  } | null;
}

// POST /api/lecture/join -- the Kahoot-style entry gate on the student page.
export interface LectureJoinResponse {
  lecture_id: number;
  label: string;
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
    example: { stdin: string; expected_stdout: string; stdout: string; students: number } | null;
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
  stdout?: string;
  stderr?: string;
  // C/Java only: what the compiler printed (a compile error has no stderr).
  compile_output?: string | null;
}

export interface ValidationResponse {
  validated: boolean;
  results: ValidationTestResult[];
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
}

// GET /api/lecturer/clusters
export interface ClusterRow {
  exec_verdict: string;
  error_type: string | null;
  count: number;
  example_submission_id: number;
  submission_ids: number[];
  discussion_point: string | null;
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
