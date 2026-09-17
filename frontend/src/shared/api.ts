import type {
  ApiErrorBody,
  ClusterRow,
  LectureFinishResponse,
  LectureNextResponse,
  LectureStatus,
  ProgressResponse,
  PublicQuestion,
  QuestionPayload,
  QuestionRow,
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
