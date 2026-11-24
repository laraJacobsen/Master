import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type {
  GradingMode,
  LectureStatus,
  SharedExample,
  StudentAttempt,
  StudentRecap,
  SubmitResponse,
  TestCase,
  Verdict,
  VisibleTestFile,
  WorkspaceEntry,
} from "../shared/types";
import {
  fetchLectureStatus,
  fetchMyAttempts,
  fetchStudentRecap,
  fetchWorkspace,
  joinLecture as joinLectureApi,
  sendActivity,
  setStudentToken,
  submitCode as submitCodeApi,
} from "../shared/api";
import { defaultStarterCode, isUntouched } from "../shared/starterCode";
import { draftKey, loadDraft, pruneOldDrafts } from "./drafts";
import { Badge, BrandMark, Button, Callout, Card, Code, CodeSkeleton, Eyebrow, Input, Label, Skeleton, Spinner, StatusLine, TimeLine } from "../shared/ui";
import { CodeBlock, FailingTestStrip } from "../shared/code";
import { HERO_FILL, SCORE_LINE, TILE_TONE } from "../shared/verdictStyles";
import { cx } from "../shared/cx";
import type { Tone } from "../shared/ui";
import type { WorkspaceHandle } from "./Workspace";
import { TestResultsList } from "./TestResults";
import { ROUTES } from "../shared/routes";
import { Footer } from "../shared/Footer";
import { rememberRole } from "../shared/role";
// Monaco is most of this page's weight -- loaded only once a task is live,
// so the join and waiting screens stay instant.
const Workspace = lazy(() => import("./Workspace").then((m) => ({ default: m.Workspace })));

// A test-graded task's editable files as one text, for what reads "the code" as a
// string: the empty/untouched checks and the typing heartbeat. Never sent: Submit
// sends the files themselves.
function joinedFiles(files: Record<string, string>): string {
  return Object.keys(files)
    .sort()
    .map((path) => files[path])
    .join("\n");
}

