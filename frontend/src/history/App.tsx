import { useEffect, useState } from "react";
import type { LectureHistoryRow, LectureReview, LectureReviewTask } from "../shared/types";
import { archiveLecture, fetchLectureHistory, fetchLectureReview, unarchiveLecture } from "../shared/api";
import { NavBar } from "../shared/NavBar";

// Lecture history, reachable from the nav bar on every lecturer page. Built
// around one decision: what should a review lecture go back over? Top to
// bottom: headline numbers and a per-week trend, the lectures ranked worst
// first (worst one open), the topics that went worst across lectures, and the
// plain list of every lecture for archiving. Ranking data comes from
// aggregation.lecture_review(); topics are grouped here by task title.

// Mirrors MIN_STUDENTS_FOR_REVIEW in backend/aggregation.py -- only used to
// explain why some lectures aren't ranked (the backend decides which).
const MIN_STUDENTS_FOR_REVIEW = 3;
const TOPICS_SHOWN = 5;
const TREND_LECTURES = 10;

function parseDate(isoLike: string): Date {
  // Server timestamps are "YYYY-MM-DD HH:MM:SS" UTC with no offset marker.
  return new Date(isoLike.replace(" ", "T") + "Z");
}
function formatDate(isoLike: string): string {
  return parseDate(isoLike).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
function shortDate(isoLike: string): string {
  return parseDate(isoLike).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}
function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

// A short, aggregate-only snapshot -- total distinct-student submissions and
// a correct-count, never a per-student breakdown (see the product decision
// against any per-student identification on this dashboard).
function statsSnapshot(row: LectureHistoryRow): string {
  if (row.submitted_total === 0) return "No submissions";
  const correct = row.verdict_counts.correct || 0;
  return `${plural(row.submitted_total, "submission")}, ${correct} correct`;
}

// Same naming as the live dashboard's issue tags.
function issueName(execVerdict: string | null, errorType: string | null): string {
  if (execVerdict === "rejected") return "Rejected before running";
  const verdict = (execVerdict || "unknown").replace(/_/g, " ");
  const label = verdict.charAt(0).toUpperCase() + verdict.slice(1);
  return errorType && errorType !== "none" ? `${label} (${errorType})` : label;
}

function Meter({ rate, size = "md" }: { rate: number; size?: "sm" | "md" }) {
  return (
    <span className={`meter meter-${size}`} role="img" aria-label={`${percent(rate)} solved`}>
      <span className="meter-fill" style={{ width: percent(rate) }} />
    </span>
  );
}

// What went wrong, as concretely as the data allows: for a wrong answer, the
// actual output most of them printed; otherwise the error kind and its line.
function IssueLine({ task }: { task: LectureReviewTask }) {
  const issue = task.top_issue;
  if (!issue) {
    return task.submitted === 0 ? <p className="issue-line">Nobody submitted this task.</p> : null;
  }
  const ex = issue.example;
  if (ex) {
    return (
      <p className="issue-line">
        <strong>{plural(ex.students, "student")}</strong> printed <code>{ex.stdout || "(nothing)"}</code> for input{" "}
        <code>{ex.stdin.trim() || "(empty)"}</code>, expected <code>{ex.expected_stdout.trim()}</code>
      </p>
    );
  }
  return (
    <p className="issue-line">
      <strong>{plural(issue.students, "student")}</strong>: {issueName(issue.exec_verdict, issue.error_type)}
      {issue.discussion_point && <span className="issue-hint"> {issue.discussion_point}</span>}
    </p>
  );
}

function TaskRow({ task }: { task: LectureReviewTask }) {
  const notSubmitted = task.students - task.submitted;
  return (
    <li className="task-row">
      <div className="task-row-head">
        <span className="task-title">{task.title}</span>
        <a className="text-link" href={`lecturer.html?question_id=${encodeURIComponent(task.question_id)}`}>
          View task
        </a>
      </div>
      {task.solve_rate !== null && (
        <div className="task-meter">
          <Meter rate={task.solve_rate} size="sm" />
          <span className="task-count">
            {task.solved}/{task.students} solved
            {notSubmitted > 0 && <span className="muted"> · {notSubmitted} didn't submit</span>}
          </span>
        </div>
      )}
      <IssueLine task={task} />
    </li>
  );
}

function LectureItem({
  review,
  rank,
  open,
  onToggle,
}: {
  review: LectureReview;
  rank: number;
  open: boolean;
  onToggle: () => void;
}) {
  const panelId = `lecture-panel-${review.lecture_id}`;
  return (
    <li className={open ? "lecture-item is-open" : "lecture-item"}>
      <button className="lecture-toggle" aria-expanded={open} aria-controls={panelId} onClick={onToggle}>
        <span className="lecture-rank">{rank}</span>
        <span className="lecture-main">
          <span className="lecture-name">{review.display_label}</span>
          <span className="lecture-sub">
            {formatDate(review.started_at)} · {plural(review.students, "student")} · {plural(review.tasks.length, "task")}
          </span>
        </span>
        {review.solve_rate !== null && (
          <span className="lecture-score">
            <span className="lecture-pct">{percent(review.solve_rate)}</span>
            <Meter rate={review.solve_rate} />
          </span>
        )}
        <span className="chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="lecture-panel" id={panelId}>
          <ul className="task-list">
            {review.tasks.map((t) => (
              <TaskRow key={t.question_id} task={t} />
            ))}
          </ul>
          <a className="text-link panel-link" href={`lecturer.html?lecture_id=${review.lecture_id}`}>
            Open the full lecture summary &rarr;
          </a>
        </div>
      )}
    </li>
  );
}

