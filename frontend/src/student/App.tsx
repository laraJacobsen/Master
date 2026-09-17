import { useEffect, useRef, useState } from "react";
import type { PublicQuestion, SubmissionRow, SubmitResponse, Verdict } from "../shared/types";
import { fetchPublicQuestions, fetchSubmissions, submitCode as submitCodeApi } from "../shared/api";

const VERDICT_LABELS: Record<string, string> = {
  correct: "Correct",
  partially_correct: "Partially Correct",
  incorrect: "Incorrect",
  error: "Error",
};

function initialQuestionId(): string | null {
  return new URLSearchParams(window.location.search).get("question_id");
}

export default function App() {
  // Mutable like the original `let QUESTION_ID` -- starts from ?question_id=,
  // then gets resolved to whichever live question the backend actually
  // returns (falls back to the first live one) once loadQuestion() runs.
  const [questionId, setQuestionId] = useState<string | null>(initialQuestionId);
  const [promptText, setPromptText] = useState("Loading question...");
  const [example, setExample] = useState<PublicQuestion["example"]>(null);

  const [name, setName] = useState("");
  const [code, setCode] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [statusText, setStatusText] = useState("");
  const slowNoticeRef = useRef<number | undefined>(undefined);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitResponse | null>(null);

  const [history, setHistory] = useState<SubmissionRow[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPublicQuestions()
      .then((questions) => {
        if (cancelled) return;
        const q = questions.find((item) => item.id === questionId) || questions[0];
        setQuestionId(q ? q.id : questionId);
        setPromptText(q ? q.prompt : "No question is live yet.");
        setExample(q && q.example ? q.example : null);
      })
      .catch(() => {
        if (cancelled) return;
        setPromptText("Could not load question (is the backend running?).");
        setExample(null);
      });
    return () => {
      cancelled = true;
    };
    // Intentionally runs once on mount, same as the original's single
    // loadQuestion() call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadHistory(studentName: string) {
    if (!studentName) {
      setHistory(null);
      return;
    }
    try {
      const rows = await fetchSubmissions(questionId);
      const mine = rows
        .filter((r) => r.student_name === studentName)
        .sort((a, b) => a.attempt_number - b.attempt_number);
      setHistory(mine.length === 0 ? null : mine);
    } catch {
      setHistory(null);
    }
  }

  async function handleSubmit() {
    const trimmedName = name.trim();
    const trimmedCode = code.trim();

    setErrorMessage(null);
    setResult(null);

    if (!trimmedName) {
      setErrorMessage("Enter your name first.");
      return;
    }
    if (!trimmedCode) {
      setErrorMessage("Write some code first.");
      return;
    }

    setSubmitting(true);
    setStatusText("Running your code on Judge0...");
    slowNoticeRef.current = window.setTimeout(() => {
      setStatusText(
        "Still working -- AI grading can take up to a minute, especially on the first submission of a session."
      );
    }, 4000);

    try {
      const data = await submitCodeApi({
        student_name: trimmedName,
        question_id: questionId ?? "",
        source_code: code,
      });
      setResult(data);
      loadHistory(trimmedName);
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : "Submission failed.");
    } finally {
      window.clearTimeout(slowNoticeRef.current);
      setSubmitting(false);
      setStatusText("");
    }
  }

  const verdictClass = (v: Verdict) => "verdict-badge verdict-" + v;
  const verdictLabel = (v: Verdict) => VERDICT_LABELS[v] || v;

  return (
    <>
      <header>
        <h1>Interactive Lecture -- Student</h1>
        <p>Practice problems with instant feedback that gets more specific the more you try.</p>
      </header>
      <main>
        <div className="col-left">
          <div className="card accent-navy">
            <label htmlFor="name">Your name</label>
            <input
              type="text"
              id="name"
              placeholder="e.g. Lara Pinheiro"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={(e) => loadHistory(e.target.value.trim())}
            />

            <label>Question</label>
            <div id="prompt-text">{promptText}</div>
            <div id="example-box" style={{ display: example ? "block" : "none" }}>
              {example && (
                <>
                  <div style={{ fontWeight: "bold", marginBottom: "0.3rem" }}>Example</div>
                  <code>{`Input:  ${example.stdin.trimEnd()}\nOutput: ${example.expected_stdout}`}</code>
                </>
              )}
            </div>
          </div>

          <div className="card" id="history-card" style={{ display: history ? "block" : "none" }}>
            <h2>Your attempts on this question</h2>
            <div id="history-trail">
              {(history ?? []).map((row) => (
                <div
                  key={row.id}
                  className={"history-dot " + (row.verdict || "incorrect")}
                  title={`Attempt ${row.attempt_number}: ${row.verdict || "unknown"}`}
                >
                  {row.attempt_number}
                </div>
              ))}
            </div>
            <div id="history-summary">
              {history &&
                (() => {
                  const passed = history.filter((r) => r.verdict === "correct").length;
                  return (
                    `${history.length} attempt${history.length === 1 ? "" : "s"} so far` +
                    (passed ? `, ${passed} correct` : "")
                  );
                })()}
            </div>
          </div>
        </div>

        <div className="col-right">
          <div className="card">
            <label htmlFor="code">Your code (Python)</label>
            <textarea
              id="code"
              spellCheck={false}
              placeholder="# Your code here."
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <button id="submit-btn" disabled={submitting} onClick={handleSubmit}>
              <span
                id="submit-spinner"
                className="spinner"
                style={{ display: submitting ? "inline-block" : "none" }}
              />
              <span id="submit-btn-text">{submitting ? "Running..." : "Submit"}</span>
            </button>
            <div id="submit-status" style={{ display: submitting ? "block" : "none" }}>
              {statusText}
            </div>
            <div id="error-box" style={{ display: errorMessage ? "block" : "none" }}>
              {errorMessage}
            </div>
          </div>

          <div className="card" id="result" style={{ display: result ? "block" : "none" }}>
            {result && (
              <>
                <span id="verdict-badge" className={verdictClass(result.verdict)}>
                  {verdictLabel(result.verdict)}
                </span>
                <span id="score-text" style={{ marginLeft: "0.6rem", color: "var(--muted)" }}>
                  {result.tests_passed}/{result.tests_total} tests passed
                </span>
                <div id="tier-note" style={{ display: result.hint_tier ? "block" : "none" }}>
                  {result.hint_tier ? (
                    <>
                      <div className="tier-label" id="tier-label">
                        {`Hint ${result.hint_tier} of ${result.hint_ceiling}`}
                      </div>
                      <div id="tier-bar">
                        {Array.from({ length: result.hint_ceiling ?? 0 }, (_, i) => i + 1).map(
                          (i) => (
                            <div
                              key={i}
                              className={"tier-seg" + (i <= (result.hint_tier ?? 0) ? " filled" : "")}
                            />
                          )
                        )}
                      </div>
                    </>
                  ) : null}
                </div>
                <div id="feedback-text">{result.feedback}</div>
                <details id="traceback-box" style={{ display: result.traceback ? "block" : "none" }}>
                  <summary>Your program's error output</summary>
                  <pre id="traceback-text">{result.traceback}</pre>
                </details>
              </>
            )}
          </div>
        </div>
      </main>
    </>
  );
}