function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} KB`;
  return `${(n / 1_000_000).toFixed(2)} MB`;
}

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
    <Badge tone={VERDICT_TONES[verdict] ?? "neutral"}>
      {VERDICT_LABELS[verdict] || verdict}
    </Badge>
  );
}

export interface ExampleIoProps {
  /** A string is shown in a monospace box; anything else (e.g. a file list) as is. */
  rows: Array<[label: string, value: ReactNode]>;
}

// The task's example, label above a monospace box -- same as the lecturer's
// "Show task" panel. Long values scroll inside their box.
function ExampleIo({ rows }: ExampleIoProps) {
  return (
    <div className="grid gap-3">
      {rows.map(([label, value]) => (
        <div key={label}>
          <div className="mb-1.5 text-xs text-zinc-500">{label}</div>
          {typeof value === "string" ? (
            <pre className="max-h-40 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[13px] text-zinc-900">
              {value}
            </pre>
          ) : (
            value
          )}
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

// Kahoot-style entry gate (POST /api/lecture/join): the right code gets the
// student a token, which every student call sends (setStudentToken) -- the
// server takes the student's name from it. Once entered, remembered for the
// rest of this browser tab so a page refresh mid-lecture doesn't force
// retyping it; a new tab (new lecture, most likely) asks again.
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

// This browser's join token, kept in localStorage (not the tab's
// sessionStorage) so a closed-and-reopened tab can rejoin the same lecture
// under the same name: the join sends it back, and the server only lets the
// browser holding a name's token use that name again.
const STUDENT_IDENTITY_KEY = "lecture_student_identity";

interface StoredIdentity {
  lectureId: number;
  token: string;
}

function loadIdentity(): StoredIdentity | null {
  try {
    const raw = localStorage.getItem(STUDENT_IDENTITY_KEY);
    const v = raw ? (JSON.parse(raw) as Partial<StoredIdentity>) : null;
    return v && typeof v.lectureId === "number" && typeof v.token === "string"
      ? { lectureId: v.lectureId, token: v.token }
      : null;
  } catch {
    return null;
  }
}

function saveIdentity(identity: StoredIdentity): void {
  try {
    localStorage.setItem(STUDENT_IDENTITY_KEY, JSON.stringify(identity));
  } catch {
    // Best effort -- worst case a reopened tab has to join under a new name.
  }
}

// The token for this tab's join, if both are still around -- set as the API
// layer's student token before anything renders (see App's useState below).
function tokenForThisSession(): string | null {
  const identity = loadIdentity();
  return identity && identity.lectureId === getJoinedLectureId() ? identity.token : null;
}

function hasJoinedThisSession(): boolean {
  try {
    return sessionStorage.getItem(JOIN_SESSION_KEY) === "1" && tokenForThisSession() !== null;
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
  const [joined, setJoined] = useState(() => {
    const restored = hasJoinedThisSession();
    if (restored) setStudentToken(tokenForThisSession());
    return restored;
  });
  const [phase, setPhase] = useState<Phase>(() => (hasJoinedThisSession() ? "loading" : "join"));
  // Pre-filled with the name from this tab's last join, if any (e.g. coming
  // back via "Back to home" after a lecture ended).
  const [joinNameInput, setJoinNameInput] = useState(getJoinedName);
  // A shared join link (/join?code=482913, copied from the lecturer's lobby) fills the code in.
  const [joinCodeInput, setJoinCodeInput] = useState(
    () => new URLSearchParams(window.location.search).get("code")?.replace(/\D/g, "") ?? "",
  );
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  // Shown on the join screen after being sent back to it because a new
  // lecture started (see applyStatus).
  const [joinNotice, setJoinNotice] = useState<string | null>(null);
  const [questionId, setQuestionId] = useState<string | null>(null);
  const [language, setLanguage] = useState("python");
  const [promptText, setPromptText] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskNumber, setTaskNumber] = useState<number | null>(null);
  const [example, setExample] = useState<TestCase | null>(null);
  const [durationSeconds, setDurationSeconds] = useState<number | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);

  // The name typed on the join screen (see JOIN_NAME_KEY) -- fixed for the
  // rest of the lecture, so submissions, the activity heartbeat and the
  // lecturer's per-student rows all stay under one name. Fixing a typo means
  // re-joining from a new tab.
  const [name, setName] = useState(getJoinedName);
  const [code, setCode] = useState("");
  // What the editor starts with for the current task: an autosaved draft from
  // an earlier visit (see drafts.ts), else the starter skeleton.
  const [initialCode, setInitialCode] = useState("");
  // Mirrors of `name`/`code` for the auto-submit-on-timeout path, which can
  // fire from inside a setInterval/poll callback where the `name`/`code`
  // state captured at effect-setup time would otherwise be stale.
  const nameRef = useRef(getJoinedName());
  const codeRef = useRef("");
  // The live task's language, for the same callbacks.
  const languageRef = useRef("python");
  // The live task's starter code -- code still equal to it isn't auto-submitted (see isUntouched).
  const starterRef = useRef("");
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
  // The hint card in the task panel -- scrolled into view when a new one arrives.
  const hintRef = useRef<HTMLDivElement>(null);
  // The task panel's file list opens files in the workspace through this.
  const workspaceRef = useRef<WorkspaceHandle>(null);
  const [openDataFiles, setOpenDataFiles] = useState<string[]>([]);
  const handleOpenDataFilesChange = useCallback((names: string[]) => setOpenDataFiles(names), []);
  // Data files the student may open (status.question.files): the example's
  // during the task, every test's once time is up.
  const [files, setFiles] = useState<VisibleTestFile[]>([]);
  // The task is graded on this file (e.g. "result.txt") instead of printed output.
  const [outputFile, setOutputFile] = useState<string | null>(null);
  // Test-graded tasks: the editor's files (fetched once per task), what the editable
  // ones start with, and what they are now -- the latter is what Submit sends.
  const [gradingMode, setGradingMode] = useState<GradingMode>("stdout");
  const [taskWorkspace, setTaskWorkspace] = useState<WorkspaceEntry[] | null>(null);
  const [initialFiles, setInitialFiles] = useState<Record<string, string>>({});
  const filesRef = useRef<Record<string, string> | null>(null);
  // What the lecturer is going over with the class right now -- see the
  // "On your lecturer's screen" card below.
  const [shownExamples, setShownExamples] = useState<SharedExample[]>([]);
  // Whether a task has gone live since this tab joined -- tells the waiting
  // screen's "lecture hasn't started yet" apart from "between tasks".
  const [hadTask, setHadTask] = useState(false);
  // The "submitted / time's up" popup over the locked editor. Opens when the
  // task ends for this student; closing it leaves the greyed-out editor.
  const [doneDialogOpen, setDoneDialogOpen] = useState(false);

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

  useEffect(() => {
    pruneOldDrafts();
  }, []);

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
  function handleFilesChange(files: Record<string, string>) {
    filesRef.current = files;
    handleEditorChange(joinedFiles(files));
  }

  // A test-graded task's files: the editable ones start as this browser's saved
  // draft where there is one, else the starter.
  async function loadTaskWorkspace(qId: string) {
    try {
      const ws = await fetchWorkspace(qId);
      if (questionIdRef.current !== qId) return;
      const starter = Object.fromEntries(ws.files.filter((f) => f.editable).map((f) => [f.path, f.content ?? ""]));
      const saved = loadDraft(draftKey(qId, nameRef.current))?.files ?? {};
      const start = { ...starter, ...Object.fromEntries(Object.entries(saved).filter(([path]) => path in starter)) };
      filesRef.current = start;
      starterRef.current = joinedFiles(starter);
      setInitialFiles(start);
      updateCode(joinedFiles(start));
      setTaskWorkspace(ws.files);
    } catch {
      if (questionIdRef.current === qId) setErrorMessage("Couldn't load this task's files. Reload the page to try again.");
    }
  }

  // After a reload the page knows nothing about this task's earlier submits:
  // put the latest one back as the result, and if it solved the task, lock it
  // again instead of sending the student back to the editor.
  async function restoreAttempts(qId: string) {
    let rows: StudentAttempt[];
    try {
      rows = await fetchMyAttempts(qId);
    } catch {
      return;
    }
    // Moved on to another task, or submitted again, while this was loading.
    if (questionIdRef.current !== qId || resultRef.current || submittingRef.current) return;
    const mine = [...rows].sort((a, b) => a.attempt_number - b.attempt_number);
    setHistory(mine.length === 0 ? null : mine);
    const latest = mine.at(-1);
    if (!latest) return;
    const restored: SubmitResponse = {
      submission_id: latest.id,
      attempt_number: latest.attempt_number,
      tests_passed: latest.tests_passed,
      tests_total: latest.tests_total,
      verdict: latest.verdict ?? "error",
      feedback: latest.feedback ?? "",
      test_results: latest.test_results,
      hidden_tests: latest.hidden_tests,
    };
    setResult(restored);
    resultRef.current = restored;
    if (latest.verdict === "correct" && phaseRef.current === "answering") {
      autoSubmittedRef.current = true; // nothing to auto-submit at time-up
      setPhase("waiting");
      setDoneDialogOpen(true);
    }
  }

  async function loadHistory(qId: string | null) {
    if (!qId) {
      setHistory(null);
      return;
    }
    try {
      const rows = await fetchMyAttempts(qId);
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
  async function performSubmit(qId: string, trimmedCode: string) {
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
        question_id: qId,
        source_code: trimmedCode,
        ...(filesRef.current ? { files: filesRef.current } : {}),
      });
      setResult(data);
      resultRef.current = data;
      window.requestAnimationFrame(() => hintRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
      loadHistory(qId);
      // Solved it -- nothing left to do on this task, so off to the waiting
      // screen. A wrong answer stays on the editor with its hint so the
      // student can resubmit (that's what escalates the hint tier).
      if (data.verdict === "correct") {
        setPhase("waiting");
        setDoneDialogOpen(true);
      }
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
    setDoneDialogOpen(true);

    // Already submitted (grading in flight, or already graded) -- the
    // existing submit/result takes it from here, nothing more to do.
    if (submittingRef.current || resultRef.current) return;

    const trimmedName = nameRef.current.trim();
    const trimmedCode = codeRef.current.trim();
    // An untouched starter skeleton is nothing the student wrote, same as an empty box.
    if (!trimmedName || isUntouched(trimmedCode, starterRef.current)) return; // render shows the neutral note

    setWasAutoSubmitted(true);
    performSubmit(qId, trimmedCode);
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
        fetchStudentRecap()
          .then(setRecap)
          .catch(() => {
            // No recap to show -- the headline/closing message still stand on their own.
          });
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
      setGradingMode(q.grading_mode ?? "stdout");
      setTaskWorkspace(null);
      filesRef.current = null;
      setPromptText(q.prompt);
      setTaskTitle(q.title);
      setTaskNumber(q.number ?? null);
      setLanguage(q.language);
      languageRef.current = q.language;
      editedRef.current = false;
      setNudge(null);
      setExample(q.example);
      setDurationSeconds(q.duration_seconds);
      const restored = loadDraft(draftKey(q.id, nameRef.current))?.code;
      // The lecturer's own starter if they wrote one, else the built-in default.
      const starter =
        q.starter_code ??
        defaultStarterCode(q.language, {
          stdin: q.example?.stdin ?? "",
          files: (q.files ?? []).filter((f) => f.test === 0).map((f) => f.name),
        });
      starterRef.current = starter;
      const startWith = restored ?? starter;
      setInitialCode(startWith);
      updateCode(startWith);
      setResult(null);
      resultRef.current = null;
      setErrorMessage(null);
      setHistory(null);
      if (q.grading_mode === "tests") void loadTaskWorkspace(q.id);
      restoreAttempts(q.id);
      setPhase(q.seconds_remaining > 0 ? "answering" : "waiting");
      // A late joiner lands on a task that's already over: say so up front.
      setDoneDialogOpen(q.seconds_remaining <= 0);
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
      const edited = editedRef.current;
      editedRef.current = false;
      sendActivity(questionId, edited)
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
      const joinedLecture = await joinLectureApi(code, trimmedName, loadIdentity()?.token ?? null);
      saveIdentity({ lectureId: joinedLecture.lecture_id, token: joinedLecture.token });
      rememberRole("student");
      setStudentToken(joinedLecture.token);
      // The lecture's spelling of the name (a rejoin keeps the original one).
      markJoinedThisSession(joinedLecture.student_name, joinedLecture.lecture_id);
      setJoinNotice(null);
      updateName(joinedLecture.student_name); // the name for the rest of this lecture (shown, not editable, while answering)
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

    await performSubmit(questionId, trimmedCode);
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
                  placeholder="e.g. Kari Nordmann"
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
        <Footer />
      </>
    );
  }

  if (phase === "loading") {
    return (
      <>
        <StudentBar name={joinedName} />
        <StudentPage className="pt-14">
          <div role="status" aria-label="Loading" className="grid gap-8 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-4 h-8 w-3/4" />
              <Skeleton className="mt-6 h-4 w-full" />
              <Skeleton className="mt-2 h-4 w-5/6" />
              <Skeleton className="mt-2 h-4 w-2/3" />
            </div>
            <Skeleton className="h-[28rem] rounded-xl lg:col-span-8" />
          </div>
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
            <Button variant="secondary" className="mt-8" onClick={() => (window.location.href = ROUTES.join)}>
              Join another lecture
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
        <Footer />
      </>
    );
  }

  // Every "nothing to type right now" moment shares one headline and message;
  // only the wording changes with what this student just did. Shown in the
  // popup over a finished task, or on the page between tasks.
  let title: string;
  let message: string;
  if (submitting) {
    title = "Your code was submitted";
    message = wasAutoSubmitted
      ? "Time ran out, so it went in automatically. Running the tests now."
      : "Running the tests now.";
  } else if (errorMessage) {
    title = "Time's up";
    message = "Waiting for your lecturer to give the next task.";
  } else if (result?.verdict === "correct") {
    title = "Your code was submitted";
    message = "It passes every test. Your lecturer will move on when the class is ready.";
  } else if (result) {
    title = "Your code was submitted";
    message = "Your lecturer will go through the results with the class before the next task.";
  } else if (hadTask) {
    title = "Time's up";
    message = "You didn't submit anything this time. There'll be another task soon.";
  } else {
    title = `You're in${name.trim() ? `, ${name.trim()}` : ""}`;
    message = "Your lecturer hasn't started the first task yet.";
  }
  const scored = result != null && !submitting;
  // A task is current but over for this student (solved, or time's up): the
  // editor stays up, locked, under the popup.
  const locked = phase === "waiting" && questionId != null;

  // What the lecturer is going over with the class (see "Show to students").
  const exampleList = (
  <div className={cx("grid gap-8", shownExamples.length > 1 && !locked && "2xl:grid-cols-2")}>
    {shownExamples.map((ex, i) => (
      <div key={i} className="min-w-0">
        {shownExamples.length > 1 && <Eyebrow className="mb-2">Example {i + 1}</Eyebrow>}
        {ex.correct && (
          <p className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-emerald-700">
            <svg className="size-3" viewBox="0 0 12 12" fill="none" aria-hidden="true">
              <path d="M2.5 6.2l2.3 2.3L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Passes every test
          </p>
        )}
        {ex.failing_test && (
          <FailingTestStrip
            className="mb-2"
            test={{
              stdin: ex.failing_test.stdin,
              expected: ex.failing_test.expected_stdout,
              got: ex.failing_test.stdout,
              error: ex.failing_test.stderr,
              testName: ex.failing_test.test_name,
              message: ex.failing_test.message,
            }}
          />
        )}
        {ex.hidden_tests && ex.hidden_tests.failed > 0 && (
          <p className="mb-2 text-xs text-amber-800">
            {ex.hidden_tests.failed} of {ex.hidden_tests.total} hidden tests failed.
          </p>
        )}
        <CodeBlock lines={ex.source_code.split("\n").length}>{ex.source_code}</CodeBlock>
      </div>
    ))}
  </div>
  );

  if (phase === "waiting" && !locked) {
    return (
      <>
        <StudentBar name={joinedName} />
        <StudentPage>
          <Card
            flush
            className="mt-10 grid max-w-3xl animate-fade-in-up overflow-hidden sm:mt-14 sm:grid-cols-[minmax(0,1fr)_auto]"
            role="status"
            aria-live="polite"
          >
            <div className="min-w-0 px-6 py-7 sm:px-8 sm:py-8">
              {submitting ? (
                <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-600">
                  <Spinner /> {statusText || "Grading..."}
                </div>
              ) : (
                <StatusLine state="live" label="Waiting for your lecturer" items={[hadTask && taskTitle]} />
              )}
              <h1 className="mt-4 text-3xl font-bold tracking-tight text-balance text-zinc-950 sm:text-4xl">{title}</h1>
              <p className="mt-2 max-w-md text-[15px] leading-relaxed text-zinc-500">{message}</p>
              {errorMessage && !submitting && (
                <Callout tone="danger" role="alert" className="mt-5">
                  {errorMessage}
                </Callout>
              )}
            </div>
            {scored && (
              <div className="flex flex-col justify-end border-t border-zinc-200 bg-zinc-50 px-6 py-6 sm:min-w-44 sm:border-t-0 sm:border-l sm:px-8 sm:py-8">
                <VerdictBadge verdict={result.verdict} />
                <div className="mt-3 font-mono text-5xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
                  {result.tests_passed}
                  <span className="text-2xl text-zinc-400">/{result.tests_total}</span>
                </div>
                <div className="mt-1.5 text-xs text-zinc-500">tests passed</div>
              </div>
            )}
          </Card>
          {shownExamples.length > 0 && (
            <section className="animate-fade-in-up pt-12" aria-label="On your lecturer's screen">
              <div className="mb-5 flex flex-wrap items-baseline gap-3">
                <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Let's look at this together</h2>
                <span className="text-[13px] text-zinc-400">
                  {shownExamples.length > 1
                    ? "attempts your lecturer picked from the class"
                    : "an attempt your lecturer picked from the class"}
                </span>
              </div>
              {exampleList}
            </section>
          )}
        </StudentPage>
      </>
    );
  }

  const timeFraction = durationSeconds && secondsRemaining != null ? secondsRemaining / durationSeconds : 0;
  const exampleFiles = files.filter((f) => f.test === 0);
  // The example gives nothing on standard input: its input is its files.
  const inputFromFiles = exampleFiles.length > 0 && !(example?.stdin ?? "").trim();
  // The example's files as rows that open them in the workspace.
  const taskFileList = (
    <ul className="grid gap-1" aria-label="Task files">
      {exampleFiles.map((f) => {
        const isOpen = openDataFiles.includes(f.name);
        return (
          <li key={f.name}>
            <button
              type="button"
              onClick={() => workspaceRef.current?.openDataFile(f.name)}
              className={cx(
                "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] ring-1 transition-colors",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
                isOpen
                  ? "bg-brand-50 text-brand-700 ring-brand-200"
                  : "bg-zinc-50 text-zinc-800 ring-zinc-200 hover:bg-white hover:ring-zinc-300",
              )}
            >
              <svg className="size-3.5 flex-none text-zinc-400" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M3 1.5h5l3 3v8H3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                <path d="M8 1.5v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
              </svg>
              <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">{f.name}</span>
              <span className="font-mono text-[11px] text-zinc-400">{formatBytes(f.size)}</span>
              <span className="text-xs text-zinc-500">{isOpen ? "Open" : "View"}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
  const lowTime = secondsRemaining != null && timeFraction <= 0.15;

  return (
    <>
      {/* A light brand tint behind the panels once the task is over for this
          student, so the locked state reads at a glance after the popup closes. */}
      <div
        aria-hidden="true"
        className={cx(
          "pointer-events-none fixed inset-0 -z-10 bg-brand-100/70 transition-opacity duration-500",
          locked ? "opacity-100" : "opacity-0",
        )}
      />
      <StudentBar name={joinedName || name} />
      <TimeLine fraction={timeFraction} />
      <main className="mx-auto grid w-full max-w-[112rem] gap-5 px-4 pt-5 pb-5 sm:px-6 lg:h-[calc(100dvh-3.5rem-2px)] lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        {/* Left: the task, and where hints appear. */}
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl bg-white shadow-card" aria-label="Task">
          <div className="flex-none border-b border-zinc-200 px-5 pt-5 pb-4">
            <div className="flex items-center justify-between gap-3">
              <StatusLine
                state={locked || secondsRemaining === 0 ? "closed" : "live"}
                label={taskNumber ? `Task ${taskNumber}` : "Task"}
                items={[<span className="capitalize">{language}</span>]}
              />
              {secondsRemaining != null && !locked && (
                <span
                  role="timer"
                  aria-label="Time left"
                  className={cx(
                    "font-mono text-xl font-semibold tracking-tight tabular-nums",
                    lowTime ? "text-red-600" : "text-zinc-950",
                  )}
                >
                  {formatMMSS(secondsRemaining)}
                </span>
              )}
            </div>
            <h1 className="mt-2 text-2xl leading-tight font-bold tracking-tight text-balance text-zinc-950">
              {taskTitle || "Task"}
            </h1>
          </div>

          {locked && (
            <div className="flex-none border-b border-brand-200 bg-brand-50 px-5 py-4" role="status">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-[13px] font-semibold text-brand-700">
                  {submitting ? (
                    <Spinner />
                  ) : (
                    <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-brand-500" aria-hidden="true" />
                  )}
                  {submitting ? "Grading your code" : "Waiting for the next task"}
                </span>
                <Button variant="ghost" size="sm" className="-mr-2 text-brand-700" onClick={() => setDoneDialogOpen(true)}>
                  {scored ? "Your result" : "Details"}
                </Button>
              </div>
              <p className="mt-1 text-[13px] leading-relaxed text-brand-950/70">
                This task is closed. Your lecturer will start the next one.
              </p>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            <div className="grid gap-7">
              {locked && shownExamples.length > 0 && (
                <section className="animate-fade-in-up" aria-label="On your lecturer's screen">
                  <Eyebrow className="mb-1">On your lecturer&apos;s screen</Eyebrow>
                  <p className="mb-4 text-[13px] text-zinc-500">
                    {shownExamples.length > 1 ? "Attempts" : "An attempt"} picked from the class to look at together.
                  </p>
                  {exampleList}
                </section>
              )}

              {nudge && (
                <div className="animate-fade-in-up rounded-lg bg-brand-50 px-4 py-3.5 ring-1 ring-brand-200" role="status">
                  <Eyebrow className="text-brand-700">A nudge</Eyebrow>
                  <p className="mt-1.5 text-sm leading-relaxed text-brand-950">{nudge}</p>
                  <Button variant="ghost" size="sm" className="mt-2 -ml-2 text-brand-700" onClick={() => setNudge(null)}>
                    Got it
                  </Button>
                </div>
              )}

              {result && (
                <div ref={hintRef} className="animate-fade-in-up scroll-mt-4" role="status" aria-label="Your result">
                  <div
                    className={cx(
                      "rounded-lg px-4 py-4 ring-1",
                      result.verdict === "correct" ? "bg-emerald-50 ring-emerald-200" : "bg-violet-50/70 ring-violet-200",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <VerdictBadge verdict={result.verdict} />
                      <span className="font-mono text-sm text-zinc-700 tabular-nums">
                        {result.tests_passed}/{result.tests_total} tests
                      </span>
                      {result.hint_tier ? (
                        <span className="ml-auto text-xs text-zinc-500">
                          Hint <span className="font-mono text-zinc-900">{result.hint_tier}</span> of{" "}
                          <span className="font-mono text-zinc-900">{result.hint_ceiling}</span>
                        </span>
                      ) : null}
                    </div>
                    {result.hint_tier ? (
                      <div className="mt-2 flex gap-1" aria-hidden="true">
                        {Array.from({ length: result.hint_ceiling ?? 0 }, (_, i) => i + 1).map((i) => (
                          <div
                            key={i}
                            className={cx("h-1 flex-1 rounded-sm", i <= (result.hint_tier ?? 0) ? "bg-brand-500" : "bg-white")}
                          />
                        ))}
                      </div>
                    ) : null}
                    <p className="mt-3 text-sm leading-relaxed text-zinc-900">{result.feedback}</p>
                    {result.test_results && (
                      <TestResultsList
                        className="mt-3 border-t border-black/5 pt-3"
                        results={result.test_results}
                        hidden={result.hidden_tests}
                      />
                    )}
                  </div>
                </div>
              )}

              <section>
                <Eyebrow>Description</Eyebrow>
                <p className="mt-2 text-[15px] leading-relaxed whitespace-pre-wrap text-zinc-800">{promptText}</p>
                {outputFile && (
                  <div className="mt-4 border-l-2 border-brand-400 py-1 pl-3.5 text-[13px] leading-relaxed text-zinc-600">
                    Write your answer to <Code>{outputFile}</Code>. That file is checked, not what your program prints.
                  </div>
                )}
              </section>

              {example && (
                <section>
                  <Eyebrow className="mb-3">Example</Eyebrow>
                  <ExampleIo
                    rows={[
                      // File tasks: the example's input is its files, not standard input.
                      inputFromFiles
                        ? [exampleFiles.length === 1 ? "Input file" : "Input files", taskFileList]
                        : ["Input", example.stdin.trimEnd() || "(none)"],
                      [outputFile ? `Expected ${outputFile}` : "Expected output", example.expected_stdout.trimEnd()],
                    ]}
                  />
                  {inputFromFiles && (
                    <p className="mt-2.5 text-[13px] leading-relaxed text-zinc-500">
                      The graded tests use their own versions of {exampleFiles.length === 1 ? "this file" : "these files"},
                      shown when time is up.
                    </p>
                  )}
                </section>
              )}

              {gradingMode === "tests" && taskWorkspace && (
                <section aria-label="Task files">
                  <Eyebrow className="mb-2">Files</Eyebrow>
                  <ul className="grid gap-1">
                    {taskWorkspace.map((f) => (
                      <li key={f.path}>
                        <button
                          type="button"
                          onClick={() => workspaceRef.current?.openDataFile(f.path)}
                          className={cx(
                            "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] ring-1 transition-colors",
                            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
                            "bg-zinc-50 text-zinc-800 ring-zinc-200 hover:bg-white hover:ring-zinc-300",
                          )}
                        >
                          <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">{f.path}</span>
                          <span className="font-mono text-[11px] text-zinc-400">{formatBytes(f.size)}</span>
                          <span className={cx("text-xs", f.editable ? "font-medium text-brand-700" : "text-zinc-500")}>
                            {f.editable ? "Yours to edit" : f.kind === "test" ? "Test" : f.kind === "data" ? "Data" : "Read-only"}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2.5 text-[13px] leading-relaxed text-zinc-500">
                    Run checks your code against the tests in <Code>tests/</Code>. Submit also runs hidden tests; you&apos;ll
                    see how many of those pass, not what they check.
                  </p>
                </section>
              )}

              {/* A task with both typed input and files: the files get their own section. */}
              {exampleFiles.length > 0 && !inputFromFiles && (
                <section aria-label="Task files">
                  <Eyebrow className="mb-2">Files</Eyebrow>
                  {taskFileList}
                  <p className="mt-2.5 text-[13px] leading-relaxed text-zinc-500">
                    Your program can open {exampleFiles.length === 1 ? "this file" : "these files"} by name, e.g.{" "}
                    <Code>open(&quot;{exampleFiles[0].name}&quot;)</Code>. The graded tests use their own versions, shown
                    when time is up.
                  </p>
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
                          className={cx("flex h-12 flex-col justify-between rounded-md border px-2 pt-1.5 pb-2", TILE_TONE[v])}
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
            </div>
          </div>
        </aside>

        {/* Right: files, editors and terminal. */}
        <section className="h-[80dvh] min-h-[32rem] min-w-0 lg:h-auto" aria-label="Your code">
          <Suspense
            fallback={
              <div className="h-full rounded-xl bg-white shadow-card">
                <CodeSkeleton lines={8} className="p-6" />
              </div>
            }
          >
            {questionId && (gradingMode !== "tests" || taskWorkspace) && (
              <Workspace
                ref={workspaceRef}
                onOpenDataFilesChange={handleOpenDataFilesChange}
                key={questionId}
                questionId={questionId}
                language={language}
                initialCode={initialCode}
                draftKey={draftKey(questionId, name)}
                exampleStdin={example?.stdin ?? ""}
                exampleExpected={example?.expected_stdout ?? null}
                outputFile={outputFile}
                dataFiles={exampleFiles}
                onCodeChange={handleEditorChange}
                onSubmit={handleSubmit}
                submitting={submitting}
                statusText={statusText}
                result={result}
                submitError={errorMessage}
                locked={locked}
                taskFiles={gradingMode === "tests" ? taskWorkspace : null}
                initialFiles={initialFiles}
                onFilesChange={handleFilesChange}
              />
            )}
          </Suspense>
        </section>
      </main>
      <DoneDialog
        open={locked && doneDialogOpen}
        onClose={() => setDoneDialogOpen(false)}
        title={title}
        message={message}
        statusText={submitting ? statusText || "Grading..." : null}
        result={scored ? result : null}
      />
    </>
  );
}

export interface DoneDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  message: string;
  /** Set while the submission is still being graded. */
  statusText: string | null;
  result: SubmitResponse | null;
}

// Pops up over the editor when the task ends for this student (solved, or
// time's up). Escape, the backdrop or the button closes it onto the locked
// editor; the task panel's "Your result" button brings it back.
function DoneDialog({ open, onClose, title, message, statusText, result }: DoneDialogProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[100] flex animate-fade-in items-center justify-center bg-zinc-950/40 p-4 backdrop-blur-[2px]"
      onPointerDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="done-dialog-title"
        aria-describedby="done-dialog-message"
        className="grid w-full max-w-xl animate-fade-in-up overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xl shadow-zinc-950/10 sm:grid-cols-[minmax(0,1fr)_auto]"
      >
        <div className="min-w-0 px-6 pt-6 pb-5 sm:px-7 sm:pt-7">
          {statusText ? (
            <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-600" role="status">
              <Spinner /> {statusText}
            </div>
          ) : (
            <StatusLine state="live" label="Waiting for your lecturer" />
          )}
          <h2 id="done-dialog-title" className="mt-3 text-2xl font-bold tracking-tight text-balance text-zinc-950">
            {title}
          </h2>
          <p id="done-dialog-message" className="mt-2 text-sm leading-relaxed text-zinc-500">
            {message}
          </p>
          <Button ref={closeRef} variant="secondary" className="mt-6" onClick={onClose}>
            Back to my code
          </Button>
        </div>
        {result && (
          <div className="flex flex-col justify-end border-t border-zinc-200 bg-zinc-50 px-6 py-5 sm:min-w-40 sm:border-t-0 sm:border-l sm:px-7 sm:py-7">
            <VerdictBadge verdict={result.verdict} />
            <div className="mt-3 font-mono text-5xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
              {result.tests_passed}
              <span className="text-2xl text-zinc-400">/{result.tests_total}</span>
            </div>
            <div className="mt-1.5 text-xs text-zinc-500">tests passed</div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatMMSS(totalSeconds: number): string {
  const sec = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(sec / 60)}:${(sec % 60).toString().padStart(2, "0")}`;
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
