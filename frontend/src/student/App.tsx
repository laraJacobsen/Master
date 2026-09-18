import { useEffect, useRef, useState } from "react";
import type { LectureStatus, StudentRecap, SubmissionRow, SubmitResponse, TestCase, Verdict } from "../shared/types";
import {
  fetchLectureStatus,
  fetchStudentRecap,
  fetchSubmissions,
  joinLecture as joinLectureApi,
  submitCode as submitCodeApi,
} from "../shared/api";

const VERDICT_LABELS: Record<string, string> = {
  correct: "Correct",
  partially_correct: "Partially Correct",
  incorrect: "Incorrect",
  error: "Error",
};

// How often the student page checks in with the backend for the live
// question/timer/finished state -- see /api/lecture/status in backend/
// main.py. Faster than the lecturer dashboard's 3s poll since the countdown
// (and the auto-submit-on-timeout it drives) benefits more from staying
// in sync.
const POLL_MS = 2000;

// Kahoot-style entry gate (POST /api/lecture/join) -- a soft UX gate, not
// real access control (/api/submit itself stays open either way, see the
// "No auth" known simplification in README.md). Once entered, remembered
// for the rest of this browser tab so a page refresh mid-lecture doesn't
// force retyping it; a new tab (new lecture, most likely) asks again.
const JOIN_SESSION_KEY = "lecture_joined";
// The name typed on the join screen -- carried forward so the later
// answering screen's own name field is pre-filled instead of asking twice
// (same self-chosen display name either way, see submission-format-and-
// error-taxonomy.md's no-real-identity stance -- this doesn't collect
// anything new, just moves the existing collection point earlier).
const JOIN_NAME_KEY = "lecture_joined_name";

