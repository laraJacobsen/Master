import { Fragment, useEffect, useState } from "react";
import type {
  ClusterRow,
  LectureSummary,
  ProgressResponse,
  QuestionRow,
  SubmissionRow,
  ValidationTestResult,
} from "../shared/types";
import {
  fetchClusters,
  fetchLectureSummary,
  fetchProgress,
  fetchQuestionDetail,
  fetchSubmissionDetail,
  fetchSubmissions,
  finishLecture,
  nextTask,
} from "../shared/api";
import { HeaderNavLink } from "../shared/HeaderNavLink";

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
function clusterLabel(c: ClusterRow) {
  if (c.exec_verdict === "rejected") return "Rejected submission";
  if (c.exec_verdict === "pass") return "Passing";
  const verdict = (c.exec_verdict || "unknown").replace(/_/g, " ");
  return c.error_type && c.error_type !== "none" ? `${verdict} (${c.error_type})` : verdict;
}

function ExampleBlock({ sub }: { sub: SubmissionRow }) {
  const meta = `${sub.student_name} -- attempt ${sub.attempt_number} -- ${sub.tests_passed}/${sub.tests_total} passed`;

  const results: ValidationTestResult[] = JSON.parse(sub.raw_test_results || "[]");
  const failing = results.find((r) => !r.passed);

  return (
    <div className="inspector-example">
      <div className="inspector-meta">{meta}</div>
      <div className="inspector-diff">
        {failing ? (
          <>
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
          </>
        ) : (
          <em>All test cases passed.</em>
        )}
      </div>
      <code className="inspector-code">{sub.source_code}</code>
    </div>
  );
}

interface InspectorState {
  title: string;
  loading: boolean;
  error: boolean;
  subs: SubmissionRow[];
}

