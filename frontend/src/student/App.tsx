import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type {
  LectureStatus,
  SharedExample,
  StudentAttempt,
  StudentRecap,
  SubmitResponse,
  TestCase,
  Verdict,
  VisibleTestFile,
} from "../shared/types";
import {
  fetchLectureStatus,
  fetchMyAttempts,
  fetchStudentRecap,
  joinLecture as joinLectureApi,
  sendActivity,
  submitCode as submitCodeApi,
} from "../shared/api";
import { isUntouched, starterCode } from "./starterCode";
import { TestFiles } from "./TestFiles";
import { Badge, BigTimer, BrandMark, Button, Callout, Card, Code, Eyebrow, Input, Label, Spinner, StatusLine, TimeLine } from "../shared/ui";
import { CodeBlock, FailingTestStrip } from "../shared/code";
import { HERO_FILL, SCORE_LINE, TILE_TONE } from "../shared/verdictStyles";
import { cx } from "../shared/cx";
import type { Tone } from "../shared/ui";
// Monaco is most of this page's weight -- loaded only once a task is live,
// so the join and waiting screens stay instant.
const CodeEditor = lazy(() => import("./CodeEditor").then((m) => ({ default: m.CodeEditor })));

const VERDICT_LABELS: Record<string, string> = {
  correct: "Correct",
  partially_correct: "Partially Correct",
  incorrect: "Incorrect",
  error: "Error",
};

const VERDICT_TONES: Record<string, Tone> = {
  correct: "success",
  partially_correct: "warning",
  incorrect: "danger",
  error: "danger",
};

export interface VerdictBadgeProps {
  verdict: Verdict;
}

function VerdictBadge({ verdict }: VerdictBadgeProps) {
  return (
    <Badge tone={VERDICT_TONES[verdict] ?? "neutral"} dot>
      {VERDICT_LABELS[verdict] || verdict}
    </Badge>
  );
}

export interface ExampleIoProps {
  rows: Array<[label: string, value: string]>;
}

// The task's example, label above a monospace box -- same as the lecturer's
// "Show task" panel. Long values scroll inside their box.
function ExampleIo({ rows }: ExampleIoProps) {
  return (
    <div className="grid gap-3">
      {rows.map(([label, value]) => (
        <div key={label}>
          <div className="mb-1.5 text-xs text-zinc-500">{label}</div>
          <pre className="max-h-40 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[13px] text-zinc-900">
            {value}
          </pre>
        </div>
      ))}
    </div>
  );
}

export interface StudentPageProps {
  children: ReactNode;
  className?: string;
}

// Same frame as the lecturer's live dashboard: full width, generous sides.
function StudentPage({ children, className }: StudentPageProps) {
  return <main className={cx("mx-auto w-full max-w-[112rem] px-5 pb-24 sm:px-8", className)}>{children}</main>;
}

// How often the student page checks in with the backend for the live
// question/timer/finished state -- see /api/lecture/status in backend/
// main.py. Faster than the lecturer dashboard's 3s poll since the countdown
// (and the auto-submit-on-timeout it drives) benefits more from staying
// in sync.
const POLL_MS = 2000;

// How often the editor reports "still here, typed / didn't type" while a
// task is running (POST /api/lecture/activity). The lecturer's dashboard
// marks a student "away" after a few missed heartbeats (AWAY_AFTER_SECONDS
// in backend/main.py), and the reply is where an idle nudge arrives.
const HEARTBEAT_MS = 10000;

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
// Which lecture the join was for -- a join only counts for that one lecture
// (see applyStatus: a different lecture_id means a new lecture, back to the
// join screen).
const JOIN_LECTURE_KEY = "lecture_joined_id";