function hasJoinedThisSession(): boolean {
  try {
    return sessionStorage.getItem(JOIN_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function getJoinedName(): string {
  try {
    return sessionStorage.getItem(JOIN_NAME_KEY) || "";
  } catch {
    return "";
  }
}

function markJoinedThisSession(studentName: string): void {
  try {
    sessionStorage.setItem(JOIN_SESSION_KEY, "1");
    sessionStorage.setItem(JOIN_NAME_KEY, studentName);
  } catch {
    // Best effort -- worst case the student re-enters the code after a refresh.
  }
}

type Phase = "join" | "loading" | "answering" | "waiting" | "finished";

function formatMMSS(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

export default function App() {
  const [joined, setJoined] = useState(hasJoinedThisSession);
  const [phase, setPhase] = useState<Phase>(() => (hasJoinedThisSession() ? "loading" : "join"));
  const [joinNameInput, setJoinNameInput] = useState("");
  const [joinCodeInput, setJoinCodeInput] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [questionId, setQuestionId] = useState<string | null>(null);
  const [promptText, setPromptText] = useState("");
  const [example, setExample] = useState<TestCase | null>(null);
  const [durationSeconds, setDurationSeconds] = useState<number | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);

  // Pre-filled from the join screen's name (see JOIN_NAME_KEY) if this tab
  // already joined -- still editable here in case of a typo.
  const [name, setName] = useState(getJoinedName);
  const [code, setCode] = useState("");
  // Mirrors of `name`/`code` for the auto-submit-on-timeout path, which can
  // fire from inside a setInterval/poll callback where the `name`/`code`
  // state captured at effect-setup time would otherwise be stale.
  const nameRef = useRef(getJoinedName());
  const codeRef = useRef("");

  const [submitting, setSubmitting] = useState(false);
  const [statusText, setStatusText] = useState("");
  const slowNoticeRef = useRef<number | undefined>(undefined);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitResponse | null>(null);
  // Whether the *current* result (or grading-in-flight submit) was fired by
  // the timeout handler rather than a manual Submit click -- only affects
  // which line shows while grading ("submitted automatically" vs nothing);
  // once a result comes back, both cases render the same verdict badge.
  const [wasAutoSubmitted, setWasAutoSubmitted] = useState(false);

  const [history, setHistory] = useState<SubmissionRow[] | null>(null);

  const questionIdRef = useRef<string | null>(null);
  const phaseRef = useRef<Phase>("loading");
  const autoSubmittedRef = useRef(false);
  // Mirrors of `submitting`/`result`, read from the timeout handler (see
  // handleTimeUp) so it can tell "a manual submit is already in flight" and
  // "already has a result" apart from "nothing was ever submitted" without
  // depending on stale state from when the poll/interval closure was set up.
  const submittingRef = useRef(false);
  const resultRef = useRef<SubmitResponse | null>(null);

  // STATE 2: this student's personal recap, fetched once when the lecture
  // ends (see applyStatus below) -- not polled, since a finished lecture's
  // recap doesn't change. Guarded by recapFetchedRef so repeated poll ticks
  // while phase stays "finished" don't keep re-fetching it.
  const [recap, setRecap] = useState<StudentRecap | null>(null);
  const recapFetchedRef = useRef(false);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  function updateName(v: string) {
    setName(v);
    nameRef.current = v;
  }
  function updateCode(v: string) {
    setCode(v);
    codeRef.current = v;
  }

  async function loadHistory(studentName: string, qId: string | null) {
    if (!studentName || !qId) {
      setHistory(null);
      return;
    }
    try {
      const rows = await fetchSubmissions(qId);
      const mine = rows
        .filter((r) => r.student_name === studentName)
        .sort((a, b) => a.attempt_number - b.attempt_number);
      setHistory(mine.length === 0 ? null : mine);
    } catch {
      setHistory(null);
    }
  }

  // Shared by the manual Submit button and the timeout auto-submit path --
  // both need the same Judge0-timing status text, spinner, and result/error
  // handling, just triggered differently and with different validation
  // upstream of this call.
  async function performSubmit(qId: string, trimmedName: string, trimmedCode: string) {
    setSubmitting(true);
    submittingRef.current = true;
    setStatusText("Running your code on Judge0...");
    slowNoticeRef.current = window.setTimeout(() => {
      setStatusText(
        "Still working. AI grading can take up to a minute, especially on the first submission of a session."
      );
    }, 4000);

    try {
      const data = await submitCodeApi({
        student_name: trimmedName,
        question_id: qId,
        source_code: trimmedCode,
      });
      setResult(data);
      resultRef.current = data;
      loadHistory(trimmedName, qId);
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : "Submission failed.");
    } finally {
      window.clearTimeout(slowNoticeRef.current);
      setSubmitting(false);
      submittingRef.current = false;
      setStatusText("");
    }
  }

  // Fires once per question, the moment its timer hits zero -- moves the
  // student to the waiting screen and, depending on where they were at that
  // instant, either leaves things alone, auto-submits, or shows the neutral
  // "nothing to submit" note (the render below derives which one from
  // submitting/result/code, this just decides whether to *start* a submit).
  // Guarded by autoSubmittedRef so the 1s local countdown and the next
  // server poll can't both trigger it.
  function handleTimeUp(qId: string) {
    if (autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    setPhase("waiting");

    // Already submitted (grading in flight, or already graded) -- the
    // existing submit/result takes it from here, nothing more to do.
    if (submittingRef.current || resultRef.current) return;

    const trimmedName = nameRef.current.trim();
    const trimmedCode = codeRef.current.trim();
    if (!trimmedName || !trimmedCode) return; // nothing to submit -- render shows the neutral note

    setWasAutoSubmitted(true);
    performSubmit(qId, trimmedName, trimmedCode);
  }

  function applyStatus(status: LectureStatus) {
    if (status.finished) {
      questionIdRef.current = null;
      setQuestionId(null);
      setSecondsRemaining(null);
      setPhase("finished");
      if (!recapFetchedRef.current) {
        recapFetchedRef.current = true;
        const studentName = nameRef.current.trim();
        if (studentName) {
          fetchStudentRecap(studentName)
            .then(setRecap)
            .catch(() => {
              // No recap to show -- the headline/closing message still stand on their own.
            });
        }
      }
      return;
    }

    if (!status.question) {
      // No task live right now -- either before the first one, or the
      // lecturer has closed one but not started the next yet.
      questionIdRef.current = null;
      setQuestionId(null);
      setSecondsRemaining(null);
      setDurationSeconds(null);
      if (phaseRef.current !== "waiting") setPhase("waiting");
      return;
    }

    const q = status.question;
    setSecondsRemaining(q.seconds_remaining);

    if (q.id !== questionIdRef.current) {
      // A new task (or the first one) -- reset the editor for it. A student
      // who loads the page after this task's timer has already run out
      // just sees the waiting screen; there's no code of theirs to submit.
      questionIdRef.current = q.id;
      // A late joiner (this task's timer is already at 0 when it first
      // loads) has nothing of theirs to submit -- mark it handled so
      // handleTimeUp never fires for this question, rather than attempting
      // a submit under a name/code that were never actually entered for it.
      autoSubmittedRef.current = q.seconds_remaining <= 0;
      setWasAutoSubmitted(false);
      recapFetchedRef.current = false;
      setRecap(null);
      setQuestionId(q.id);
      setPromptText(q.prompt);
      setExample(q.example);
      setDurationSeconds(q.duration_seconds);
      updateCode("");
      setResult(null);
      resultRef.current = null;
      setErrorMessage(null);
      loadHistory(nameRef.current.trim(), q.id);
      setPhase(q.seconds_remaining > 0 ? "answering" : "waiting");
      return;
    }

    if (q.seconds_remaining <= 0 && phaseRef.current === "answering") {
      handleTimeUp(q.id);
    }
  }

  useEffect(() => {
    if (!joined) return; // Still on the join-code screen -- nothing to poll yet.
    let cancelled = false;
    const poll = () => {
      fetchLectureStatus()
        .then((status) => {
          if (!cancelled) applyStatus(status);
        })
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };
    poll();
    const t = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
    // applyStatus reads current state via refs -- only `joined` needs to
    // retrigger this (start polling right after a successful join).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined]);

  async function handleJoin() {
    const trimmedName = joinNameInput.trim();
    const code = joinCodeInput.trim();
    if (!trimmedName) {
      setJoinError("Enter your name.");
      return;
    }
    if (!code) {
      setJoinError("Enter the code your lecturer shared.");
      return;
    }
    setJoining(true);
    setJoinError(null);
    try {
      await joinLectureApi(code, trimmedName);
      markJoinedThisSession(trimmedName);
      updateName(trimmedName); // carries forward to the answering screen's own name field
      setJoined(true);
      setPhase("loading");
    } catch (e) {
      setJoinError(e instanceof Error ? e.message : "Could not join.");
    } finally {
      setJoining(false);
    }
  }

  // Local 1s countdown between polls so the timer doesn't visibly jump only
  // every POLL_MS -- re-synced to the server's own count on every poll
  // above (via setSecondsRemaining(q.seconds_remaining)) rather than left to
  // free-run, so client clock drift can't push it out of step with what the
  // lecturer dashboard shows.
  useEffect(() => {
    if (phase !== "answering") return;
    const t = window.setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev == null) return prev;
        const next = prev - 1;
        if (next <= 0 && questionIdRef.current) {
          handleTimeUp(questionIdRef.current);
        }
        return Math.max(0, next);
      });
    }, 1000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, questionId]);

  async function handleSubmit() {
    const trimmedName = name.trim();
    const trimmedCode = code.trim();

    setErrorMessage(null);
    setResult(null);
    resultRef.current = null;
    setWasAutoSubmitted(false);

    if (!trimmedName) {
      setErrorMessage("Enter your name first.");
      return;
    }
    if (!trimmedCode) {
      setErrorMessage("Write some code first.");
      return;
    }
    if (!questionId) {
      setErrorMessage("No task is live right now.");
      return;
    }

    await performSubmit(questionId, trimmedName, trimmedCode);
  }

  const verdictClass = (v: Verdict) => "verdict-badge verdict-" + v;
  const verdictLabel = (v: Verdict) => VERDICT_LABELS[v] || v;

  if (phase === "join") {
    return (
      <>
        <header>
          <h1>Interactive Lecture</h1>
          <p>Enter the code your lecturer shared to join.</p>
        </header>
        <main className="waiting-main">
          <div className="card accent-navy waiting-card">
            <h2>Enter the lecture</h2>
            <label htmlFor="join-name">Your name</label>
            <input
              type="text"
              id="join-name"
              placeholder="e.g. Lara Pinheiro"
              autoFocus
              value={joinNameInput}
              onChange={(e) => setJoinNameInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleJoin();
              }}
            />
            <label htmlFor="join-code">Join code</label>
            <input
              type="text"
              id="join-code"
              placeholder="e.g. 482913"
              inputMode="numeric"
              value={joinCodeInput}
              onChange={(e) => setJoinCodeInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleJoin();
              }}
            />
            <button onClick={handleJoin} disabled={joining}>
              {joining ? "Joining..." : "Join"}
            </button>
            {joinError && (
              <div id="error-box" style={{ display: "block" }}>
                {joinError}
              </div>
            )}
          </div>
        </main>
      </>
    );
  }

  if (phase === "loading") {
    return (
      <>
        <header>
          <h1>Interactive Lecture</h1>
        </header>
        <main>
          <div className="card">Loading...</div>
        </main>
      </>
    );
  }

  if (phase === "finished") {
    const correctCount = recap ? recap.results.filter((r) => r.verdict === "correct").length : 0;
    return (
      <>
        <header>
          <h1>Interactive Lecture</h1>
        </header>
        <main className="waiting-main">
          <div className="card accent-navy waiting-card">
            <h2>That's the lecture. Thanks for working through it.</h2>
            <p className="waiting-message">Nothing else needed from you here. It's safe to close this tab.</p>
          </div>
          {recap && (
            <div className="card" id="recap-card">
              <h2>Your recap</h2>
              <div id="recap-summary-line">
                {recap.attempted} of {recap.total} tasks attempted, {correctCount} correct
              </div>
              <ul id="recap-list">
                {recap.results.map((r) => (
                  <li key={r.question_id}>
                    <span>{r.title}</span>
                    {r.attempted && r.verdict ? (
                      <span className={verdictClass(r.verdict)}>{verdictLabel(r.verdict)}</span>
                    ) : (
                      <span className="recap-not-attempted">Not attempted</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </main>
      </>
    );
  }

  const isWaiting = phase === "waiting";
  // The STATE-1 sub-cases the "time's up" panel below can be in -- derived
  // from state rather than tracked separately, since once the editor goes
  // read-only `code`/`result`/`submitting` don't change except through the
  // auto-submit/grading flow itself.
  const waitingIsGrading = isWaiting && submitting;
  const waitingIsEmpty = isWaiting && !result && !submitting && !errorMessage && !code.trim();

  return (
    <>
      <header>
        <h1>Interactive Lecture</h1>
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
              onChange={(e) => updateName(e.target.value)}
              onBlur={(e) => loadHistory(e.target.value.trim(), questionId)}
            />

            <div id="timer-box" style={{ display: secondsRemaining != null ? "block" : "none" }}>
              <div className="timer-label">{isWaiting ? "Time's up" : "Time remaining"}</div>
              <div className={"timer-value" + (secondsRemaining === 0 ? " time-up" : "")}>
                {secondsRemaining != null ? formatMMSS(secondsRemaining) : ""}
              </div>
              <div id="timer-bar-track">
                <div
                  id="timer-bar-fill"
                  style={{
                    width:
                      durationSeconds && secondsRemaining != null
                        ? `${Math.min(100, Math.max(0, (secondsRemaining / durationSeconds) * 100))}%`
                        : "0%",
                  }}
                />
              </div>
            </div>

            {isWaiting && (
              <div id="waiting-status">
                <div className="pulse-indicator">
                  <span className="pulse-dot" />
                  Waiting for the next task...
                </div>
                <div className="waiting-attention-note">Your lecturer is going over the results now.</div>
              </div>
            )}

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
              readOnly={isWaiting}
              onChange={(e) => updateCode(e.target.value)}
            />
            {!isWaiting && (
              <>
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
              </>
            )}
            {isWaiting && (
              <div id="waiting-submit-status">
                {waitingIsGrading && (
                  <div id="submit-status" style={{ display: "block" }}>
                    <span className="spinner" style={{ display: "inline-block" }} />
                    {wasAutoSubmitted && <div>Your code was submitted automatically.</div>}
                    <div>{statusText || "Grading..."}</div>
                  </div>
                )}
                {waitingIsEmpty && (
                  <div className="neutral-note">
                    No code to submit this time. That's fine, the next one's coming.
                  </div>
                )}
                {errorMessage && !waitingIsGrading && (
                  <div id="error-box" style={{ display: "block" }}>
                    {errorMessage}
                  </div>
                )}
              </div>
            )}
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
