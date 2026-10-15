import { Fragment, useEffect, useState } from "react";
import type {
  ClusterRow,
  LectureRow,
  LectureSummary,
  ProgressResponse,
  QuestionRow,
  StudentActivity,
  SubmissionRow,
  ValidationTestResult,
} from "../shared/types";
import {
  fetchActiveLecture,
  fetchActivity,
  fetchClusters,
  fetchJoinedCount,
  fetchLectureSummary,
  fetchProgress,
  fetchQuestionDetail,
  fetchSubmissionDetail,
  fetchSubmissions,
  endQuestionNow,
  finishLecture,
  nextTask,
  raiseIssue,
} from "../shared/api";
import { ClassProgress } from "./ClassProgress";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { HeaderNavLink } from "../shared/HeaderNavLink";
import { NavBar } from "../shared/NavBar";

const POLL_MS = 3000;

// How long after a task's timer hits zero to keep showing the "live" pulse
// on the submissions/discussion cards -- gives the auto-submit backstop and
// any still-resolving gradings time to land before the dashboard settles.
// Background polling itself never stops (see the always-on intervals below);
// this only controls the "still updating" visual affordance.
const SETTLE_GRACE_MS = 8000;

function formatMMSS(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

// Which question this dashboard is watching -- set via ?question_id= (the
// link the setup page's "Start"/"Live dashboard" actions send a lecturer
// to). With no param, falls back to the old behavior of showing everything.
const QUESTION_ID = new URLSearchParams(window.location.search).get("question_id");

// ?lecture_id= puts this page straight into the generalized end-of-lecture
// summary view for that specific past lecture (the home dashboard's history
// list links here) -- skips the live task-control UI/polling entirely, since
// a historical lecture has nothing new to arrive. Mutually exclusive with
// QUESTION_ID in practice (the two flows never link to each other with both
// params set).
const LECTURE_ID = new URLSearchParams(window.location.search).get("lecture_id");

// ?lobby= puts this page into the lobby stage for that lecture: the code +
// a live "N joined" counter + a "Start lecture" button, before anything is
// timed (see the lobby-scoping-decision). One more state in the same
// lecturer-dashboard state machine as QUESTION_ID/LECTURE_ID above, not a
// separate page -- the audience and the underlying page never change,
// only which controls/data are showing.
const LOBBY_ID = new URLSearchParams(window.location.search).get("lobby");

function verdictClass(v: string) {
  return "verdict-pill verdict-" + v;
}
function verdictLabel(v: string) {
  const labels: Record<string, string> = {
    correct: "Correct",
    partially_correct: "Partial",
    incorrect: "Incorrect",
    error: "Error",
  };
  return labels[v] || v;
}
function issueTag(c: ClusterRow) {
  if (c.exec_verdict === "rejected") return "Rejected";
  if (c.exec_verdict === "pass") return "Passing";
  const verdict = (c.exec_verdict || "unknown").replace(/_/g, " ");
  const label = verdict.charAt(0).toUpperCase() + verdict.slice(1);
  return c.error_type && c.error_type !== "none" ? `${label} · ${c.error_type}` : label;
}

// Stable across polls even as students join a cluster (its submission_ids
// and example_submission_id both change then), so an open issue doesn't
// snap shut on the next refresh. Sub-clusters of one verdict are told apart
// by their discussion point, or by their earliest submission when there's
// no point yet (a single-student sub-cluster).
function issueKey(c: ClusterRow) {
  const ids = c.submission_ids && c.submission_ids.length ? c.submission_ids : [c.example_submission_id];
  return `${c.exec_verdict}|${c.error_type ?? ""}|${c.discussion_point ?? Math.min(...ids)}`;
}

function issueText(c: ClusterRow) {
  if (c.exec_verdict === "pass") return "Passed every test.";
  if (c.discussion_point) return c.discussion_point;
  return c.count < 2
    ? "Only one student so far. Show it to the students if it's worth going over anyway."
    : "No discussion point for this issue.";
}

// Students in one cluster often submit character-for-character identical
// code -- shown once, with everyone who wrote it, instead of N copies.
function groupByCode(subs: SubmissionRow[]): SubmissionRow[][] {
  const groups = new Map<string, SubmissionRow[]>();
  for (const sub of subs) {
    const key = sub.source_code.trim();
    groups.set(key, [...(groups.get(key) ?? []), sub]);
  }
  return [...groups.values()];
}

function ExampleBlock({ subs }: { subs: SubmissionRow[] }) {
  const sub = subs[0];
  const names = subs.map((s) => s.student_name).join(", ");
  const meta = `${subs.length > 1 ? `${subs.length} students: ` : ""}${names} · ${sub.tests_passed}/${sub.tests_total} tests passed`;

  const results: ValidationTestResult[] = JSON.parse(sub.raw_test_results || "[]");
  const failing = results.find((r) => !r.passed);

  return (
    <div className="example">
      <div className="example-meta">{meta}</div>
      {failing && (
        <div className="example-diff">
          <div>
            <strong>Input:</strong> <code>{failing.stdin ?? ""}</code>
          </div>
          <div>
            <strong>Expected output:</strong> <code>{failing.expected_stdout ?? ""}</code>
          </div>
          <div>
            <strong>Actual output:</strong> <code>{(failing.stdout || "").trim() || "(none)"}</code>
          </div>
          {failing.stderr && (
            <div>
              <strong>Error output:</strong> <code>{failing.stderr}</code>
            </div>
          )}
        </div>
      )}
      <code className="example-code">{sub.source_code}</code>
    </div>
  );
}

export default function App() {
  const [pageTitle, setPageTitle] = useState("Lecturer Dashboard");

  // Rows from the last successful poll, kept around so toggling a student's
  // code open/closed can re-render instantly without waiting on (or
  // triggering) a fresh fetch, and submissions already carry source_code so
  // no per-row fetch is needed either.
  const [subRows, setSubRows] = useState<SubmissionRow[]>([]);
  // Submission ids currently expanded in the table -- survives across polls
  // (which otherwise fully rebuild the list every 3s) so an open dropdown
  // doesn't snap shut on the next refresh.
  const [expandedSubIds, setExpandedSubIds] = useState<Set<number>>(new Set());

  const [clusters, setClusters] = useState<ClusterRow[]>([]);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  // Who's typing / idle / away -- see ClassProgress and api_lecturer_question_activity.
  const [activity, setActivity] = useState<StudentActivity[]>([]);
  // Issues whose code is expanded inline (by issueKey), plus any submissions
  // an open issue needed that weren't in the polled list -- see toggleIssue.
  const [openIssues, setOpenIssues] = useState<Set<string>>(new Set());
  const [fetchedSubs, setFetchedSubs] = useState<Record<number, SubmissionRow>>({});
  const [issueLoadError, setIssueLoadError] = useState(false);
  const [raisingKey, setRaisingKey] = useState<string | null>(null);
  const [raiseError, setRaiseError] = useState<string | null>(null);

  // The active lecture's Kahoot-style join code, shown in the Task control
  // card for the whole session -- fetched once (it doesn't change once the
  // lecture starts, so unlike the polled state below there's no need to
  // re-fetch it).
  const [joinCode, setJoinCode] = useState<string | null>(null);

  // Powers the "Time remaining" banner and gates the Next task/Finish
  // lecture controls -- see api_lecture_next/finish in backend/main.py.
  const [question, setQuestion] = useState<QuestionRow | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
  // False while the task is active, and for SETTLE_GRACE_MS after its timer
  // hits zero -- drives the "live" pulse on the submissions/discussion
  // cards below. Data itself keeps polling regardless (see the always-on
  // intervals below); this only controls that visual affordance.
  const [settled, setSettled] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [advanceMessage, setAdvanceMessage] = useState<string | null>(null);
  const [lectureFinished, setLectureFinished] = useState(false);
  // Ending the whole lecture can't be undone and kicks every student to the
  // end screen, so it sits behind a confirm (and out of the main button row).
  const [confirmFinishOpen, setConfirmFinishOpen] = useState(false);

  // The STATE 2 post-lecture view -- fetched once, right when "End session"
  // succeeds (see handleFinishLecture below), not polled: the lecture is
  // over, so unlike the live dashboard there's nothing new to arrive.
  const [summary, setSummary] = useState<LectureSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  // Every task's submissions, for the per-task Class progress charts in the
  // summary -- keyed by question_id; a task missing here failed to load.
  const [taskSubs, setTaskSubs] = useState<Record<string, SubmissionRow[]>>({});
  const [taskSubsLoaded, setTaskSubsLoaded] = useState(false);

  // Lobby mode (?lobby=) -- the lecture row itself (for its code/label,
  // fetched once) and the live joined-count (polled, same cadence as the
  // rest of this dashboard's polling).
  const [lobbyLecture, setLobbyLecture] = useState<LectureRow | null>(null);
  const [joinedCount, setJoinedCount] = useState<number | null>(null);
  const [lobbyError, setLobbyError] = useState<string | null>(null);
  const [startingLecture, setStartingLecture] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Historical mode (?lecture_id=): fetch that lecture's summary once and
  // stop -- no polling, since a past lecture has nothing new to arrive.
  useEffect(() => {
    if (!LECTURE_ID) return;
    setSummaryLoading(true);
    setSummaryError(null);
    fetchLectureSummary(Number(LECTURE_ID))
      .then((s) => {
        setSummary(s);
        setPageTitle(`${s.lecture_label} summary`);
        return Promise.all(
          s.tasks.map((t) =>
            fetchSubmissions(t.question_id)
              .then((rows) => [t.question_id, rows] as const)
              .catch(() => null),
          ),
        ).then((results) => {
          setTaskSubs(Object.fromEntries(results.filter((r) => r !== null)));
          setTaskSubsLoaded(true);
        });
      })
      .catch((e) => {
        setSummaryError(e instanceof Error ? e.message : "Could not load this lecture's summary.");
      })
      .finally(() => setSummaryLoading(false));
  }, []);

  // Lobby mode (?lobby=): fetch the lecture row once (its code/label don't
  // change), then poll the joined-count -- the one thing in this view that
  // actually updates while the lecturer's watching students trickle in.
  // Checks live_question_id first: navigating back here (e.g. from "Manage
  // questions") after the lecture has already been started must land on the
  // live task dashboard, not the pre-start lobby again -- otherwise "Start
  // lecture" would fire a second time and start a second question
  // concurrently with the one already live.
  useEffect(() => {
    if (!LOBBY_ID) return;
    const id = Number(LOBBY_ID);
    fetchActiveLecture()
      .then((a) => {
        if (a.live_question_id) {
          window.location.href = `lecturer.html?question_id=${encodeURIComponent(a.live_question_id)}`;
          return;
        }
        if (!a.lecture || a.lecture.id !== id) {
          setLobbyError("This lecture is no longer active.");
          return;
        }
        setLobbyLecture(a.lecture);
        setPageTitle(`${a.lecture.display_label} lobby`);
      })
      .catch((e) => setLobbyError(e instanceof Error ? e.message : "Could not load this lecture."));

    const pollJoined = () => {
      fetchJoinedCount(id)
        .then((r) => setJoinedCount(r.joined))
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };
    pollJoined();
    const t = window.setInterval(pollJoined, POLL_MS);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (LECTURE_ID || LOBBY_ID) return; // historical/lobby mode -- no live task polling, see effects above.

    if (QUESTION_ID) {
      fetchQuestionDetail(QUESTION_ID)
        .then((q) => {
          setPageTitle(q.title);
          setQuestion(q);
        })
        .catch(() => {
          // Leave the generic title in place.
        });
      fetchActiveLecture()
        .then((a) => setJoinCode(a.lecture?.join_code ?? null))
        .catch(() => {
          // Not critical -- the task-control card just omits the code.
        });
    }

    const poll = () => {
      fetchSubmissions(QUESTION_ID)
        .then((rows) => setSubRows(rows))
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };
    const pollClusters = () => {
      fetchClusters(QUESTION_ID)
        .then((rows) => setClusters(rows))
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };
    // Only meaningful for a single-question dashboard -- with no
    // ?question_id= (the old "show everything" view) there's no one
    // question's expected_students to compare against.
    const pollProgress = () => {
      if (!QUESTION_ID) return;
      fetchProgress(QUESTION_ID)
        .then((p) => setProgress(p))
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };
    const pollActivity = () => {
      if (!QUESTION_ID) return;
      fetchActivity(QUESTION_ID)
        .then((rows) => setActivity(rows))
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };
    // Re-fetched (not just loaded once) so the "Time remaining" banner and
    // status pill stay accurate if the question gets closed out from under
    // this tab (e.g. a second lecturer tab, or a manual API call).
    const pollQuestion = () => {
      if (!QUESTION_ID) return;
      fetchQuestionDetail(QUESTION_ID)
        .then((q) => setQuestion(q))
        .catch(() => {
          // Backend not reachable yet -- stay quiet and retry on the next poll.
        });
    };

    poll();
    pollClusters();
    pollProgress();
    pollQuestion();
    pollActivity();
    const t1 = window.setInterval(poll, POLL_MS);
    const t2 = window.setInterval(pollClusters, POLL_MS);
    const t3 = window.setInterval(pollProgress, POLL_MS);
    const t4 = window.setInterval(pollQuestion, POLL_MS);
    const t5 = window.setInterval(pollActivity, POLL_MS);
    return () => {
      window.clearInterval(t1);
      window.clearInterval(t2);
      window.clearInterval(t3);
      window.clearInterval(t4);
      window.clearInterval(t5);
    };
  }, []);

  // Ticks the "Time remaining" banner once a second, anchored to the
  // question's server-side started_at/duration_seconds (re-synced whenever
  // pollQuestion above refreshes `question`) rather than counting down from
  // page-load, so it can't drift from what the student page shows.
  useEffect(() => {
    if (!question || question.status !== "live" || !question.started_at) {
      setSecondsRemaining(null);
      setSettled(false);
      return;
    }
    const startedMs = new Date(question.started_at.replace(" ", "T") + "Z").getTime();
    const endMs = startedMs + question.duration_seconds * 1000;
    const settleAtMs = endMs + SETTLE_GRACE_MS;
    const tick = () => {
      const now = Date.now();
      setSecondsRemaining(Math.max(0, Math.round((endMs - now) / 1000)));
      setSettled(now >= settleAtMs);
    };
    tick();
    const t = window.setInterval(tick, 1000);
    return () => window.clearInterval(t);
  }, [question]);

  async function handleNextTask() {
    setAdvancing(true);
    setAdvanceMessage(null);
    try {
      const res = await nextTask(QUESTION_ID);
      if (res.started) {
        window.location.href = `lecturer.html?question_id=${encodeURIComponent(res.started.id)}`;
      } else {
        setAdvanceMessage("No more tasks left to start. Use \"End lecture...\" below to finish.");
        setAdvancing(false);
      }
    } catch (e) {
      setAdvanceMessage(e instanceof Error ? e.message : "Could not advance to the next task.");
      setAdvancing(false);
    }
  }

  // "End task now" -- runs this task's timer out early (everyone's answered,
  // short on time, ...). Lands on the same "time's up" state as a timer that
  // ran out by itself: students go to their waiting screen and the lecturer
  // can show them examples before clicking "Next task".
  async function handleEndTaskNow() {
    if (!QUESTION_ID) return;
    setAdvancing(true);
    setAdvanceMessage(null);
    try {
      setQuestion(await endQuestionNow(QUESTION_ID));
    } catch (e) {
      setAdvanceMessage(e instanceof Error ? e.message : "Could not end this task.");
    } finally {
      setAdvancing(false);
    }
  }

  async function handleFinishLecture() {
    setConfirmFinishOpen(false);
    setAdvancing(true);
    setAdvanceMessage(null);
    try {
      const res = await finishLecture(QUESTION_ID);
      if (res.lecture_id != null) {
        // The summary view is now reachable by its own URL (?lecture_id=) --
        // land there directly rather than toggling in-page state, so it's
        // the same shareable/bookmarkable link the home dashboard's history
        // list uses for this same lecture.
        window.location.href = `lecturer.html?lecture_id=${res.lecture_id}`;
        return;
      }
      // Defensive fallback -- there was no active lecture to end (shouldn't
      // normally happen if this button is visible at all).
      setLectureFinished(true);
    } catch (e) {
      setAdvanceMessage(e instanceof Error ? e.message : "Could not finish the lecture.");
      setAdvancing(false);
    }
  }

  // Lobby mode's "Start lecture" button -- reuses the same "start the
  // earliest validated draft" logic "Next task" already uses (there's
  // nothing currently live yet, so passing no current_question_id is
  // exactly right), just from the lobby's own view instead of a live task's.
  async function handleStartLecture() {
    setStartingLecture(true);
    setStartError(null);
    try {
      const res = await nextTask(null);
      if (res.started) {
        window.location.href = `lecturer.html?question_id=${encodeURIComponent(res.started.id)}`;
      } else {
        setStartError("No questions ready to start yet. Add and validate one on setup first.");
        setStartingLecture(false);
      }
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Could not start the lecture.");
      setStartingLecture(false);
    }
  }


  function toggleExpanded(subId: number) {
    setExpandedSubIds((prev) => {
      const next = new Set(prev);
      if (next.has(subId)) next.delete(subId);
      else next.add(subId);
      return next;
    });
  }

  // The lecturer shouldn't have to guess what a cluster's talking point
  // means -- each issue expands in place to the actual student code behind
  // it (with the input/expected/actual output of the test it failed), so the
  // discussion point is a starting point to investigate, not the only
  // evidence. The polled submissions list already carries everything shown;
  // only ids missing from it (none, normally) are fetched individually.
  function clusterIds(c: ClusterRow) {
    return c.submission_ids && c.submission_ids.length ? c.submission_ids : [c.example_submission_id];
  }

  function knownSub(id: number) {
    return subRows.find((r) => r.id === id) ?? fetchedSubs[id];
  }

  async function toggleIssue(c: ClusterRow) {
    const key = issueKey(c);
    const opening = !openIssues.has(key);
    setOpenIssues((prev) => {
      const next = new Set(prev);
      if (opening) next.add(key);
      else next.delete(key);
      return next;
    });
    if (!opening) return;
    const missing = clusterIds(c).filter((id) => !knownSub(id));
    if (missing.length === 0) return;
    setIssueLoadError(false);
    try {
      const subs = await Promise.all(missing.map((id) => fetchSubmissionDetail(id)));
      setFetchedSubs((prev) => ({ ...prev, ...Object.fromEntries(subs.map((sub) => [sub.id, sub])) }));
    } catch {
      setIssueLoadError(true);
    }
  }

  // "Show to students" -- the lecturer's call that an issue is worth going
  // over with the class, even if only one student hit it: its example goes to
  // every student's waiting screen once time is up (see
  // aggregation.raise_issue()). Raising a wrong_answer issue waits on a live
  // Label call, hence the busy state.
  async function toggleRaised(c: ClusterRow) {
    if (!QUESTION_ID) return;
    const key = issueKey(c);
    setRaisingKey(key);
    setRaiseError(null);
    try {
      setClusters(await raiseIssue(QUESTION_ID, c, !c.raised));
    } catch (e) {
      setRaiseError(e instanceof Error ? e.message : "Could not update this issue.");
    } finally {
      setRaisingKey(null);
    }
  }

  // Passing last: it's context ("how many got there"), not an issue to discuss.
  const issueRows = [
    ...clusters.filter((c) => c.exec_verdict !== "pass"),
    ...clusters.filter((c) => c.exec_verdict === "pass"),
  ];

  // `expected` is just a number the lecturer typed in at setup time (see
  // live-submission-progress-scoping-decision.md) -- there's no roster, so
  // it can be wrong in either direction. Submitted > expected is a normal
  // outcome (more students showed up than the lecturer guessed), not an
  // error state, so it needs its own wording rather than raw "7/2 submitted"
  // reading like something's broken.
  function submittedText(submitted: number, expected: number | null): string {
    if (expected == null) return `${submitted} submitted`;
    if (submitted > expected) return `${submitted} submitted (more than the ${expected} expected)`;
    return `${submitted}/${expected} submitted`;
  }

  return (
    <>
      <NavBar />
      <ConfirmDialog
        open={confirmFinishOpen}
        title="End the whole lecture?"
        message="Every student is sent to the end-of-lecture screen and can't submit anything more. Tasks you haven't started yet won't run. This can't be undone."
        confirmLabel="End lecture"
        cancelLabel="Keep going"
        focusCancel
        onConfirm={handleFinishLecture}
        onCancel={() => setConfirmFinishOpen(false)}
      />
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 id="page-title">{pageTitle}</h1>
        </div>
        <div style={{ textAlign: "right" }}>
          <div id="stats">
            {!LECTURE_ID && !LOBBY_ID && `${subRows.length} submission${subRows.length === 1 ? "" : "s"}`}
          </div>
          {!LECTURE_ID && !LOBBY_ID && (
            <HeaderNavLink href="setup.html" style={{ fontSize: "0.85rem" }}>
              Question setup &rarr;
            </HeaderNavLink>
          )}
        </div>
      </header>
      <main>
        {LOBBY_ID && (
          <div className="card" id="lobby-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <h2>Lobby</h2>
              <button className="secondary" onClick={() => (window.location.href = "setup.html")}>
                Manage questions
              </button>
            </div>
            {lobbyError && <div className="summary-status summary-error">{lobbyError}</div>}
            {lobbyLecture && (
              <>
                <div id="join-code-display" className="join-code-display">
                  <div className="join-code-label">Join code</div>
                  <div className="join-code-value">{lobbyLecture.join_code}</div>
                  <div className="join-code-hint">Students enter this on the student page to join.</div>
                </div>
                <div id="joined-count" style={{ textAlign: "center", margin: "0.9rem 0" }}>
                  <span style={{ fontSize: "1.4rem", fontWeight: "bold" }}>
                    {joinedCount != null ? joinedCount : "--"}
                  </span>{" "}
                  <span style={{ color: "var(--muted)" }}>
                    student{joinedCount === 1 ? "" : "s"} joined
                  </span>
                </div>
                <div style={{ textAlign: "center" }}>
                  <button onClick={handleStartLecture} disabled={startingLecture}>
                    {startingLecture ? "Starting..." : "Start lecture (earliest question)"}
                  </button>
                </div>
                {startError && (
                  <div className="summary-status summary-error" style={{ textAlign: "center", marginTop: "0.6rem" }}>
                    {startError}
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {QUESTION_ID && !LECTURE_ID && (
          <div className="card" id="task-control-card">
            {lectureFinished ? (
              <div id="lecture-finished-banner">
                <h2>Lecture finished</h2>
                <p>Students now see an end-of-lecture screen. The session summary is below.</p>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <h2>Task control</h2>
                  {joinCode && (
                    <div id="join-code-pill" className="join-code-pill">
                      Join code <strong>{joinCode}</strong>
                    </div>
                  )}
                </div>
                <div className="task-control-row">
                  <div>
                    {secondsRemaining === 0 ? (
                      <>
                        <div className="timer-label">Pacing</div>
                        <div className="timer-value time-up">
                          Time's up --{" "}
                          {progress ? submittedText(progress.submitted, progress.expected) : "-- submitted"}
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="timer-label">Time remaining</div>
                        <div className="timer-value">
                          {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
                        </div>
                      </>
                    )}
                  </div>
                  <div className="task-control-actions">
                    {secondsRemaining != null && secondsRemaining > 0 && (
                      <button className="secondary" onClick={handleEndTaskNow} disabled={advancing}>
                        End task now
                      </button>
                    )}
                    <button
                      className={secondsRemaining === 0 ? undefined : "secondary"}
                      onClick={handleNextTask}
                      disabled={advancing}
                    >
                      Next task
                    </button>
                  </div>
                </div>
                {secondsRemaining === 0 && (
                  <div className="advance-message">
                    Students are on their waiting screen. Use "Show to students" on an issue below to go
                    over it with them, then "Next task" when you're ready.
                  </div>
                )}
                {advanceMessage && <div className="advance-message">{advanceMessage}</div>}
                <div className="end-lecture-row">
                  <button
                    className="end-lecture-link"
                    onClick={() => setConfirmFinishOpen(true)}
                    disabled={advancing}
                  >
                    End lecture...
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        {!lectureFinished && !LECTURE_ID && !LOBBY_ID && (
        <>
        <div className="card" id="progress-card" style={{ display: progress ? "block" : "none" }}>
          <h2>Class progress</h2>
          <div id="progress-text" style={{ fontSize: "1.4rem", fontWeight: "bold" }}>
            {progress && submittedText(progress.submitted, progress.expected)}
          </div>
          {progress && (
            <ClassProgress
              subs={subRows}
              expected={progress.expected}
              // Activity only means something while students can still type --
              // once time's up everyone's heartbeat stops and would read "away".
              activity={secondsRemaining != null && secondsRemaining > 0 ? activity : null}
            />
          )}
        </div>
        <div className="grid">
          <div className="card" id="issues-card">
            <h2>
              Common issues
              {QUESTION_ID && !settled && <span className="pulse-dot" title="Still updating" />}
            </h2>
            {raiseError && <div className="issue-error">{raiseError}</div>}
            {issueRows.length === 0 ? (
              <div className="card-empty">Nothing yet.</div>
            ) : (
              <ul className="issue-list">
                {issueRows.map((c) => {
                  const key = issueKey(c);
                  const open = openIssues.has(key);
                  const subs = clusterIds(c)
                    .map(knownSub)
                    .filter((sub): sub is SubmissionRow => !!sub);
                  const isPass = c.exec_verdict === "pass";
                  const raising = raisingKey === key;
                  return (
                    <li
                      key={key}
                      className={["issue", isPass && "issue-pass", c.raised && "issue-raised"].filter(Boolean).join(" ")}
                    >
                      <div className="issue-head">
                        <span className="issue-count">
                          {c.count} {c.count === 1 ? "student" : "students"}
                        </span>
                        <span className="issue-tag">{issueTag(c)}</span>
                        {c.raised && <span className="issue-raised-badge">Showing to students</span>}
                      </div>
                      <p className={c.discussion_point ? "issue-point" : "issue-point issue-point-muted"}>
                        {issueText(c)}
                      </p>
                      <div className="issue-actions">
                        <button className="view-example-btn" aria-expanded={open} onClick={() => toggleIssue(c)}>
                          {open ? "Hide code" : "View code"}
                        </button>
                        {!isPass && QUESTION_ID && (
                          <button
                            className="view-example-btn"
                            aria-pressed={c.raised}
                            disabled={raisingKey !== null}
                            onClick={() => toggleRaised(c)}
                          >
                            {raising ? (c.raised ? "Removing..." : "Sharing...") : c.raised ? "Stop showing" : "Show to students"}
                          </button>
                        )}
                      </div>
                      {open && (
                        <div className="issue-examples">
                          {subs.length > 0
                            ? groupByCode(subs).map((group) => <ExampleBlock key={group[0].id} subs={group} />)
                            : issueLoadError
                            ? "Could not load these submissions."
                            : "Loading..."}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div className="card">
            <h2>
              {QUESTION_ID && settled ? "Submissions" : "Submissions (live)"}
              {QUESTION_ID && !settled && <span className="pulse-dot" title="Still updating" />}
            </h2>
            <div id="empty-state" style={{ display: subRows.length === 0 ? "block" : "none" }}>
              No submissions yet.
            </div>
            <table id="sub-table" style={{ display: subRows.length === 0 ? "none" : "table" }}>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Student</th>
                  <th>Result</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody id="sub-body">
                {subRows.map((row) => {
                  const time = (row.created_at || "").split(" ")[1] || row.created_at;
                  const isOpen = expandedSubIds.has(row.id);
                  return (
                    <Fragment key={row.id}>
                      <tr>
                        <td>{time || ""}</td>
                        <td>
                          <button className="student-name-btn" onClick={() => toggleExpanded(row.id)}>
                            {isOpen ? "▾" : "▸"} {row.student_name}
                          </button>
                        </td>
                        <td>
                          <span className={verdictClass(row.verdict || "")}>
                            {verdictLabel(row.verdict || "")}
                          </span>
                        </td>
                        <td>
                          {row.tests_passed}/{row.tests_total}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="detail-row">
                          <td colSpan={4}>
                            <pre>{row.source_code}</pre>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        </>
        )}
        {(lectureFinished || LECTURE_ID) && (
          <>
          <div id="back-to-home-row">
            <a href="index.html" className="back-to-home-btn">
              &larr; Back to home
            </a>
          </div>
          <div className="grid" id="session-summary">
            <div className="card" id="summary-tasks-card">
              <h2>{LECTURE_ID && summary ? summary.lecture_label : "Session summary"}</h2>
              {summaryLoading && <div className="summary-status">Loading...</div>}
              {summaryError && <div className="summary-status summary-error">{summaryError}</div>}
              {summary && summary.tasks.length === 0 && (
                <div className="summary-status">No tasks were run this lecture.</div>
              )}
              {summary && summary.tasks.length > 0 && (
                // Same chart as the live dashboard, one per task -- each
                // student's best result, with their attempts behind "Show
                // students". Replaces the old verdict-pill column, which
                // counted latest (not best) results and would have disagreed
                // with the chart right next to it.
                <ul id="summary-task-list">
                  {summary.tasks.map((t) => (
                    <li key={t.question_id} className="summary-task">
                      <div className="summary-task-head">
                        <strong>{t.title}</strong>
                        <span className="summary-task-count">{submittedText(t.submitted, t.expected)}</span>
                        <a
                          className="drilldown-link"
                          href={`lecturer.html?question_id=${encodeURIComponent(t.question_id)}`}
                        >
                          View task &rarr;
                        </a>
                      </div>
                      {taskSubs[t.question_id] ? (
                        <ClassProgress subs={taskSubs[t.question_id]} expected={t.expected} activity={null} finished />
                      ) : (
                        <div className="summary-status">
                          {taskSubsLoaded ? "Could not load this task's submissions." : "Loading..."}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="card" id="carry-forward-card">
              <h2>Carry-forward discussion points</h2>
              <div className="hint" style={{ marginBottom: "0.75rem" }}>
                Issues that came up on more than one task this lecture, worth revisiting next time.
              </div>
              {summary && summary.carry_forward_discussion_points.length === 0 && (
                <div className="summary-status">Nothing recurred across tasks.</div>
              )}
              {summary && summary.carry_forward_discussion_points.length > 0 && (
                <ul id="carry-forward-list">
                  {summary.carry_forward_discussion_points.map((c, i) => (
                    <li key={i}>
                      <div>{c.discussion_point}</div>
                      <div className="carry-forward-tasks">Recurred on: {c.task_titles.join(", ")}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          </>
        )}
      </main>
    </>
  );
}
