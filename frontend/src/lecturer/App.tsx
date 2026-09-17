import { Fragment, useEffect, useState } from "react";
import type { ClusterRow, ProgressResponse, SubmissionRow, ValidationTestResult } from "../shared/types";
import {
  fetchClusters,
  fetchProgress,
  fetchQuestionDetail,
  fetchSubmissionDetail,
  fetchSubmissions,
} from "../shared/api";

const POLL_MS = 3000;

// Which question this dashboard is watching -- set via ?question_id= (the
// link the setup page's "Start"/"Live dashboard" actions send a lecturer
// to). With no param, falls back to the old behavior of showing everything.
const QUESTION_ID = new URLSearchParams(window.location.search).get("question_id");

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

  useEffect(() => {
    if (QUESTION_ID) {
      fetchQuestionDetail(QUESTION_ID)
        .then((q) => setPageTitle(`Lecturer View -- ${q.title}`))
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

    poll();
    pollClusters();
    pollProgress();
    const t1 = window.setInterval(poll, POLL_MS);
    const t2 = window.setInterval(pollClusters, POLL_MS);
    const t3 = window.setInterval(pollProgress, POLL_MS);
    return () => {
      window.clearInterval(t1);
      window.clearInterval(t2);
      window.clearInterval(t3);
    };
  }, []);

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
            {subRows.length} submission{subRows.length === 1 ? "" : "s"}
          </div>
          <a href="setup.html" style={{ color: "#cadcfc", fontSize: "0.85rem" }}>
            &larr; Question setup
          </a>
        </div>
      </header>
      <main>
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
            <h2>Submissions (live)</h2>
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
            <h2>Discussion points for the class</h2>
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
      </main>
    </>
  );
}
