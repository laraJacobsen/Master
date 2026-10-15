import { useEffect, useState } from "react";
import type { LectureHistoryRow, LectureReview, LectureReviewTask } from "../shared/types";
import { archiveLecture, fetchLectureHistory, fetchLectureReview, unarchiveLecture } from "../shared/api";
import { NavBar } from "../shared/NavBar";

// Lecture history, reachable from the nav bar on every lecturer page. Two
// cards: "Needs revisiting" ranks finished lectures by how many students
// solved their tasks, worst first, so the lecturer can pick what a review
// lecture should go back over (see aggregation.lecture_review()); "All
// lectures" is the plain list that used to sit on the home page.

// The ranking starts short so the worst few stand out; the rest are a click away.
const REVIEW_SHOWN = 5;

// Mirrors MIN_STUDENTS_FOR_REVIEW in backend/aggregation.py -- only used to
// explain why some lectures aren't ranked (the backend decides which).
const MIN_STUDENTS_FOR_REVIEW = 3;

function formatDate(isoLike: string): string {
  // Server timestamps are "YYYY-MM-DD HH:MM:SS" UTC, no offset marker --
  // append one so the Date parses as UTC rather than local time.
  const d = new Date(isoLike.replace(" ", "T") + "Z");
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

// A short, aggregate-only snapshot -- total distinct-student submissions and
// a correct-count, never a per-student breakdown (see the product decision
// against any per-student identification on this dashboard).
function statsSnapshot(row: LectureHistoryRow): string {
  if (row.submitted_total === 0) return "No submissions.";
  const correct = row.verdict_counts.correct || 0;
  return `${row.submitted_total} submission${row.submitted_total === 1 ? "" : "s"}, ${correct} correct`;
}

// Same naming as the live dashboard's issue tags.
function issueName(execVerdict: string | null, errorType: string | null): string {
  if (execVerdict === "rejected") return "Rejected before running";
  const verdict = (execVerdict || "unknown").replace(/_/g, " ");
  const label = verdict.charAt(0).toUpperCase() + verdict.slice(1);
  return errorType && errorType !== "none" ? `${label} · ${errorType}` : label;
}

function TaskLine({ task }: { task: LectureReviewTask }) {
  const notSubmitted = task.students - task.submitted;
  const issue = task.top_issue;
  return (
    <li className="review-task">
      <div className="review-task-head">
        <span className="review-task-title">{task.title}</span>
        <span className="review-task-count">
          {task.solved} of {task.students} solved
          {notSubmitted > 0 && ` · ${notSubmitted} didn't submit`}
        </span>
        <a className="drilldown-link" href={`lecturer.html?question_id=${encodeURIComponent(task.question_id)}`}>
          View task &rarr;
        </a>
      </div>
      {issue ? (
        <div className="review-issue">
          Most common issue: <strong>{issueName(issue.exec_verdict, issue.error_type)}</strong> ({issue.students}{" "}
          student{issue.students === 1 ? "" : "s"})
          {issue.discussion_point && <div className="review-issue-point">{issue.discussion_point}</div>}
        </div>
      ) : (
        task.submitted === 0 && <div className="review-issue">Nobody submitted this task.</div>
      )}
    </li>
  );
}

function ReviewRow({ review }: { review: LectureReview }) {
  // The two weakest tasks are the review lecture's starting point; a task
  // everyone solved isn't worth listing here.
  const weakest = review.tasks.filter((t) => t.solve_rate !== null && t.solve_rate < 1).slice(0, 2);
  return (
    <li className="review-row">
      <div className="review-head">
        <a className="review-title" href={`lecturer.html?lecture_id=${review.lecture_id}`}>
          {review.display_label}
        </a>
        <span className="review-meta">
          {formatDate(review.started_at)} · {review.students} students
        </span>
      </div>
      {review.solve_rate !== null && (
        <div className="review-meter">
          <div
            className="review-meter-track"
            role="img"
            aria-label={`${percent(review.solve_rate)} of tasks solved on average`}
          >
            <div className="review-meter-fill" style={{ width: percent(review.solve_rate) }} />
          </div>
          <span className="review-meter-value">{percent(review.solve_rate)} solved</span>
        </div>
      )}
      {weakest.length > 0 ? (
        <ul className="review-tasks">
          {weakest.map((t) => (
            <TaskLine key={t.question_id} task={t} />
          ))}
        </ul>
      ) : (
        <div className="review-issue">Every task was solved by everyone.</div>
      )}
    </li>
  );
}

export default function App() {
  const [reviews, setReviews] = useState<LectureReview[] | null>(null);
  const [reviewError, setReviewError] = useState(false);
  const [showAllReviews, setShowAllReviews] = useState(false);

  const [history, setHistory] = useState<LectureHistoryRow[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState<number | null>(null);

  function loadHistory(includeArchived: boolean) {
    fetchLectureHistory(includeArchived)
      .then(setHistory)
      .catch(() => {
        // Backend not reachable -- leave the last-known list in place.
      });
  }

  useEffect(() => {
    fetchLectureReview()
      .then(setReviews)
      .catch(() => setReviewError(true));
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
      // Archived lectures drop out of the ranking too.
      fetchLectureReview().then(setReviews).catch(() => setReviewError(true));
    } finally {
      setArchiving(null);
    }
  }

  const ranked = (reviews ?? []).filter((r) => r.enough_data);
  const unranked = (reviews ?? []).length - ranked.length;
  const shownReviews = showAllReviews ? ranked : ranked.slice(0, REVIEW_SHOWN);

  return (
    <>
      <NavBar />
      <header>
        <h1>Lecture history</h1>
        <p>Past lectures, and which ones are worth revisiting.</p>
      </header>
      <main>
        <div className="card" id="review-card">
          <h2>Needs revisiting</h2>
          <p className="muted-note">
            Finished lectures ranked by the share of students who solved each task, worst first. A student who
            took part but didn't submit a task counts as not solving it. The weakest tasks and their most
            common issue are a starting point for a review lecture.
          </p>
          {reviewError && <div className="form-error">Could not load the ranking.</div>}
          {reviews && ranked.length === 0 && (
            <div className="muted-note">No finished lectures with enough students to compare yet.</div>
          )}
          {ranked.length > 0 && (
            <ol className="review-list">
              {shownReviews.map((r) => (
                <ReviewRow key={r.lecture_id} review={r} />
              ))}
            </ol>
          )}
          {ranked.length > REVIEW_SHOWN && (
            <button className="secondary show-all-btn" onClick={() => setShowAllReviews((v) => !v)}>
              {showAllReviews ? "Show fewer" : `Show all ${ranked.length}`}
            </button>
          )}
          {unranked > 0 && (
            <div className="review-footnote">
              {unranked} lecture{unranked === 1 ? "" : "s"} with fewer than {MIN_STUDENTS_FOR_REVIEW} students{" "}
              {unranked === 1 ? "isn't" : "aren't"} ranked: too few to compare fairly.
            </div>
          )}
        </div>

        <div className="card" id="history-card">
          <div className="history-header">
            <h2>All lectures</h2>
            <label className="archived-toggle">
              <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Show archived
            </label>
          </div>
          {history && history.length === 0 && <div className="muted-note">No lectures yet.</div>}
          {history && history.length > 0 && (
            <ul id="lecture-list">
              {history.map((row) => (
                <li key={row.id} className={row.archived ? "archived" : ""}>
                  <a className="lecture-row-link" href={`lecturer.html?lecture_id=${row.id}`}>
                    <div className="lecture-row-main">
                      <div className="lecture-title">{row.display_label}</div>
                      <div className="lecture-meta">
                        {formatDate(row.started_at)} &middot; {row.task_count} task
                        {row.task_count === 1 ? "" : "s"} &middot; {statsSnapshot(row)}
                      </div>
                    </div>
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
