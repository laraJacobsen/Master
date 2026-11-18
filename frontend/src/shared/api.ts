import type {
  ActiveLectureResponse,
  ActivityResponse,
  ApiErrorBody,
  ClusterRow,
  HintDraftRequest,
  HintDraftResponse,
  JoinedCountResponse,
  LectureFinishResponse,
  LectureHistoryRow,
  LectureJoinResponse,
  LectureNextResponse,
  LectureReview,
  LectureRow,
  LectureStatus,
  LectureSummary,
  LectureTotals,
  ProgressResponse,
  PublicQuestion,
  QuestionPayload,
  QuestionRow,
  StudentActivity,
  StudentRecap,
  SubmissionRow,
  StudentAttempt,
  SubmitResponse,
  ValidationResponse,
  RunResponse,
  ScreenQueue,
} from "./types";

const API_BASE = ""; // same origin as the page when served by the FastAPI backend

// Fired when a lecturer call comes back 401 -- see LecturerGate.
export const LECTURER_AUTH_EXPIRED_EVENT = "lecturer-auth-expired";

// The student's join token (see POST /api/lecture/join): sent with every
// student call, and it's how the server knows who the student is -- the
// calls below never send a name. Set by the student page once joined.
let studentToken: string | null = null;

export function setStudentToken(token: string | null): void {
  studentToken = token;
}

export interface LecturerSession {
  auth_required: boolean;
  logged_in: boolean;
}

export function fetchLecturerSession(): Promise<LecturerSession> {
  return apiFetch(`${API_BASE}/api/lecturer/session`).then((res) => asJson(res));
}

export function lecturerLogin(password: string): Promise<{ logged_in: boolean }> {
  return apiFetch(`${API_BASE}/api/lecturer/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  }).then((res) => asJson(res));
}

export function lecturerLogout(): Promise<unknown> {
  return apiFetch(`${API_BASE}/api/lecturer/logout`, { method: "POST" }).then((res) => asJson(res));
}

// Fired when the server stops or starts answering again -- only on the change,
// not per call. ConnectionBanner shows "Reconnecting..." while it's down.
export const CONNECTION_EVENT = "api-connection";
export interface ConnectionDetail {
  ok: boolean;
}
let connectionOk = true;
function reportConnection(ok: boolean): void {
  if (ok === connectionOk) return;
  connectionOk = ok;
  window.dispatchEvent(new CustomEvent<ConnectionDetail>(CONNECTION_EVENT, { detail: { ok } }));
}

// fetch() only rejects when the server can't be reached at all (network down,
// server stopped), with browser jargon like "Failed to fetch" -- shown as-is in
// the pages' error lines, which is no use to a lecturer or student.
function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (studentToken && !input.includes("/api/lecturer/")) headers.set("X-Student-Token", studentToken);
  return fetch(input, { ...init, headers })
    .catch(() => {
      reportConnection(false);
      throw new Error("Couldn't reach the server. Check your connection and try again.");
    })
    .then((res) => {
      // A proxy in front of a stopped backend answers 502/503/504 instead.
      reportConnection(res.status < 502 || res.status > 504);
      // The lecturer's session ran out (or was never there): LecturerGate shows
      // the login dialog over the page, which stays as it was underneath.
      if (res.status === 401 && input.includes("/api/lecturer/") && !input.endsWith("/api/lecturer/login")) {
        window.dispatchEvent(new Event(LECTURER_AUTH_EXPIRED_EVENT));
      }
      return res;
    });
}

async function asJson<T>(res: Response): Promise<T> {
  const data = await res.json();
  if (!res.ok) {
    const detail = (data as ApiErrorBody)?.detail;
    throw new Error(detail || "Request failed.");
  }
  return data as T;
}

export function fetchPublicQuestions(): Promise<PublicQuestion[]> {
  return apiFetch(`${API_BASE}/api/questions`).then((res) => asJson(res));
}

export function fetchQuestionList(): Promise<QuestionRow[]> {
  return apiFetch(`${API_BASE}/api/lecturer/questions`).then((res) => asJson(res));
}

export function fetchQuestionDetail(questionId: string): Promise<QuestionRow> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}`).then(
    (res) => asJson(res)
  );
}