export default function App() {
  const [pageTitle, setPageTitle] = useState("Interactive Lecture -- Lecturer View");

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
  const [inspector, setInspector] = useState<InspectorState | null>(null);

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

  // The STATE 2 post-lecture view -- fetched once, right when "End session"
  // succeeds (see handleFinishLecture below), not polled: the lecture is
  // over, so unlike the live dashboard there's nothing new to arrive.
  const [summary, setSummary] = useState<LectureSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Historical mode (?lecture_id=): fetch that lecture's summary once and
  // stop -- no polling, since a past lecture has nothing new to arrive.
  useEffect(() => {
    if (!LECTURE_ID) return;
    setSummaryLoading(true);
    setSummaryError(null);
    fetchLectureSummary(Number(LECTURE_ID))
      .then((s) => {
        setSummary(s);
        setPageTitle(`Lecturer View -- ${s.lecture_label}`);
      })
      .catch((e) => {
        setSummaryError(e instanceof Error ? e.message : "Could not load this lecture's summary.");
      })
      .finally(() => setSummaryLoading(false));
  }, []);

  useEffect(() => {
    if (LECTURE_ID) return; // historical mode -- no live polling, see effect above.

    if (QUESTION_ID) {
      fetchQuestionDetail(QUESTION_ID)
        .then((q) => {
          setPageTitle(`Lecturer View -- ${q.title}`);
          setQuestion(q);
        })
        .catch(() => {
          // Leave the generic title in place.
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
    const t1 = window.setInterval(poll, POLL_MS);
    const t2 = window.setInterval(pollClusters, POLL_MS);
    const t3 = window.setInterval(pollProgress, POLL_MS);
    const t4 = window.setInterval(pollQuestion, POLL_MS);
    return () => {
      window.clearInterval(t1);
      window.clearInterval(t2);
      window.clearInterval(t3);
      window.clearInterval(t4);
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
        setAdvanceMessage("No more tasks left to start -- click \"Finish lecture\" to end.");
        setAdvancing(false);
      }
    } catch (e) {
      setAdvanceMessage(e instanceof Error ? e.message : "Could not advance to the next task.");
      setAdvancing(false);
    }
  }

  async function handleFinishLecture() {
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

  function toggleExpanded(subId: number) {
    setExpandedSubIds((prev) => {
      const next = new Set(prev);
      if (next.has(subId)) next.delete(subId);
      else next.add(subId);
      return next;
    });
  }

  // The lecturer shouldn't have to guess what a cluster's talking point
  // means -- this fetches the actual example submissions (real student code,
  // real input/expected/actual output for the test case each failed) on
  // demand, so the discussion point is a starting point to investigate, not
  // the only evidence. A cluster can span several distinct students, so this
  // fetches and stacks all of them rather than picking just one.
  async function showExamples(subIds: number[]) {
    setInspector({
      title: subIds.length > 1 ? `Example submissions (${subIds.length})` : "Example submission",
      loading: true,
      error: false,
      subs: [],
    });
    try {
      const subs = await Promise.all(subIds.map((id) => fetchSubmissionDetail(id)));
      setInspector({
        title: subIds.length > 1 ? `Example submissions (${subIds.length})` : "Example submission",
        loading: false,
        error: false,
        subs,
      });
    } catch {
      setInspector((prev) => (prev ? { ...prev, loading: false, error: true } : prev));
    }
  }

  const discussionPoints = clusters.filter((c) => c.discussion_point).map((c) => c.discussion_point as string);

  const progressPct =
    progress && progress.expected != null && progress.expected > 0
      ? Math.min(100, Math.round((progress.submitted / progress.expected) * 100))
      : 0;

  return (
    <>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 id="page-title">{pageTitle}</h1>
        </div>
        <div style={{ textAlign: "right" }}>
          <div id="stats">
            {!LECTURE_ID && `${subRows.length} submission${subRows.length === 1 ? "" : "s"}`}
          </div>
          <HeaderNavLink href="index.html" style={{ fontSize: "0.85rem" }}>
            &larr; Home
          </HeaderNavLink>
          {!LECTURE_ID && (
            <HeaderNavLink href="setup.html" style={{ fontSize: "0.85rem", marginLeft: "0.75rem" }}>
              Question setup &rarr;
            </HeaderNavLink>
          )}
        </div>
      </header>
      <main>
        {QUESTION_ID && !LECTURE_ID && (
          <div className="card" id="task-control-card">
            {lectureFinished ? (
              <div id="lecture-finished-banner">
                <h2>Lecture finished</h2>
                <p>Students now see an end-of-lecture screen. The session summary is below.</p>
              </div>
            ) : (
              <>
                <h2>Task control</h2>
                <div className="task-control-row">
                  <div>
                    {secondsRemaining === 0 ? (
                      <>
                        <div className="timer-label">Pacing</div>
                        <div className="timer-value time-up">
                          Time's up --{" "}
                          {progress
                            ? progress.expected != null
                              ? `${progress.submitted}/${progress.expected} submitted`
                              : `${progress.submitted} submitted`
                            : "-- submitted"}
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
                  <div>
                    <button className="secondary" onClick={handleNextTask} disabled={advancing}>
                      Next task
                    </button>
                    <button
                      className="danger"
                      onClick={handleFinishLecture}
                      disabled={advancing}
                      style={{ marginLeft: "0.6rem" }}
                    >
                      End session
                    </button>
                  </div>
                </div>
                {advanceMessage && <div className="advance-message">{advanceMessage}</div>}
              </>
            )}
          </div>
        )}
        {!lectureFinished && !LECTURE_ID && (
        <>
        <div className="card" id="progress-card" style={{ display: progress ? "block" : "none" }}>
          <h2>Submission progress</h2>
          <div id="progress-text" style={{ fontSize: "1.4rem", fontWeight: "bold" }}>
            {progress &&
              (progress.expected == null
                ? `${progress.submitted} submitted`
                : `${progress.submitted}/${progress.expected} submitted`)}
          </div>
          <div
            id="progress-bar-track"
            style={{
              background: "#eceef3",
              borderRadius: "999px",
              height: "10px",
              marginTop: "0.6rem",
              overflow: "hidden",
              display: progress && progress.expected != null ? "block" : "none",
            }}
          >
            <div
              id="progress-bar-fill"
              style={{ background: "var(--navy)", height: "100%", width: `${progressPct}%` }}
            />
          </div>
          <div id="progress-not-submitted" style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: "0.4rem" }}>
            {progress && progress.expected != null
              ? progress.not_submitted && progress.not_submitted > 0
                ? `${progress.not_submitted} not yet submitted`
                : "Everyone has submitted."
              : ""}
          </div>
        </div>
        <div className="grid">
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
          <div className="card">
            <h2>
              Discussion points for the class
              {QUESTION_ID && !settled && <span className="pulse-dot" title="Still updating" />}
            </h2>
            <ul id="discussion-list">
              {discussionPoints.length === 0 ? (
                <li style={{ color: "#5a6072" }}>Nothing yet.</li>
              ) : (
                discussionPoints.map((d, i) => <li key={i}>{d}</li>)
              )}
            </ul>
          </div>
          <div className="card">
            <h2>Common issues (by count)</h2>
            <table id="cluster-table" style={{ display: clusters.length === 0 ? "none" : "table" }}>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Count</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="cluster-body">
                {clusters.map((c, i) => {
                  const ids =
                    c.submission_ids && c.submission_ids.length ? c.submission_ids : [c.example_submission_id];
                  const label = ids.length > 1 ? `View all (${ids.length})` : "View code";
                  return (
                    <tr key={i}>
                      <td>{clusterLabel(c)}</td>
                      <td>{c.count}</td>
                      <td>
                        <button className="view-example-btn" onClick={() => showExamples(ids)}>
                          {label}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div id="cluster-empty" style={{ color: "#5a6072", fontSize: "0.9rem", display: clusters.length === 0 ? "block" : "none" }}>
              Nothing yet.
            </div>
          </div>
          <div className="card" id="inspector-card" style={{ display: inspector ? "block" : "none" }}>
            <h2 id="inspector-title">{inspector ? inspector.title : "Example submission"}</h2>
            <div id="inspector-body">
              {inspector &&
                (inspector.loading
                  ? "Loading..."
                  : inspector.error
                  ? "Could not load one or more of these submissions."
                  : inspector.subs.map((sub) => <ExampleBlock key={sub.id} sub={sub} />))}
            </div>
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
                <table id="summary-table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Submitted</th>
                      <th>Verdict breakdown</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.tasks.map((t) => (
                      <tr key={t.question_id}>
                        <td>{t.title}</td>
                        <td>{t.expected != null ? `${t.submitted}/${t.expected}` : `${t.submitted}`}</td>
                        <td>
                          <div className="verdict-breakdown">
                            {Object.entries(t.verdict_counts).map(([verdict, count]) => (
                              <span key={verdict} className={verdictClass(verdict)}>
                                {verdictLabel(verdict)} {count}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td>
                          <a
                            className="drilldown-link"
                            href={`lecturer.html?question_id=${encodeURIComponent(t.question_id)}`}
                          >
                            View task &rarr;
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="card" id="carry-forward-card">
              <h2>Carry-forward discussion points</h2>
              <div className="hint" style={{ marginBottom: "0.75rem" }}>
                Issues that came up on more than one task this lecture -- worth revisiting next time.
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