function hasJoinedThisSession(): boolean {
  try {
    return sessionStorage.getItem(JOIN_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function getJoinedLectureId(): number | null {
  try {
    const v = sessionStorage.getItem(JOIN_LECTURE_KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

function forgetJoin(): void {
  try {
    sessionStorage.removeItem(JOIN_SESSION_KEY);
    sessionStorage.removeItem(JOIN_LECTURE_KEY);
  } catch {
    // Best effort.
  }
}

function getJoinedName(): string {
  try {
    return sessionStorage.getItem(JOIN_NAME_KEY) || "";
  } catch {
    return "";
  }
}

function markJoinedThisSession(studentName: string, lectureId: number): void {
  try {
    sessionStorage.setItem(JOIN_SESSION_KEY, "1");
    sessionStorage.setItem(JOIN_NAME_KEY, studentName);
    sessionStorage.setItem(JOIN_LECTURE_KEY, String(lectureId));
  } catch {
    // Best effort -- worst case the student re-enters the code after a refresh.
  }
}

type Phase = "join" | "loading" | "answering" | "waiting" | "finished";

export default function App() {
  const [joined, setJoined] = useState(hasJoinedThisSession);
  const [phase, setPhase] = useState<Phase>(() => (hasJoinedThisSession() ? "loading" : "join"));
  // Pre-filled with the name from this tab's last join, if any (e.g. coming
  // back via "Back to home" after a lecture ended).
  const [joinNameInput, setJoinNameInput] = useState(getJoinedName);
  const [joinCodeInput, setJoinCodeInput] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  // Shown on the join screen after being sent back to it because a new
  // lecture started (see applyStatus).
  const [joinNotice, setJoinNotice] = useState<string | null>(null);
  const [questionId, setQuestionId] = useState<string | null>(null);
  const [language, setLanguage] = useState("python");
  const [promptText, setPromptText] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [example, setExample] = useState<TestCase | null>(null);
  const [durationSeconds, setDurationSeconds] = useState<number | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);

  // The name typed on the join screen (see JOIN_NAME_KEY) -- fixed for the
  // rest of the lecture, so submissions, the activity heartbeat and the
  // lecturer's per-student rows all stay under one name. Fixing a typo means
  // re-joining from a new tab.
  const [name, setName] = useState(getJoinedName);
  const [code, setCode] = useState("");
  // Mirrors of `name`/`code` for the auto-submit-on-timeout path, which can
  // fire from inside a setInterval/poll callback where the `name`/`code`
  // state captured at effect-setup time would otherwise be stale.
  const nameRef = useRef(getJoinedName());
  const codeRef = useRef("");
  // The live task's language, for the same callbacks (see isUntouched below).
  const languageRef = useRef("python");
  // Set on every keystroke, cleared by each heartbeat -- so a heartbeat
  // reports "typed since the last one" without ever sending the code.
  const editedRef = useRef(false);
  // The idle nudge from the last heartbeat, shown above the editor until the
  // student types or dismisses it.
  const [nudge, setNudge] = useState<string | null>(null);

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

  const [history, setHistory] = useState<StudentAttempt[] | null>(null);
  // Data files the student may open (status.question.files): the example's
  // during the task, every test's once time is up.
  const [files, setFiles] = useState<VisibleTestFile[]>([]);
  // The task is graded on this file (e.g. "result.txt") instead of printed output.
  const [outputFile, setOutputFile] = useState<string | null>(null);
  // What the lecturer is going over with the class right now -- see the
  // "On your lecturer's screen" card below.
  const [shownExamples, setShownExamples] = useState<SharedExample[]>([]);
  // Whether a task has gone live since this tab joined -- tells the waiting
  // screen's "lecture hasn't started yet" apart from "between tasks".
  const [hadTask, setHadTask] = useState(false);

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
  function handleEditorChange(v: string) {
    updateCode(v);
    editedRef.current = true;
    setNudge(null);
  }

  async function loadHistory(studentName: string, qId: string | null) {
    if (!studentName || !qId) {
      setHistory(null);
      return;
    }
    try {
      const rows = await fetchMyAttempts(qId, studentName);
      const mine = [...rows].sort((a, b) => a.attempt_number - b.attempt_number);
      setHistory(mine.length === 0 ? null : mine);
    } catch {
      setHistory(null);
    }
  }

  // Shared by the manual Submit button and the timeout auto-submit path --
  // both need the same status text, spinner, and result/error
  // handling, just triggered differently and with different validation
  // upstream of this call.
  async function performSubmit(qId: string, trimmedName: string, trimmedCode: string) {
    setSubmitting(true);
    submittingRef.current = true;
    setStatusText("Running your tests...");
    // Normally graded in about a second; longer means the class is submitting at
    // once (e.g. time's up) and this one is queued -- 10-20s with 150 students
    // (load_test.py). Say so, so a long wait doesn't look like a frozen page.
    slowNoticeRef.current = window.setTimeout(() => {
      setStatusText("Lots of students are submitting right now, so you're in a queue. It'll be graded shortly.");
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
      // Solved it -- nothing left to do on this task, so off to the waiting
      // screen. A wrong answer stays on the editor with its hint so the
      // student can resubmit (that's what escalates the hint tier).
      if (data.verdict === "correct") setPhase("waiting");
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
    // An untouched starter skeleton is nothing the student wrote, same as an empty box.
    if (!trimmedName || isUntouched(trimmedCode, languageRef.current)) return; // render shows the neutral note

    setWasAutoSubmitted(true);
    performSubmit(qId, trimmedName, trimmedCode);
  }

  function applyStatus(status: LectureStatus) {
    // A different lecture than the one this tab joined (or a join saved
    // before lecture ids were tracked) -- the old join doesn't carry over.
    // Back to the join screen for the new lecture's code.
    if (status.lecture_id !== getJoinedLectureId() && !(status.finished && phaseRef.current === "finished")) {
      forgetJoin();
      setJoined(false);
      setJoinCodeInput(""); // the old lecture's code -- keep the name, not this
      setPhase("join");
      setJoinNotice(status.finished ? null : "A new lecture has started. Enter its code to join.");
      return;
    }
    setShownExamples(status.shown_examples ?? []);
    if (status.finished) {
      // Lecture's over: this tab's join is used up. The finished screen stays
      // up, but a refresh (or a new lecture) goes back to the join screen.
      forgetJoin();
      questionIdRef.current = null;
      setQuestionId(null);
      setFiles([]);
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
      setFiles([]);
      setSecondsRemaining(null);
      setDurationSeconds(null);
      if (phaseRef.current !== "waiting") setPhase("waiting");
      return;
    }

    const q = status.question;
    setSecondsRemaining(q.seconds_remaining);
    setFiles(q.files ?? []);
    setOutputFile(q.output_file ?? null);

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
      setHadTask(true);
      setPromptText(q.prompt);
      setTaskTitle(q.title);
      setLanguage(q.language);
      languageRef.current = q.language;
      editedRef.current = false;
      setNudge(null);
      setExample(q.example);
      setDurationSeconds(q.duration_seconds);
      updateCode(starterCode(q.language));
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

  // Activity heartbeat -- only while answering, so the waiting screen (time's
  // up, or already solved) never earns a nudge or counts as idle.
  useEffect(() => {
    if (phase !== "answering" || !questionId) return;
    const beat = () => {
      const studentName = nameRef.current.trim();
      if (!studentName) return;
      const edited = editedRef.current;
      editedRef.current = false;
      sendActivity(studentName, questionId, edited)
        .then((r) => {
          if (r.nudge) setNudge(r.nudge);
        })
        .catch(() => {
          // Missed heartbeat -- the next one catches up.
        });
    };
    beat();
    const t = window.setInterval(beat, HEARTBEAT_MS);
    return () => window.clearInterval(t);
  }, [phase, questionId]);

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
      const joinedLecture = await joinLectureApi(code, trimmedName);
      markJoinedThisSession(trimmedName, joinedLecture.lecture_id);
      setJoinNotice(null);
      updateName(trimmedName); // the name for the rest of this lecture (shown, not editable, while answering)
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

  const joinedName = joined ? name.trim() : "";

  if (phase === "join") {
    return (
      <>
        <StudentBar />
        <StudentPage className="grid max-w-6xl gap-10 pt-14 sm:pt-24 lg:grid-cols-12 lg:gap-16">
          <section className="animate-fade-in-up lg:col-span-5">
            <Eyebrow>Student</Eyebrow>
            <h1 className="mt-4 text-4xl font-bold tracking-tight text-balance text-zinc-950 sm:text-5xl">
              Join a lecture
            </h1>
            <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-zinc-500">
              Enter your name and the code your lecturer shared. You'll get each task here as it starts.
            </p>
          </section>
          <section className="lg:col-span-7 lg:pt-8">
            <Card className="animate-fade-in-up p-6 sm:p-8">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleJoin();
                }}
              >
                {joinNotice && (
                  <Callout tone="info" className="mb-6">
                    {joinNotice}
                  </Callout>
                )}
                <Label htmlFor="join-name">Your name</Label>
                <Input
                  type="text"
                  id="join-name"
                  placeholder="e.g. Lara Pinheiro"
                  autoFocus
                  className="h-11 text-[15px]"
                  value={joinNameInput}
                  onChange={(e) => setJoinNameInput(e.target.value)}
                />
                <Label htmlFor="join-code" className="mt-6">
                  Join code
                </Label>
                <Input
                  type="text"
                  id="join-code"
                  placeholder="482913"
                  inputMode="numeric"
                  autoComplete="off"
                  mono
                  className="h-16 text-3xl font-bold tracking-[0.18em] tabular-nums"
                  value={joinCodeInput}
                  onChange={(e) => setJoinCodeInput(e.target.value)}
                />
                <Button type="submit" size="lg" className="mt-7 w-full" disabled={joining}>
                  {joining && <Spinner />}
                  {joining ? "Joining..." : "Join"}
                </Button>
                {joinError && (
                  <Callout tone="danger" role="alert" className="mt-4">
                    {joinError}
                  </Callout>
                )}
              </form>
            </Card>
          </section>
        </StudentPage>
      </>
    );
  }

  if (phase === "loading") {
    return (
      <>
        <StudentBar name={joinedName} />
        <StudentPage className="pt-14">
          <p className="flex items-center gap-2 text-sm text-zinc-500">
            <Spinner /> Loading...
          </p>
        </StudentPage>
      </>
    );
  }

  if (phase === "finished") {
    const correctCount = recap ? recap.results.filter((r) => r.verdict === "correct").length : 0;
    return (
      <>
        <StudentBar name={joinedName} />
        <StudentPage className="grid max-w-6xl gap-10 pt-14 sm:pt-24 lg:grid-cols-12 lg:gap-16">
          <section className="animate-fade-in-up lg:col-span-5">
            <StatusLine state="closed" label="Lecture over" />
            <h1 className="mt-4 text-4xl font-bold tracking-tight text-balance text-zinc-950 sm:text-5xl">
              Thanks for working through it.
            </h1>
            <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-zinc-500">
              Nothing else needed from you here. It's safe to close this tab.
            </p>
            {/* The join screen is the student's "home" -- this tab's join was
                already forgotten when the lecture ended (see applyStatus), so a
                fresh load lands there, ready for the next lecture's code. */}
            <Button variant="secondary" className="mt-8" onClick={() => (window.location.href = "student.html")}>
              Back to home
            </Button>
          </section>
          {recap && (
            <section className="animate-fade-in-up lg:col-span-7 lg:pt-8" aria-label="Your recap">
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-4xl font-semibold tracking-tight text-zinc-950 tabular-nums">
                  {correctCount}
                </span>
                <span className="font-mono text-xl text-zinc-400 tabular-nums">/ {recap.total}</span>
                <span className="ml-1 text-sm text-zinc-500">
                  correct · {recap.attempted} attempted
                </span>
              </div>
              <ul className="mt-6 border-t border-zinc-200">
                {recap.results.map((r) => {
                  const kind = r.attempted && r.verdict ? r.verdict : "none";
                  return (
                    <li key={r.question_id} className="flex items-center gap-4 border-b border-zinc-200 py-4">
                      <span className={cx("size-3 flex-none rounded-[3px]", HERO_FILL[kind], kind === "none" && "border border-zinc-300")} aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate text-[15px] text-zinc-900">{r.title}</span>
                      {r.attempted && r.verdict ? (
                        <VerdictBadge verdict={r.verdict} />
                      ) : (
                        <span className="text-[13px] text-zinc-400">Not attempted</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </StudentPage>
      </>
    );
  }

  if (phase === "waiting") {
    // One screen for every "nothing to type right now" moment -- only the
    // headline/message change with what this student just did.
    let title: string;
    let message: string;
    if (submitting) {
      title = "Time's up";
      message = wasAutoSubmitted ? "Your code was submitted automatically." : "Your code is being graded.";
    } else if (errorMessage) {
      title = "Time's up";
      message = "Waiting for your lecturer to give the next task.";
    } else if (result?.verdict === "correct") {
      title = "Good job!";
      message = "You solved it. Waiting for your lecturer to give the next task.";
    } else if (result) {
      title = "Thanks for submitting";
      message = "Your lecturer will go over the results. Waiting for the next task.";
    } else if (hadTask) {
      title = "Time's up";
      message = "No code submitted for this task. That's fine, the next one's coming.";
    } else {
      title = `You're in${name.trim() ? `, ${name.trim()}` : ""}!`;
      message = "Waiting for your lecturer to start the first task.";
    }
    const showFiles = questionId != null && files.some((f) => f.test > 0);

    return (
      <>
        <StudentBar name={joinedName} />
        <StudentPage>
          <header className="animate-fade-in-up pt-10 sm:pt-14">
            <div className="flex flex-wrap items-end justify-between gap-x-12 gap-y-6">
              <div className="min-w-0 flex-1 basis-96">
                {submitting ? (
                  <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-600">
                    <Spinner /> {statusText || "Grading..."}
                  </div>
                ) : (
                  <StatusLine
                    state="live"
                    label="Waiting for your lecturer"
                    items={[hadTask && taskTitle]}
                  />
                )}
                <h1 className="mt-3 text-4xl font-bold tracking-tight text-balance text-zinc-950 lg:text-5xl">{title}</h1>
                <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-zinc-500">{message}</p>
              </div>
              {result && !submitting && (
                <div className="text-right">
                  <VerdictBadge verdict={result.verdict} />
                  <div className="mt-2 font-mono text-5xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
                    {result.tests_passed}
                    <span className="text-2xl text-zinc-400">/{result.tests_total}</span>
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">tests passed</div>
                </div>
              )}
            </div>
            {errorMessage && !submitting && (
              <Callout tone="danger" role="alert" className="mt-6 max-w-2xl">
                {errorMessage}
              </Callout>
            )}
            <div className="mt-8 h-px w-full bg-zinc-200" aria-hidden="true" />
          </header>

          {(shownExamples.length > 0 || showFiles) && (
            <div
              className={cx(
                "grid items-start gap-x-14 gap-y-12 pt-10",
                shownExamples.length > 0 && showFiles && "lg:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)]",
              )}
            >
              {shownExamples.length > 0 && (
                <section className="min-w-0 animate-fade-in-up" aria-label="On your lecturer's screen">
                  <div className="mb-5 flex flex-wrap items-baseline gap-3">
                    <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Let's look at this together</h2>
                    <span className="text-[13px] text-zinc-400">
                      {shownExamples.length > 1
                        ? "attempts your lecturer picked from the class"
                        : "an attempt your lecturer picked from the class"}
                    </span>
                  </div>
                  <div className={cx("grid gap-8", shownExamples.length > 1 && "2xl:grid-cols-2")}>
                    {shownExamples.map((ex, i) => (
                      <div key={i} className="min-w-0">
                        {shownExamples.length > 1 && <Eyebrow className="mb-2">Example {i + 1}</Eyebrow>}
                        {ex.failing_test && (
                          <FailingTestStrip
                            className="mb-2"
                            test={{
                              stdin: ex.failing_test.stdin,
                              expected: ex.failing_test.expected_stdout,
                              got: ex.failing_test.stdout,
                              error: ex.failing_test.stderr,
                            }}
                          />
                        )}
                        <CodeBlock lines={ex.source_code.split("\n").length}>{ex.source_code}</CodeBlock>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {showFiles && questionId && (
                <section className="min-w-0 animate-fade-in-up" aria-label="Test files">
                  <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Test files</h2>
                  <p className="mt-1 mb-4 text-[13px] text-zinc-500">Time&apos;s up, so every test&apos;s files are open now.</p>
                  <TestFiles key={questionId} questionId={questionId} files={files} groupByTest />
                </section>
              )}
            </div>
          )}
        </StudentPage>
      </>
    );
  }

  const timeFraction = durationSeconds && secondsRemaining != null ? secondsRemaining / durationSeconds : 0;
  const exampleFiles = files.filter((f) => f.test === 0);

  return (
    <>
      <StudentBar name={joinedName || name} />
      <StudentPage>
        <header className="pt-8 sm:pt-10">
          <div className="flex flex-wrap items-end justify-between gap-x-12 gap-y-6">
            <div className="min-w-0 flex-1 basis-96">
              <StatusLine
                state={secondsRemaining === 0 ? "closed" : "live"}
                label={secondsRemaining === 0 ? "Closed" : "Live"}
                items={[
                  <span className="capitalize">{language}</span>,
                  history && `${history.length} attempt${history.length === 1 ? "" : "s"}`,
                ]}
              />
              <h1 className="mt-3 text-4xl font-bold tracking-tight text-balance text-zinc-950 lg:text-5xl">
                {taskTitle || "Task"}
              </h1>
            </div>
            {secondsRemaining != null && <BigTimer seconds={secondsRemaining} />}
          </div>
          <TimeLine fraction={timeFraction} className="mt-8" />
        </header>

        <div className="grid items-start gap-x-14 gap-y-10 pt-10 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)] 2xl:grid-cols-[minmax(0,30rem)_minmax(0,1fr)]">
          <aside className="grid min-w-0 gap-8 lg:sticky lg:top-20" aria-label="Task">
            <section>
              <Eyebrow>Task</Eyebrow>
              <p className="mt-2 max-h-[45vh] overflow-y-auto pr-2 text-[15px] leading-relaxed whitespace-pre-wrap text-zinc-800">
                {promptText}
              </p>
              {outputFile && (
                <div className="mt-4 border-l-2 border-zinc-900 py-1 pl-3.5 text-[13px] leading-relaxed text-zinc-600">
                  Write your answer to <Code>{outputFile}</Code>. That file is checked, not what your program prints.
                </div>
              )}
            </section>
            {example && (
              <section>
                <Eyebrow className="mb-3">Example</Eyebrow>
                <ExampleIo
                  rows={[
                    ["Input", example.stdin.trimEnd() || "(none)"],
                    [outputFile ? `Expected ${outputFile}` : "Expected output", example.expected_stdout.trimEnd()],
                  ]}
                />
              </section>
            )}
            {questionId && exampleFiles.length > 0 && (
              <section>
                <Eyebrow className="mb-2">Files</Eyebrow>
                <p className="mb-3 text-[13px] leading-relaxed text-zinc-500">
                  Your program can open these by name, e.g. <Code>open(&quot;{exampleFiles[0].name}&quot;)</Code>. The
                  graded tests use their own versions, shown when time is up.
                </p>
                <TestFiles key={questionId} questionId={questionId} files={exampleFiles} />
              </section>
            )}
            {history && (
              <section aria-label="Your attempts">
                <Eyebrow className="mb-3">Your attempts</Eyebrow>
                <ul className="grid grid-cols-[repeat(auto-fill,minmax(3.25rem,1fr))] gap-1.5">
                  {history.map((row) => {
                    const v = row.verdict ?? "error";
                    const share = row.tests_total ? row.tests_passed / row.tests_total : 0;
                    return (
                      <li
                        key={row.id}
                        title={`Attempt ${row.attempt_number}: ${row.verdict || "unknown"}, ${row.tests_passed}/${row.tests_total} tests`}
                        className={cx(
                          "flex h-12 flex-col justify-between rounded-md border px-2 pt-1.5 pb-2",
                          TILE_TONE[v],
                        )}
                      >
                        <span className="font-mono text-xs leading-tight">#{row.attempt_number}</span>
                        <span className="block h-[3px] overflow-hidden rounded-sm bg-black/10" aria-hidden="true">
                          <span
                            className={cx("block h-full rounded-sm", SCORE_LINE[v])}
                            style={{ width: `${Math.max(share, 0.04) * 100}%` }}
                          />
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}
          </aside>

          <div className="grid min-w-0 gap-6">
            {nudge && (
              <div
                className="flex animate-fade-in-up flex-col items-start gap-3 rounded-lg border border-sky-200 bg-sky-50 px-5 py-4 sm:flex-row sm:items-center"
                role="status"
              >
                <p className="flex-1 text-sm leading-relaxed text-sky-950">{nudge}</p>
                <Button variant="secondary" size="sm" onClick={() => setNudge(null)}>
                  Got it
                </Button>
              </div>
            )}

            <section aria-label="Your code">
              <div className="mb-3 flex items-center gap-3">
                <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Your code</h2>
                <div className="ml-auto flex items-center gap-3">
                  {submitting && statusText && (
                    <span className="hidden text-[13px] text-zinc-500 sm:inline">{statusText}</span>
                  )}
                  <Button size="lg" disabled={submitting} onClick={handleSubmit}>
                    {submitting && <Spinner />}
                    {submitting ? "Running..." : "Submit"}
                  </Button>
                </div>
              </div>
              <Suspense
                fallback={
                  <div className="h-[460px] rounded-lg border border-zinc-200 bg-white p-3 text-sm text-zinc-500">
                    Loading editor...
                  </div>
                }
              >
                <CodeEditor
                  key={questionId}
                  language={language}
                  initialValue={starterCode(language)}
                  onChange={handleEditorChange}
                />
              </Suspense>
              {submitting && statusText && <p className="mt-2 text-[13px] text-zinc-500 sm:hidden">{statusText}</p>}
              {errorMessage && (
                <Callout tone="danger" role="alert" className="mt-4">
                  {errorMessage}
                </Callout>
              )}
            </section>

            {result && (
              <section className="animate-fade-in-up border-t border-zinc-200 pt-8" aria-label="Result">
                <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
                  <div>
                    <div className="font-mono text-4xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
                      {result.tests_passed}
                      <span className="text-xl text-zinc-400">/{result.tests_total}</span>
                    </div>
                    <div className="mt-1.5 text-xs text-zinc-500">tests passed</div>
                  </div>
                  <VerdictBadge verdict={result.verdict} />
                  {result.hint_tier ? (
                    <div className="ml-auto w-44">
                      <div className="mb-1.5 text-xs text-zinc-500">
                        Hint <span className="font-mono text-zinc-900">{result.hint_tier}</span> of{" "}
                        <span className="font-mono text-zinc-900">{result.hint_ceiling}</span>
                      </div>
                      <div className="flex gap-1">
                        {Array.from({ length: result.hint_ceiling ?? 0 }, (_, i) => i + 1).map((i) => (
                          <div
                            key={i}
                            className={cx("h-1 flex-1 rounded-sm", i <= (result.hint_tier ?? 0) ? "bg-zinc-900" : "bg-zinc-200")}
                          />
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
                <p className="mt-6 max-w-3xl text-base leading-relaxed text-zinc-900">{result.feedback}</p>
                {result.traceback && (
                  <details className="mt-6">
                    <summary className="cursor-pointer rounded-sm text-[13px] font-medium text-zinc-500 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900">
                      Your program's error output
                    </summary>
                    <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-zinc-950 px-4 py-3 font-mono text-[13px] leading-relaxed text-zinc-100">
                      {result.traceback}
                    </pre>
                  </details>
                )}
                {result.hidden_crash && (
                  <p className="mt-4 max-w-3xl text-sm leading-relaxed text-zinc-500">
                    Your program crashed on a hidden test{result.hidden_error ? ` (${result.hidden_error})` : ""}. Its
                    error output isn&apos;t shown, because it could reveal that test&apos;s data. Try inputs like the
                    hidden tests might use.
                  </p>
                )}
              </section>
            )}
          </div>
        </div>
      </StudentPage>
    </>
  );
}

export interface StudentBarProps {
  name?: string;
}

// Same top bar as the lecturer pages (shared/NavBar.tsx's look), minus the
// links -- a student has nowhere else in the app to go. The right side shows
// who this tab joined as once that's known.
function StudentBar({ name }: StudentBarProps) {
  return (
    <nav className="sticky top-0 z-50 border-b border-zinc-200 bg-zinc-50/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[112rem] items-center justify-between gap-4 px-5 sm:px-8">
        <BrandMark compact />
        {name && (
          <span className="flex max-w-[60%] items-center gap-2 truncate text-[13px] text-zinc-500">
            <span className="grid size-6 flex-none place-items-center rounded-md bg-zinc-200 font-mono text-[11px] font-semibold text-zinc-700">
              {name.trim().charAt(0).toUpperCase()}
            </span>
            <strong className="truncate font-semibold text-zinc-900">{name}</strong>
          </span>
        )}
      </div>
    </nav>
  );
}
