import type {
  ActiveLectureResponse,
  ApiErrorBody,
  ClusterRow,
  JoinedCountResponse,
  LectureFinishResponse,
  LectureHistoryRow,
  LectureJoinResponse,
  LectureNextResponse,
  LectureRow,
  LectureStatus,
  LectureSummary,
  LectureTotals,
  ProgressResponse,
  PublicQuestion,
  QuestionPayload,
  QuestionRow,
  StudentRecap,
  SubmissionRow,
  SubmitResponse,
  ValidationResponse,
} from "./types";

const API_BASE = ""; // same origin as the page when served by the FastAPI backend

async function asJson<T>(res: Response): Promise<T> {
  const data = await res.json();
  if (!res.ok) {
    const detail = (data as ApiErrorBody)?.detail;
    throw new Error(detail || "Request failed.");
  }
  return data as T;
}

export function fetchPublicQuestions(): Promise<PublicQuestion[]> {
  return fetch(`${API_BASE}/api/questions`).then((res) => asJson(res));
}

export function fetchQuestionList(): Promise<QuestionRow[]> {
  return fetch(`${API_BASE}/api/lecturer/questions`).then((res) => asJson(res));
}

export function fetchQuestionDetail(questionId: string): Promise<QuestionRow> {
  return fetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}`).then(
    (res) => asJson(res)
  );
}

export function createQuestion(payload: QuestionPayload): Promise<QuestionRow> {
  return fetch(`${API_BASE}/api/lecturer/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function updateQuestion(
  questionId: string,
  payload: QuestionPayload
): Promise<QuestionRow> {
  return fetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function validateQuestion(questionId: string): Promise<ValidationResponse> {
  return fetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/validate`, {
    method: "POST",
  }).then((res) => asJson(res));
}

export function startQuestion(questionId: string): Promise<QuestionRow> {
  return fetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/start`, {
    method: "POST",
  }).then((res) => asJson(res));
}

export function deleteQuestion(questionId: string): Promise<{ deleted: boolean }> {
  return fetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}`, {
    method: "DELETE",
  }).then((res) => asJson(res));
}

export function submitCode(payload: {
  student_name: string;
  question_id: string;
  source_code: string;
}): Promise<SubmitResponse> {
  return fetch(`${API_BASE}/api/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson(res));
}

export function fetchSubmissions(questionId?: string | null): Promise<SubmissionRow[]> {
  const qs = questionId ? `?question_id=${encodeURIComponent(questionId)}` : "";
  return fetch(`${API_BASE}/api/lecturer/submissions${qs}`).then((res) => asJson(res));
}

export function fetchSubmissionDetail(subId: number): Promise<SubmissionRow> {
  return fetch(`${API_BASE}/api/lecturer/submissions/${subId}`).then((res) => asJson(res));
}

export function fetchProgress(questionId: string): Promise<ProgressResponse> {
  return fetch(`${API_BASE}/api/lecturer/questions/${encodeURIComponent(questionId)}/progress`).then(
    (res) => asJson(res)
  );
}

export function fetchClusters(questionId?: string | null): Promise<ClusterRow[]> {
  const qs = questionId ? `?question_id=${encodeURIComponent(questionId)}` : "";
  return fetch(`${API_BASE}/api/lecturer/clusters${qs}`).then((res) => asJson(res));
}

export function fetchLectureStatus(): Promise<LectureStatus> {
  return fetch(`${API_BASE}/api/lecture/status`).then((res) => asJson(res));
}

export function joinLecture(code: string, studentName: string): Promise<LectureJoinResponse> {
  return fetch(`${API_BASE}/api/lecture/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, student_name: studentName }),
  }).then((res) => asJson(res));
}

export function nextTask(currentQuestionId: string | null): Promise<LectureNextResponse> {
  return fetch(`${API_BASE}/api/lecturer/lecture/next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_question_id: currentQuestionId }),
  }).then((res) => asJson(res));
}

export function finishLecture(currentQuestionId: string | null): Promise<LectureFinishResponse> {
  return fetch(`${API_BASE}/api/lecturer/lecture/finish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_question_id: currentQuestionId }),
  }).then((res) => asJson(res));
}

export function fetchLectureSummary(lectureId?: number | null): Promise<LectureSummary> {
  const qs = lectureId != null ? `?lecture_id=${lectureId}` : "";
  return fetch(`${API_BASE}/api/lecturer/lecture/summary${qs}`).then((res) => asJson(res));
}

export function fetchStudentRecap(studentName: string): Promise<StudentRecap> {
  return fetch(`${API_BASE}/api/lecture/recap?student_name=${encodeURIComponent(studentName)}`).then((res) =>
    asJson(res)
  );
}

export function createLecture(label: string | null): Promise<LectureRow> {
  return fetch(`${API_BASE}/api/lecturer/lectures`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  }).then((res) => asJson(res));
}

export function fetchActiveLecture(): Promise<ActiveLectureResponse> {
  return fetch(`${API_BASE}/api/lecturer/lectures/active`).then((res) => asJson(res));
}

export function fetchLectureDetail(lectureId: number): Promise<LectureRow> {
  return fetch(`${API_BASE}/api/lecturer/lectures/${lectureId}`).then((res) => asJson(res));
}

export function openLobby(lectureId: number): Promise<LectureRow> {
  return fetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/open_lobby`, { method: "POST" }).then((res) =>
    asJson(res)
  );
}

export function fetchJoinedCount(lectureId: number): Promise<JoinedCountResponse> {
  return fetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/joined_count`).then((res) => asJson(res));
}

export function fetchLectureHistory(includeArchived = false): Promise<LectureHistoryRow[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  return fetch(`${API_BASE}/api/lecturer/lectures${qs}`).then((res) => asJson(res));
}

export function archiveLecture(lectureId: number): Promise<LectureRow> {
  return fetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/archive`, { method: "POST" }).then((res) =>
    asJson(res)
  );
}

export function unarchiveLecture(lectureId: number): Promise<LectureRow> {
  return fetch(`${API_BASE}/api/lecturer/lectures/${lectureId}/unarchive`, { method: "POST" }).then((res) =>
    asJson(res)
  );
}

export function fetchLectureTotals(): Promise<LectureTotals> {
  return fetch(`${API_BASE}/api/lecturer/stats/totals`).then((res) => asJson(res));
}