export function createQuestion(payload: QuestionPayload): Promise<QuestionRow> {
  return apiFetch(`${API_BASE}/api/lecturer/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function updateQuestion(
  questionId: string,
  payload: QuestionPayload
): Promise<QuestionRow> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function draftHints(payload: HintDraftRequest): Promise<HintDraftResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/hints/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function validateQuestion(questionId: string): Promise<ValidationResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/validate`, {
    method: "POST",
  }).then((res) => asJson(res));
}

export function startQuestion(questionId: string): Promise<QuestionRow> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/start`, {
    method: "POST",
  }).then((res) => asJson(res));
}

export function deleteQuestion(questionId: string): Promise<{ deleted: boolean }> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}`, {
    method: "DELETE",
  }).then((res) => asJson(res));
}

export function submitCode(payload: {
  question_id: string;
  source_code: string;
}): Promise<SubmitResponse> {
  return apiFetch(`${API_BASE}/api/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function runCode(payload: {
  question_id: string;
  source_code: string;
  stdin: string;
}): Promise<RunResponse> {
  return apiFetch(`${API_BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

// The projector's Run on a shown attempt -- same as runCode, as the lecturer.
export function lecturerRunCode(payload: { question_id: string; source_code: string; stdin: string }): Promise<RunResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function fetchSubmissions(questionId?: string | null): Promise<SubmissionRow[]> {
  const qs = questionId ? `?question_id=${encodeURIComponent(questionId)}` : "";
  return apiFetch(`${API_BASE}/api/lecturer/submissions${qs}`).then((res) => asJson(res));
}

// The student page's own attempts trail -- never the lecturer's submissions feed.
export function fetchMyAttempts(questionId: string): Promise<StudentAttempt[]> {
  const qs = `?question_id=${encodeURIComponent(questionId)}`;
  return apiFetch(`${API_BASE}/api/lecture/attempts${qs}`).then((res) => asJson(res));
}

// One test file's content for the student's file viewer (plain text).
export function fetchTestFile(questionId: string, test: number, name: string): Promise<string> {
  const path = name.split("/").map(encodeURIComponent).join("/");
  return apiFetch(`${API_BASE}/api/lecture/questions/${encodeURIComponent(questionId)}/tests/${test}/files/${path}`).then(
    async (res) => {
      if (!res.ok) throw new Error(res.status === 403 ? "This file is shown once the task is over." : "Couldn't load the file.");
      return res.text();
    },
  );
}

export function fetchSubmissionDetail(subId: number): Promise<SubmissionRow> {
  return apiFetch(`${API_BASE}/api/lecturer/submissions/${subId}`).then((res) => asJson(res));
}

export function fetchProgress(questionId: string): Promise<ProgressResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/progress`).then(
    (res) => asJson(res)
  );
}

export function fetchClusters(questionId?: string | null): Promise<ClusterRow[]> {
  const qs = questionId ? `?question_id=${encodeURIComponent(questionId)}` : "";
  return apiFetch(`${API_BASE}/api/lecturer/clusters${qs}`).then((res) => asJson(res));
}

// Returns the question's clusters re-ranked with the change applied.
// `exampleId` picks which of the issue's snippets goes on screen (default: its first).
export function raiseIssue(
  questionId: string,
  cluster: ClusterRow,
  raised: boolean,
  exampleId?: number,
): Promise<ClusterRow[]> {
  return apiFetch(`${API_BASE}/api/lecturer/clusters/raise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question_id: questionId,
      exec_verdict: cluster.exec_verdict,
      error_type: cluster.error_type,
      submission_ids: cluster.submission_ids,
      raised,
      example_submission_id: exampleId ?? null,
    }),
  }).then((res) => asJson(res));
}

export function fetchLectureStatus(): Promise<LectureStatus> {
  return apiFetch(`${API_BASE}/api/lecture/status`).then((res) => asJson(res));
}

// `token`: this browser's token from an earlier join of the same lecture, so
// rejoining keeps the student's name (anyone else gets "name taken").
export function joinLecture(code: string, studentName: string, token: string | null): Promise<LectureJoinResponse> {
  return apiFetch(`${API_BASE}/api/lecture/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, student_name: studentName, token }),
  }).then((res) => asJson(res));
}

// Heartbeat from the student editor -- `edited` says whether they typed since
// the previous one; the code itself is never sent here.
export function sendActivity(questionId: string, edited: boolean): Promise<ActivityResponse> {
  return apiFetch(`${API_BASE}/api/lecture/activity`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, edited }),
  }).then((res) => asJson(res));
}

export function fetchActivity(questionId: string): Promise<StudentActivity[]> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/activity`).then((res) =>
    asJson(res)
  );
}

