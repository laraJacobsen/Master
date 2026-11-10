import { Fragment, useEffect, useState } from "react";
import type {
  ClusterRow,
  LectureRow,
  LectureSummary,
  ProgressResponse,
  QuestionRow,
  StudentActivity,
  SubmissionRow,
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
import { ClassBar } from "./ClassBar";
import { IssueList } from "./IssueList";
import { clusterIds, issueKey } from "./issues";
import { TaskHeader } from "./TaskHeader";
import { buildTracks } from "./studentTracks";
import { StudentGrid } from "./StudentGrid";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { HeaderNavLink } from "../shared/HeaderNavLink";
import { NavBar } from "../shared/NavBar";
import { Badge, Button, Card, Callout, ErrorText, Eyebrow, LinkButton, Page, PageHeader, SectionTitle, TextLink } from "../shared/ui";
import { cx } from "../shared/cx";
import type { Tone } from "../shared/ui";

const POLL_MS = 3000;

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

const VERDICT_TONE: Record<string, Tone> = {
  correct: "success",
  partially_correct: "warning",
  incorrect: "danger",
  error: "danger",
};
function verdictLabel(v: string) {
  const labels: Record<string, string> = {
    correct: "Correct",
    partially_correct: "Partial",
    incorrect: "Incorrect",
    error: "Error",
  };
  return labels[v] || v;
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
  // Whether "Next task" would start anything -- polled, since a question added
  // on setup mid-lecture brings it back. null = not known yet, so the button
  // shows as usual until the first answer arrives.
  const [hasNextTask, setHasNextTask] = useState<boolean | null>(null);

  // Powers the "Time remaining" banner and gates the Next task/Finish
  // lecture controls -- see api_lecture_next/finish in backend/main.py.
  const [question, setQuestion] = useState<QuestionRow | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
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
    }
    const pollActiveLecture = () => {
      if (!QUESTION_ID) return;
      fetchActiveLecture()
        .then((a) => {
          setJoinCode(a.lecture?.join_code ?? null);
          setHasNextTask(a.has_next_task ?? null);
        })
        .catch(() => {
          // Not critical -- the card omits the code and keeps "Next task".
        });
    };

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
    pollActiveLecture();
    const t1 = window.setInterval(poll, POLL_MS);
    const t2 = window.setInterval(pollClusters, POLL_MS);
    const t3 = window.setInterval(pollProgress, POLL_MS);
    const t4 = window.setInterval(pollQuestion, POLL_MS);
    const t5 = window.setInterval(pollActivity, POLL_MS);
    const t6 = window.setInterval(pollActiveLecture, POLL_MS);
    return () => {
      window.clearInterval(t1);
      window.clearInterval(t2);
      window.clearInterval(t3);
      window.clearInterval(t4);
      window.clearInterval(t5);
      window.clearInterval(t6);
    };
  }, []);

  // Ticks the "Time remaining" banner once a second, anchored to the
  // question's server-side started_at/duration_seconds (re-synced whenever
  // pollQuestion above refreshes `question`) rather than counting down from
  // page-load, so it can't drift from what the student page shows.
  useEffect(() => {
    if (!question || question.status !== "live" || !question.started_at) {
      setSecondsRemaining(null);
      return;
    }
    const startedMs = new Date(question.started_at.replace(" ", "T") + "Z").getTime();
    const endMs = startedMs + question.duration_seconds * 1000;
    const tick = () => {
      const now = Date.now();
      setSecondsRemaining(Math.max(0, Math.round((endMs - now) / 1000)));
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
        // Someone started/removed the last draft since the last poll.
        setHasNextTask(false);
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

  const lastTask = hasNextTask === false;
  const taskRunning = secondsRemaining != null && secondsRemaining > 0;
  // What an issue's bar is a share of: everyone who's submitted so far.
  const classSize = Math.max(progress?.submitted ?? 0, ...clusters.map((c) => c.count), 1);
  const tracks = buildTracks(subRows, taskRunning ? activity : null);

  return (
    <>
      <NavBar wide={Boolean(QUESTION_ID && !LECTURE_ID)} />
      <ConfirmDialog
        open={confirmFinishOpen}
        title="End the whole lecture?"
        message={
          "Every student is sent to the end-of-lecture screen and can't submit anything more." +
          (lastTask ? "" : " Tasks you haven't started yet won't run.") +
          " This can't be undone."
        }
        confirmLabel="End lecture"
        cancelLabel="Keep going"
        focusCancel
        onConfirm={handleFinishLecture}
        onCancel={() => setConfirmFinishOpen(false)}
      />
      <Page width={QUESTION_ID && !LECTURE_ID ? "full" : "wide"}>
        {!(QUESTION_ID && !LECTURE_ID) && (
          <PageHeader
            eyebrow={LECTURE_ID ? "Lecture summary" : LOBBY_ID ? "Lobby" : "Dashboard"}
            title={pageTitle}
            actions={
              !LECTURE_ID && !LOBBY_ID ? (
                <div className="text-right">
                  <div className="font-mono text-sm text-zinc-500 tabular-nums">
                    {subRows.length} submission{subRows.length === 1 ? "" : "s"}
                  </div>
                  <HeaderNavLink href="setup.html">Question setup &rarr;</HeaderNavLink>
                </div>
              ) : LECTURE_ID ? (
                /* Summaries are opened from the history page, so that's where "back" goes. */
                <LinkButton href="history.html" variant="secondary">
                  &larr; Lecture history
                </LinkButton>
              ) : undefined
            }
          />
        )}

        {LOBBY_ID && (
          <div className="grid gap-6 lg:grid-cols-12">
            <Card className="p-8 sm:p-10 lg:col-span-8">
              {lobbyError && <ErrorText>{lobbyError}</ErrorText>}
              {lobbyLecture && (
                <>
                  <Eyebrow>Join code</Eyebrow>
                  <div className="mt-2 font-mono text-6xl font-bold tracking-[0.18em] text-zinc-950 sm:text-7xl">
                    {lobbyLecture.join_code}
                  </div>
                  <p className="mt-3 text-sm text-zinc-500">Students enter this on the student page to join.</p>
                </>
              )}
            </Card>
            <Card className="flex flex-col p-8 lg:col-span-4">
              <Eyebrow>Joined</Eyebrow>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-mono text-5xl font-semibold tracking-tight text-zinc-950 tabular-nums">
                  {joinedCount != null ? joinedCount : "--"}
                </span>
                <span className="text-sm text-zinc-500">student{joinedCount === 1 ? "" : "s"}</span>
              </div>
              <div className="mt-auto grid gap-2 pt-8">
                {lobbyLecture && (
                  <Button size="lg" onClick={handleStartLecture} disabled={startingLecture}>
                    {startingLecture ? "Starting..." : "Start lecture"}
                  </Button>
                )}
                <Button variant="secondary" size="lg" onClick={() => (window.location.href = "setup.html")}>
                  Manage questions
                </Button>
              </div>
              {startError && <ErrorText className="mt-3">{startError}</ErrorText>}
            </Card>
          </div>
        )}

        {QUESTION_ID && !LECTURE_ID && (
          lectureFinished ? (
            <Callout tone="success" className="mt-8">
              <h2 className="font-bold">Lecture finished</h2>
              <p className="mt-1">Students now see an end-of-lecture screen. The session summary is below.</p>
            </Callout>
          ) : (
            <>
              <TaskHeader
                title={pageTitle}
                question={question}
                secondsRemaining={secondsRemaining}
                joinCode={joinCode}
                lastTask={lastTask}
                advancing={advancing}
                advanceMessage={advanceMessage}
                onNextTask={handleNextTask}
                onEndTaskNow={handleEndTaskNow}
                onEndLecture={() => setConfirmFinishOpen(true)}
              />
              <section className="pt-10 pb-12" aria-label="Class progress">
                <ClassBar
                  tracks={tracks}
                  submitted={progress?.submitted ?? tracks.filter((t) => t.best).length}
                  expected={progress?.expected ?? null}
                  showActivity={taskRunning}
                />
              </section>
            </>
          )
        )}

        {!lectureFinished && !LECTURE_ID && !LOBBY_ID && (
          <div className="grid items-start gap-x-14 gap-y-12 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)] 2xl:grid-cols-[minmax(0,1fr)_minmax(18rem,30rem)]">
            <section aria-label="Common issues" className="min-w-0">
              <div className="mb-4 flex items-baseline gap-3">
                <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Issues</h2>
                <span className="text-[13px] text-zinc-400">biggest first · click one to see the code</span>
              </div>
              {raiseError && <ErrorText className="mb-3">{raiseError}</ErrorText>}
              <IssueList
                issues={clusters}
                classSize={classSize}
                openKeys={openIssues}
                onToggleOpen={toggleIssue}
                subsFor={(c) =>
                  clusterIds(c)
                    .map(knownSub)
                    .filter((sub): sub is SubmissionRow => !!sub)
                }
                loadError={issueLoadError}
                raisingKey={raisingKey}
                onToggleRaised={QUESTION_ID ? toggleRaised : null}
              />
            </section>
            {QUESTION_ID ? (
              <div className="lg:sticky lg:top-20">
                <StudentGrid subs={subRows} activity={taskRunning ? activity : null} />
              </div>
            ) : (
              // No ?question_id= (the old everything-at-once view): students span
              // several questions there, so it keeps the plain attempt log.
              <Card>
                <SectionTitle>Submissions</SectionTitle>
                {subRows.length === 0 ? (
                  <p className="mt-3 text-sm text-zinc-500">No submissions yet.</p>
                ) : (
                  <table className="mt-3 w-full border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-zinc-200 text-left text-[11px] font-semibold tracking-[0.08em] text-zinc-500 uppercase">
                        <th className="py-2 pr-2 font-semibold">Time</th>
                        <th className="py-2 pr-2 font-semibold">Student</th>
                        <th className="py-2 pr-2 font-semibold">Result</th>
                        <th className="py-2 font-semibold">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {subRows.map((row) => {
                        const time = (row.created_at || "").split(" ")[1] || row.created_at;
                        const isOpen = expandedSubIds.has(row.id);
                        return (
                          <Fragment key={row.id}>
                            <tr className={cx("align-top", !isOpen && "border-b border-zinc-100")}>
                              <td className="py-2 pr-2 font-mono text-xs text-zinc-500">{time || ""}</td>
                              <td className="py-2 pr-2">
                                <button
                                  type="button"
                                  className="rounded-sm text-left text-zinc-900 underline decoration-zinc-300 decoration-dotted underline-offset-4 hover:decoration-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
                                  aria-expanded={isOpen}
                                  onClick={() => toggleExpanded(row.id)}
                                >
                                  {isOpen ? "▾" : "▸"} {row.student_name}
                                </button>
                              </td>
                              <td className="py-2 pr-2">
                                <Badge tone={VERDICT_TONE[row.verdict || ""] ?? "neutral"}>
                                  {verdictLabel(row.verdict || "")}
                                </Badge>
                              </td>
                              <td className="py-2 font-mono text-xs tabular-nums">
                                {row.tests_passed}/{row.tests_total}
                              </td>
                            </tr>
                            {isOpen && (
                              <tr className="border-b border-zinc-100">
                                <td colSpan={4} className="pb-3">
                                  <pre className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs break-words whitespace-pre-wrap">
                                    {row.source_code}
                                  </pre>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </Card>
            )}
          </div>
        )}

        {(lectureFinished || LECTURE_ID) && (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            {lectureFinished && (
              <div className="lg:col-span-2">
                {/* Summaries are opened from the history page, so that's where "back" goes. */}
                <LinkButton href="history.html" variant="secondary">
                  &larr; Lecture history
                </LinkButton>
              </div>
            )}
            <Card>
              <SectionTitle>Tasks</SectionTitle>
              {summaryLoading && <p className="mt-3 text-sm text-zinc-500">Loading...</p>}
              {summaryError && <ErrorText className="mt-3">{summaryError}</ErrorText>}
              {summary && summary.tasks.length === 0 && (
                <p className="mt-3 text-sm text-zinc-500">No tasks were run this lecture.</p>
              )}
              {summary && summary.tasks.length > 0 && (
                // Same chart as the live dashboard, one per task -- each
                // student's best result, with their attempts behind "Show
                // students". Replaces the old verdict-pill column, which
                // counted latest (not best) results and would have disagreed
                // with the chart right next to it.
                <ul className="mt-2 divide-y divide-zinc-200">
                  {summary.tasks.map((t) => (
                    <li key={t.question_id} className="py-5 last:pb-0">
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <strong className="text-sm font-semibold text-zinc-950">{t.title}</strong>
                        <span className="text-[13px] text-zinc-500">{submittedText(t.submitted, t.expected)}</span>
                        <TextLink
                          className="ml-auto text-[13px] whitespace-nowrap"
                          href={`lecturer.html?question_id=${encodeURIComponent(t.question_id)}`}
                        >
                          View task &rarr;
                        </TextLink>
                      </div>
                      {taskSubs[t.question_id] ? (
                        <ClassProgress subs={taskSubs[t.question_id]} expected={t.expected} activity={null} finished />
                      ) : (
                        <p className="mt-2 text-sm text-zinc-500">
                          {taskSubsLoaded ? "Could not load this task's submissions." : "Loading..."}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <SectionTitle>Carry-forward discussion points</SectionTitle>
              <p className="mt-1 text-[13px] text-zinc-500">
                Issues that came up on more than one task this lecture, worth revisiting next time.
              </p>
              {summary && summary.carry_forward_discussion_points.length === 0 && (
                <p className="mt-4 text-sm text-zinc-500">Nothing recurred across tasks.</p>
              )}
              {summary && summary.carry_forward_discussion_points.length > 0 && (
                <ul className="mt-3 divide-y divide-zinc-200">
                  {summary.carry_forward_discussion_points.map((c, i) => (
                    <li key={i} className="py-3 text-sm leading-snug last:pb-0">
                      <div className="text-zinc-900">{c.discussion_point}</div>
                      <div className="mt-1 text-xs text-zinc-500">Recurred on: {c.task_titles.join(", ")}</div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        )}
      </Page>
    </>
  );
}
