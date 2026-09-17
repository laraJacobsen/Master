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
  question: LiveQuestion | null;
}

export type QuestionStatus = "draft" | "live" | "closed";

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
}

// POST /api/lecturer/lecture/next
export interface LectureNextResponse {
  started: QuestionRow | null;
}

// POST /api/lecturer/lecture/finish
export interface LectureFinishResponse {
  finished: boolean;
}

export interface ValidationTestResult {
  stdin: string;
  expected_stdout: string;
  passed: boolean;
  stdout?: string;
  stderr?: string;
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

// GET /api/lecturer/lecture/summary -- the STATE 2 lecturer post-lecture view.
export interface LectureSummary {
  lecture_seq: number;
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
