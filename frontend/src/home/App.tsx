import { useEffect, useState } from "react";
import type { ActiveLectureResponse, LectureHistoryRow, LectureTotals } from "../shared/types";
import {
  archiveLecture,
  createLecture,
  deleteLecture,
  fetchActiveLecture,
  fetchLectureHistory,
  fetchLectureTotals,
  unarchiveLecture,
} from "../shared/api";
import { activeLectureAction } from "../shared/lectureNav";
import { NavBar } from "../shared/NavBar";
import { ConfirmDialog } from "../shared/ConfirmDialog";

// A short, aggregate-only snapshot -- total distinct-student submissions and
// a correct-count, never a per-student breakdown (see the product decision
// against any per-student identification on this dashboard).
function statsSnapshot(row: LectureHistoryRow): string {
  if (row.submitted_total === 0) return "No submissions.";
  const correct = row.verdict_counts.correct || 0;
  return `${row.submitted_total} submission${row.submitted_total === 1 ? "" : "s"}, ${correct} correct`;
}

function formatDate(isoLike: string): string {
  // Server timestamps are "YYYY-MM-DD HH:MM:SS" UTC, no offset marker --
  // append one so the Date parses as UTC rather than local time.
  const d = new Date(isoLike.replace(" ", "T") + "Z");
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function App() {
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);
  const [activeLoading, setActiveLoading] = useState(true);
  const [label, setLabel] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [history, setHistory] = useState<LectureHistoryRow[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState<number | null>(null);

  const [totals, setTotals] = useState<LectureTotals | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  function loadActive() {
    setActiveLoading(true);
    fetchActiveLecture()
      .then(setActive)
      .catch(() => setActive({ lecture: null, live_question_id: null }))
      .finally(() => setActiveLoading(false));
  }

  function loadHistory(includeArchived: boolean) {
    fetchLectureHistory(includeArchived)
      .then(setHistory)
      .catch(() => {
        // Backend not reachable -- leave the last-known list in place.
      });
  }

  useEffect(() => {
    loadActive();
    loadHistory(showArchived);
    fetchLectureTotals()
      .then(setTotals)
      .catch(() => {
        // Optional stats line -- fine to just not show it.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadHistory(showArchived);
  }, [showArchived]);

  async function handleNewLecture() {
    setStarting(true);
    setStartError(null);
    try {
      await createLecture(label.trim() || null);
      window.location.href = "setup.html";
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Could not start a new lecture.");
      loadActive(); // someone else may have just started one -- pick up "Resume" instead
      setStarting(false);
    }
  }

  // Same logic NavBar's own shortcut uses -- kept in one place
  // (shared/lectureNav.ts) so the two can't drift apart.
  function handleResume() {
    window.location.href = activeLectureAction(active).href;
  }

  // Only ever offered before anything's started (see the JSX below) --
  // once a question's gone live there's real history, and the backend
  // itself refuses the delete at that point anyway (see
  // api_lecturer_delete_lecture in main.py).
  async function confirmDeleteLecture() {
    setConfirmDeleteOpen(false);
    if (!active?.lecture) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteLecture(active.lecture.id);
      loadActive();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Could not delete this lecture.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleArchiveToggle(row: LectureHistoryRow) {
    setArchiving(row.id);
    try {
      if (row.archived) await unarchiveLecture(row.id);
      else await archiveLecture(row.id);
      loadHistory(showArchived);
    } finally {
      setArchiving(null);
    }
  }

  const hasActive = !activeLoading && active?.lecture != null;

  return (
    <>
      <NavBar />
      <header className="hero">
        <h1>Interactive Lecture</h1>
        <p>Start a new lecture, resume one in progress, or browse past ones.</p>
      </header>
      <main>
        <div className="card fade-in-up" id="start-card">
          {activeLoading ? (
            <div className="muted-note">Loading...</div>
          ) : hasActive ? (
            <>
              <h2>Lecture in progress</h2>
              <p className="muted-note">
                {active!.lecture!.display_label} is currently active. This backend supports one lecture at a
                time, so finish it before starting another.
              </p>
              {active!.lecture!.lobby_opened_at ? (
                active!.lecture!.join_code && (
                  <div id="join-code-display" className="join-code-display">
                    <div className="join-code-label">Join code</div>
                    <div className="join-code-value">{active!.lecture!.join_code}</div>
                    <div className="join-code-hint">Students enter this on the student page to join.</div>
                  </div>
                )
              ) : (
                <p className="muted-note">
                  Still being prepared. Nothing is joinable yet, so add your questions on setup, then open the
                  lobby when you're ready for students to join.
                </p>
              )}
              <button onClick={handleResume}>{activeLectureAction(active).label}</button>
              {!active!.live_question_id && (
                <button className="danger" onClick={() => setConfirmDeleteOpen(true)} disabled={deleting}>
                  {deleting ? "Deleting..." : "Delete lecture"}
                </button>
              )}
              {deleteError && <div className="form-error">{deleteError}</div>}
            </>
          ) : (
            <>
              <h2>Start a new lecture</h2>
              <label htmlFor="f-label">
                Label <span className="hint">(optional, defaults to today's date if left blank)</span>
              </label>
              <input
                type="text"
                id="f-label"
                placeholder="e.g. Week 3: Recursion"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
              <button onClick={handleNewLecture} disabled={starting}>
                {starting ? "Starting..." : "New lecture"}
              </button>
              {startError && <div className="form-error">{startError}</div>}
            </>
          )}
        </div>

        {totals && (
          <div id="totals-line" className="fade-in-up" style={{ animationDelay: "0.08s" }}>
            {totals.lectures_run} lecture{totals.lectures_run === 1 ? "" : "s"} run, {totals.total_submissions}{" "}
            total submission{totals.total_submissions === 1 ? "" : "s"}
          </div>
        )}

        <div className="card fade-in-up" id="history-card" style={{ animationDelay: "0.15s" }}>
          <div className="history-header">
            <h2>Lecture history</h2>
            <label className="archived-toggle">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
              />
              Show archived
            </label>
          </div>
          {history && history.length === 0 && (
            <div className="muted-note">No lectures yet. Start one above.</div>
          )}
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
      <ConfirmDialog
        open={confirmDeleteOpen}
        title="Delete lecture?"
        message={`Delete "${active?.lecture?.display_label ?? ""}"? This can't be undone.`}
        onConfirm={confirmDeleteLecture}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </>
  );
}