interface Topic {
  title: string;
  rate: number;
  lectures: number;
  worst: LectureReviewTask; // its weakest run, for the concrete issue
}

// Same task title across lectures = same topic (the demo and real lectures
// reuse exercises), averaged so a topic that's hard every time stands out.
function topicsFrom(ranked: LectureReview[]): Topic[] {
  const byTitle = new Map<string, LectureReviewTask[]>();
  for (const r of ranked) {
    for (const t of r.tasks) {
      if (t.solve_rate === null) continue;
      byTitle.set(t.title, [...(byTitle.get(t.title) ?? []), t]);
    }
  }
  return [...byTitle.entries()]
    .map(([title, runs]) => ({
      title,
      rate: runs.reduce((sum, t) => sum + (t.solve_rate ?? 0), 0) / runs.length,
      lectures: runs.length,
      worst: runs.reduce((a, b) => ((a.solve_rate ?? 1) <= (b.solve_rate ?? 1) ? a : b)),
    }))
    .sort((a, b) => a.rate - b.rate);
}

function Trend({ ranked }: { ranked: LectureReview[] }) {
  const chronological = [...ranked]
    .sort((a, b) => parseDate(a.started_at).getTime() - parseDate(b.started_at).getTime())
    .slice(-TREND_LECTURES);
  const weakest = ranked[0]?.lecture_id;
  return (
    <div className="trend" role="img" aria-label="Share of tasks solved per lecture, oldest to newest">
      <div className="trend-plot">
        {[0.25, 0.5, 0.75, 1].map((y) => (
          <span key={y} className="trend-grid" style={{ bottom: percent(y) }} />
        ))}
        {[0.5, 1].map((y) => (
          <span key={y} className="trend-grid-label" style={{ bottom: percent(y) }}>
            {percent(y)}
          </span>
        ))}
        {chronological.map((r) => (
          <div
            key={r.lecture_id}
            className="trend-col"
            title={`${r.display_label}: ${percent(r.solve_rate ?? 0)} solved`}
          >
            {r.lecture_id === weakest && <span className="trend-label">{percent(r.solve_rate ?? 0)}</span>}
            <span
              className={r.lecture_id === weakest ? "trend-bar is-weakest" : "trend-bar"}
              style={{ height: percent(r.solve_rate ?? 0) }}
            />
          </div>
        ))}
      </div>
      <div className="trend-axis">
        {chronological.map((r) => (
          <span key={r.lecture_id}>{shortDate(r.started_at)}</span>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [reviews, setReviews] = useState<LectureReview[] | null>(null);
  const [reviewError, setReviewError] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const [history, setHistory] = useState<LectureHistoryRow[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState<number | null>(null);

  function loadReview() {
    fetchLectureReview()
      .then((rows) => {
        setReviews(rows);
        setReviewError(false);
        // Worst lecture open on arrival -- it's what the page is for.
        setOpenId((prev) => prev ?? rows.find((r) => r.enough_data)?.lecture_id ?? null);
      })
      .catch(() => setReviewError(true));
  }

  function loadHistory(includeArchived: boolean) {
    fetchLectureHistory(includeArchived)
      .then(setHistory)
      .catch(() => {
        // Backend not reachable -- leave the last-known list in place.
      });
  }

  useEffect(() => {
    loadReview();
  }, []);

  useEffect(() => {
    loadHistory(showArchived);
  }, [showArchived]);

  async function handleArchiveToggle(row: LectureHistoryRow) {
    setArchiving(row.id);
    try {
      if (row.archived) await unarchiveLecture(row.id);
      else await archiveLecture(row.id);
      loadHistory(showArchived);
      loadReview(); // archived lectures drop out of the ranking too
    } finally {
      setArchiving(null);
    }
  }

  const ranked = (reviews ?? []).filter((r) => r.enough_data && r.solve_rate !== null);
  const unranked = (reviews ?? []).length - ranked.length;
  const topics = topicsFrom(ranked);
  const average = ranked.length ? ranked.reduce((s, r) => s + (r.solve_rate ?? 0), 0) / ranked.length : null;

  return (
    <>
      <NavBar />
      <header>
        <h1>Lecture history</h1>
        <p>Which past lectures and topics are worth going back over in a review lecture.</p>
      </header>
      <main>
        {reviewError && (
          <div className="card notice">Could not load the ranking. Check that the backend is running.</div>
        )}
        {reviews && ranked.length === 0 && !reviewError && (
          <div className="card notice">
            No finished lectures with at least {MIN_STUDENTS_FOR_REVIEW} students yet. Run one and it will show up
            here.
          </div>
        )}

        {ranked.length > 0 && (
          <>
            <section className="stats" aria-label="Overview">
              <div className="stat">
                <span className="stat-label">Weakest lecture</span>
                <span className="stat-value">{percent(ranked[0].solve_rate ?? 0)}</span>
                <span className="stat-sub">{ranked[0].display_label}</span>
              </div>
              {topics[0] && (
                <div className="stat">
                  <span className="stat-label">Hardest topic</span>
                  <span className="stat-value stat-value-text">{topics[0].title}</span>
                  <span className="stat-sub">
                    {percent(topics[0].rate)} solved on average · {plural(topics[0].lectures, "lecture")}
                  </span>
                </div>
              )}
              {average !== null && (
                <div className="stat">
                  <span className="stat-label">Average across lectures</span>
                  <span className="stat-value">{percent(average)}</span>
                  <span className="stat-sub">
                    {plural(ranked.length, "lecture")} compared
                  </span>
                </div>
              )}
            </section>

            <div className="card trend-card">
              <div className="card-head">
                <h2>Solved per lecture</h2>
                <span className="card-caption">Oldest to newest · hover a bar for details</span>
              </div>
              <Trend ranked={ranked} />
            </div>

            <div className="layout">
              <div className="card">
                <div className="card-head">
                  <h2>Lectures, worst first</h2>
                </div>
                <p className="card-intro">
                  Share of students who solved each task, averaged per lecture. Students who took part but didn't
                  submit a task count as not solving it.
                </p>
                <ol className="lecture-list">
                  {ranked.map((r, i) => (
                    <LectureItem
                      key={r.lecture_id}
                      review={r}
                      rank={i + 1}
                      open={openId === r.lecture_id}
                      onToggle={() => setOpenId((id) => (id === r.lecture_id ? null : r.lecture_id))}
                    />
                  ))}
                </ol>
                {unranked > 0 && (
                  <p className="footnote">
                    {plural(unranked, "lecture")} with fewer than {MIN_STUDENTS_FOR_REVIEW} students{" "}
                    {unranked === 1 ? "isn't" : "aren't"} ranked: too few to compare fairly.
                  </p>
                )}
              </div>

              <div className="card">
                <div className="card-head">
                  <h2>Topics to revisit</h2>
                </div>
                <p className="card-intro">The same task across lectures, hardest first.</p>
                <ol className="topic-list">
                  {topics.slice(0, TOPICS_SHOWN).map((t) => (
                    <li key={t.title} className="topic">
                      <div className="topic-head">
                        <span className="task-title">{t.title}</span>
                        <span className="topic-pct">{percent(t.rate)}</span>
                      </div>
                      <Meter rate={t.rate} size="sm" />
                      <span className="topic-sub">{plural(t.lectures, "lecture")}</span>
                      <IssueLine task={t.worst} />
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </>
        )}

        <div className="card" id="history-card">
          <div className="card-head">
            <h2>All lectures</h2>
            <label className="archived-toggle">
              <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Show archived
            </label>
          </div>
          {history && history.length === 0 && <p className="card-intro">No lectures yet.</p>}
          {history && history.length > 0 && (
            <ul id="lecture-list">
              {history.map((row) => (
                <li key={row.id} className={row.archived ? "archived" : ""}>
                  <a className="lecture-row-link" href={`lecturer.html?lecture_id=${row.id}`}>
                    <span className="lecture-name">{row.display_label}</span>
                    <span className="lecture-sub">
                      {formatDate(row.started_at)} · {plural(row.task_count, "task")} · {statsSnapshot(row)}
                    </span>
                  </a>
                  <button
                    className="secondary archive-btn"
                    disabled={archiving === row.id}
                    onClick={() => handleArchiveToggle(row)}
                  >
                    {row.archived ? "Unarchive" : "Archive"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </>
  );
}