export function nextTask(currentQuestionId: string | null): Promise<LectureNextResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/lecture/next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_question_id: currentQuestionId }),
  }).then((res) => asJson(res));
}

export function endQuestionNow(questionId: string): Promise<QuestionRow> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/end_now`, {
    method: "POST",
  }).then((res) => asJson(res));
}

// Ids of the single submissions the lecturer is showing the class.
export function fetchShownSubmissions(questionId: string): Promise<number[]> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/shown_submissions`).then((res) =>
    asJson(res),
  );
}

// "Show on screen" in a student's code drawer: any attempt, correct ones
// included. Returns the question's shown single-submission ids.
export function showSubmission(submissionId: number, shown: boolean): Promise<number[]> {
  return apiFetch(`${API_BASE}/api/lecturer/submissions/${submissionId}/show`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ shown }),
  }).then((res) => asJson(res));
}

// The screen queue -- see backend/main.py's api_lecturer_screen_queue. Every
// change returns the whole queue as it now stands.
export function fetchScreenQueue(questionId: string): Promise<ScreenQueue> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/screen_queue`).then((res) =>
    asJson(res),
  );
}

export function moveQueueEntry(entryId: number, index: number): Promise<ScreenQueue> {
  return apiFetch(`${API_BASE}/api/lecturer/screen_queue/${entryId}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  }).then((res) => asJson(res));
}

export function removeQueueEntry(entryId: number): Promise<ScreenQueue> {
  return apiFetch(`${API_BASE}/api/lecturer/screen_queue/${entryId}`, { method: "DELETE" }).then((res) => asJson(res));
}

// Put one entry on screen, or move `step` places along the queue.
export function setScreenQueueCurrent(
  questionId: string,
  target: { entry_id: number } | { step: number },
): Promise<ScreenQueue> {
  return apiFetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/screen_queue/current`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(target),
  }).then((res) => asJson(res));
}

export function finishLecture(currentQuestionId: string | null): Promise<LectureFinishResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/lecture/finish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_question_id: currentQuestionId }),
  }).then((res) => asJson(res));
}

export function fetchLectureSummary(lectureId?: number | null): Promise<LectureSummary> {
  const qs = lectureId != null ? `?lecture_id=${lectureId}` : "";
  return apiFetch(`${API_BASE}/api/lecturer/lecture/summary${qs}`).then((res) => asJson(res));
}

export function fetchStudentRecap(): Promise<StudentRecap> {
  return apiFetch(`${API_BASE}/api/lecture/recap`).then((res) =>
    asJson(res)
  );
}

export function createLecture(label: string | null): Promise<LectureRow> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  }).then((res) => asJson(res));
}

export function fetchActiveLecture(): Promise<ActiveLectureResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/active`).then((res) => asJson(res));
}

export function fetchLectureDetail(lectureId: number): Promise<LectureRow> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/${lectureId}`).then((res) => asJson(res));
}

export function openLobby(lectureId: number): Promise<LectureRow> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/open_lobby`, { method: "POST" }).then((res) =>
    asJson(res)
  );
}

export function fetchJoinedCount(lectureId: number): Promise<JoinedCountResponse> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/joined_count`).then((res) => asJson(res));
}

export function fetchLectureReview(): Promise<LectureReview[]> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/review`).then((res) => asJson(res));
}

export function fetchLectureHistory(includeArchived = false): Promise<LectureHistoryRow[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  return apiFetch(`${API_BASE}/api/lecturer/lectures${qs}`).then((res) => asJson(res));
}

export function archiveLecture(lectureId: number): Promise<LectureRow> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/archive`, { method: "POST" }).then((res) =>
    asJson(res)
  );
}

export function unarchiveLecture(lectureId: number): Promise<LectureRow> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/unarchive`, { method: "POST" }).then((res) =>
    asJson(res)
  );
}

export function deleteLecture(lectureId: number): Promise<{ deleted: boolean }> {
  return apiFetch(`${API_BASE}/api/lecturer/lectures/${lectureId}`, { method: "DELETE" }).then((res) =>
    asJson(res)
  );
}

export function fetchLectureTotals(): Promise<LectureTotals> {
  return apiFetch(`${API_BASE}/api/lecturer/stats/totals`).then((res) => asJson(res));
}
