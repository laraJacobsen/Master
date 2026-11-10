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
import { Badge, BrandMark, Button, Callout, Card, Code, Eyebrow, Input, Label, ProgressBar, SectionTitle, Spinner } from "../shared/ui";
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

export interface TestsPassedProps {
  passed: number;
  total: number;
}

function TestsPassed({ passed, total }: TestsPassedProps) {
  return (
    <span className="text-[13px] text-zinc-500">
      <span className="font-mono text-zinc-900 tabular-nums">
        {passed}/{total}
      </span>{" "}
      tests passed
    </span>
  );
}

export interface IoListProps {
  rows: Array<[label: string, value: string]>;
  className?: string;
}

// Label / monospace value pairs (example input, expected, got, ...).
function IoList({ rows, className }: IoListProps) {
  return (
    <dl className={cx("grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-[13px]", className)}>
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-zinc-500">{label}</dt>
          <dd className="font-mono break-words whitespace-pre-wrap text-zinc-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function failingRows(t: NonNullable<SharedExample["failing_test"]>): Array<[string, string]> {
  const rows: Array<[string, string]> = [
    ["Input", t.stdin.trimEnd()],
    ["Expected", t.expected_stdout.trimEnd()],
    ["Got", t.stdout.trim() || "(nothing)"],
  ];
  if (t.stderr) rows.push(["Error", t.stderr.trim().split("\n").pop() ?? ""]);
  return rows;
}

export interface NarrowMainProps {
  children: ReactNode;
}

// Single-column screens: join, waiting, finished.
function NarrowMain({ children }: NarrowMainProps) {
  return <main className="mx-auto grid w-full max-w-xl gap-5 px-5 pt-12 pb-20 sm:pt-20">{children}</main>;
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

function formatMMSS(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

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
        <NarrowMain>
          <div className="animate-fade-in-up">
            <Eyebrow>Student</Eyebrow>
            <h1 className="mt-3 text-4xl font-bold tracking-tight text-zinc-950">Join a lecture</h1>
            <p className="mt-3 text-[15px] text-zinc-500">Enter your name and the code your lecturer shared.</p>
          </div>
          <Card className="animate-fade-in-up p-6 sm:p-7">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleJoin();
              }}
            >
              {joinNotice && (
                <Callout tone="info" className="mb-5">
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
              <Label htmlFor="join-code" className="mt-5">
                Join code
              </Label>
              <Input
                type="text"
                id="join-code"
                placeholder="482913"
                inputMode="numeric"
                autoComplete="off"
                mono
                className="h-14 text-2xl font-semibold tracking-[0.2em] tabular-nums"
                value={joinCodeInput}
                onChange={(e) => setJoinCodeInput(e.target.value)}
              />
              <Button type="submit" size="lg" className="mt-6 w-full" disabled={joining}>
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
        </NarrowMain>
      </>
    );
  }

  if (phase === "loading") {
    return (
      <>
        <StudentBar name={joinedName} />
        <NarrowMain>
          <p className="flex items-center gap-2 text-sm text-zinc-500">
            <Spinner /> Loading...
          </p>
        </NarrowMain>
      </>
    );
  }

  if (phase === "finished") {
    const correctCount = recap ? recap.results.filter((r) => r.verdict === "correct").length : 0;
    return (
      <>
        <StudentBar name={joinedName} />
        <NarrowMain>
          <div className="animate-fade-in-up">
            <h1 className="text-3xl font-bold tracking-tight text-balance text-zinc-950">
              That's the lecture. Thanks for working through it.
            </h1>
            <p className="mt-3 text-[15px] text-zinc-500">Nothing else needed from you here. It's safe to close this tab.</p>
            {/* The join screen is the student's "home" -- this tab's join was
                already forgotten when the lecture ended (see applyStatus), so a
                fresh load lands there, ready for the next lecture's code. */}
            <Button variant="secondary" className="mt-6" onClick={() => (window.location.href = "student.html")}>
              Back to home
            </Button>
          </div>
          {recap && (
            <Card className="animate-fade-in-up">
              <SectionTitle
                meta={
                  <>
                    <span className="font-mono tabular-nums">{recap.attempted}</span> of{" "}
                    <span className="font-mono tabular-nums">{recap.total}</span> tasks attempted,{" "}
                    <span className="font-mono tabular-nums">{correctCount}</span> correct
                  </>
                }
              >
                Your recap
              </SectionTitle>
              <ul className="mt-3">
                {recap.results.map((r) => (
                  <li
                    key={r.question_id}
                    className="flex items-center justify-between gap-4 border-t border-zinc-200 py-3 text-sm first:border-t-0 last:pb-0"
                  >
                    <span className="text-zinc-900">{r.title}</span>
                    {r.attempted && r.verdict ? (
                      <VerdictBadge verdict={r.verdict} />
                    ) : (
                      <span className="text-[13px] text-zinc-400">Not attempted</span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </NarrowMain>
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

    return (
      <>
        <StudentBar name={joinedName} />
        <NarrowMain>
          <div className="animate-fade-in-up">
            <div className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1 text-[13px] font-medium text-zinc-600">
              {submitting ? (
                <Spinner />
              ) : (
                <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-emerald-500" aria-hidden="true" />
              )}
              {submitting ? statusText || "Grading..." : "Waiting for your lecturer"}
            </div>
            <h1 className="mt-5 text-4xl font-bold tracking-tight text-balance text-zinc-950">{title}</h1>
            <p className="mt-3 text-[15px] leading-relaxed text-zinc-500">{message}</p>
            {result && !submitting && (
              <div className="mt-5 flex items-center gap-3">
                <VerdictBadge verdict={result.verdict} />
                <TestsPassed passed={result.tests_passed} total={result.tests_total} />
              </div>
            )}
            {errorMessage && !submitting && (
              <Callout tone="danger" role="alert" className="mt-5">
                {errorMessage}
              </Callout>
            )}
          </div>

          {questionId && files.some((f) => f.test > 0) && (
            <Card className="mt-4 animate-fade-in-up">
              <SectionTitle>Test files</SectionTitle>
              <p className="mt-1 mb-4 text-[13px] text-zinc-500">Time&apos;s up, so every test&apos;s files are open now.</p>
              <TestFiles key={questionId} questionId={questionId} files={files} groupByTest />
            </Card>
          )}

          {shownExamples.length > 0 && (
            <Card className="animate-fade-in-up">
              <SectionTitle>Let's look at this together</SectionTitle>
              <p className="mt-1 mb-5 text-[13px] text-zinc-500">
                {shownExamples.length > 1
                  ? "Your lecturer picked these attempts from the class to go over."
                  : "Your lecturer picked this attempt from the class to go over."}
              </p>
              <div className="grid divide-y divide-zinc-200">
                {shownExamples.map((ex, i) => (
                  <div className="py-5 first:pt-0 last:pb-0" key={i}>
                    {shownExamples.length > 1 && (
                      <div className="mb-2 text-[13px] font-semibold text-zinc-900">Example {i + 1}</div>
                    )}
                    <pre className="overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 font-mono text-[13px] leading-relaxed break-words whitespace-pre-wrap">
                      {ex.source_code}
                    </pre>
                    {ex.failing_test && <IoList className="mt-3" rows={failingRows(ex.failing_test)} />}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </NarrowMain>
      </>
    );
  }

  const timeFraction = durationSeconds && secondsRemaining != null ? secondsRemaining / durationSeconds : 0;

  return (
    <>
      <StudentBar name={joinedName || name} />
      <main className="mx-auto grid w-full max-w-6xl items-start gap-5 px-5 pt-8 pb-20 sm:px-8 md:grid-cols-[360px_minmax(0,1fr)]">
        <div className="grid gap-5 md:sticky md:top-20">
          <Card>
            {secondsRemaining != null && (
              <div className="mb-6">
                <div className="flex items-baseline justify-between">
                  <Eyebrow>Time left</Eyebrow>
                  <span
                    className={cx(
                      "font-mono text-2xl font-semibold tracking-tight tabular-nums",
                      secondsRemaining === 0 ? "text-red-600" : "text-zinc-950",
                    )}
                  >
                    {formatMMSS(secondsRemaining)}
                  </span>
                </div>
                <ProgressBar
                  className="mt-2"
                  value={timeFraction}
                  tone={timeFraction <= 0.15 ? "danger" : "neutral"}
                  label="Time left"
                />
              </div>
            )}

            <h2 className="text-lg font-bold tracking-tight text-zinc-950">Task</h2>
            <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap text-zinc-700">{promptText}</p>
            {outputFile && (
              <div className="mt-4 border-l-2 border-zinc-900 bg-zinc-50 py-2.5 pr-3 pl-3.5 text-[13px] leading-relaxed text-zinc-700">
                Write your answer to <Code>{outputFile}</Code>. That file is checked, not what your program prints.
              </div>
            )}
            {example && (
              <div className="mt-5">
                <Eyebrow className="mb-2">Example</Eyebrow>
                <IoList
                  className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3"
                  rows={[
                    ["Input", example.stdin.trimEnd() || "(none)"],
                    [outputFile ?? "Output", example.expected_stdout.trimEnd()],
                  ]}
                />
              </div>
            )}
            {questionId && files.some((f) => f.test === 0) && (
              <div className="mt-5">
                <Eyebrow className="mb-2">Files</Eyebrow>
                <p className="mb-3 text-[13px] leading-relaxed text-zinc-500">
                  Your program can open these by name, e.g.{" "}
                  <Code>open(&quot;{files.find((f) => f.test === 0)?.name}&quot;)</Code>. The graded tests use their own
                  versions, shown when time is up.
                </p>
                <TestFiles key={questionId} questionId={questionId} files={files.filter((f) => f.test === 0)} />
              </div>
            )}
          </Card>

          {history && (
            <Card>
              <SectionTitle>Your attempts</SectionTitle>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {history.map((row) => (
                  <div
                    key={row.id}
                    className={cx(
                      "grid size-7 place-items-center rounded-md font-mono text-[11px] font-semibold text-white tabular-nums",
                      row.verdict === "correct"
                        ? "bg-emerald-600"
                        : row.verdict === "partially_correct"
                          ? "bg-amber-500"
                          : "bg-red-600",
                    )}
                    title={`Attempt ${row.attempt_number}: ${row.verdict || "unknown"}`}
                  >
                    {row.attempt_number}
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[13px] text-zinc-500">
                {(() => {
                  const passed = history.filter((r) => r.verdict === "correct").length;
                  return (
                    `${history.length} attempt${history.length === 1 ? "" : "s"} so far` +
                    (passed ? `, ${passed} correct` : "")
                  );
                })()}
              </p>
            </Card>
          )}
        </div>

        <div className="grid min-w-0 gap-5">
          {nudge && (
            <div
              className="flex animate-fade-in-up flex-col items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-5 py-4 sm:flex-row sm:items-center"
              role="status"
            >
              <p className="flex-1 text-sm leading-relaxed text-sky-950">{nudge}</p>
              <Button variant="secondary" size="sm" onClick={() => setNudge(null)}>
                Got it
              </Button>
            </div>
          )}
          <Card>
            <SectionTitle actions={<Badge>{language.charAt(0).toUpperCase() + language.slice(1)}</Badge>}>
              Your code
            </SectionTitle>
            <div className="mt-4">
              <Suspense
                fallback={
                  <div className="h-80 rounded-lg border border-zinc-200 p-3 text-sm text-zinc-500">Loading editor...</div>
                }
              >
                <CodeEditor
                  key={questionId}
                  language={language}
                  initialValue={starterCode(language)}
                  onChange={handleEditorChange}
                />
              </Suspense>
            </div>
            <div className="mt-4 flex items-center justify-end gap-3">
              {submitting && statusText && <span className="text-[13px] text-zinc-500">{statusText}</span>}
              <Button size="lg" disabled={submitting} onClick={handleSubmit}>
                {submitting && <Spinner />}
                {submitting ? "Running..." : "Submit"}
              </Button>
            </div>
            {errorMessage && (
              <Callout tone="danger" role="alert" className="mt-4">
                {errorMessage}
              </Callout>
            )}
          </Card>
          {result && (
            <Card className="animate-fade-in-up">
              <div className="flex flex-wrap items-center gap-3">
                <VerdictBadge verdict={result.verdict} />
                <TestsPassed passed={result.tests_passed} total={result.tests_total} />
              </div>
              {result.hint_tier ? (
                <div className="mt-5">
                  <div className="mb-2 text-xs font-medium text-zinc-500">
                    Hint <span className="font-mono">{result.hint_tier}</span> of{" "}
                    <span className="font-mono">{result.hint_ceiling}</span>
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
              <div className="mt-5 text-[15px] leading-relaxed text-zinc-800">{result.feedback}</div>
              {result.traceback && (
                <details className="group mt-5 border-t border-zinc-200 pt-4">
                  <summary className="cursor-pointer rounded-sm text-[13px] font-medium text-zinc-500 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900">
                    Your program's error output
                  </summary>
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-zinc-950 px-4 py-3 font-mono text-[13px] leading-relaxed break-words whitespace-pre-wrap text-zinc-100">
                    {result.traceback}
                  </pre>
                </details>
              )}
              {result.hidden_crash && (
                <p className="mt-4 text-sm leading-relaxed text-zinc-500">
                  Your program crashed on a hidden test{result.hidden_error ? ` (${result.hidden_error})` : ""}. Its error
                  output isn&apos;t shown, because it could reveal that test&apos;s data. Try inputs like the hidden tests
                  might use.
                </p>
              )}
            </Card>
          )}
        </div>
      </main>
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
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
        <BrandMark compact />
        {name && (
          <span className="max-w-[60%] truncate text-[13px] text-zinc-500">
            Joined as <strong className="font-semibold text-zinc-900">{name}</strong>
          </span>
        )}
      </div>
    </nav>
  );
}
