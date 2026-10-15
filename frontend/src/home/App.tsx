import { useEffect, useState } from "react";
import type { ActiveLectureResponse, LectureTotals } from "../shared/types";
import { createLecture, deleteLecture, fetchActiveLecture, fetchLectureTotals } from "../shared/api";
import { activeLectureAction } from "../shared/lectureNav";
import { NavBar } from "../shared/NavBar";
import { ConfirmDialog } from "../shared/ConfirmDialog";

export default function App() {
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);
  const [activeLoading, setActiveLoading] = useState(true);
  const [label, setLabel] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

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

  useEffect(() => {
    loadActive();
    fetchLectureTotals()
      .then(setTotals)
      .catch(() => {
        // Optional stats line -- fine to just not show it.
      });
  }, []);

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

  const hasActive = !activeLoading && active?.lecture != null;

  return (
    <>
      <NavBar />
      <header className="hero">
        <h1>Interactive Lecture</h1>
        <p>Start a new lecture or resume one in progress.</p>
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

        {/* Past lectures live on their own page now (nav bar "History"). */}
        <div id="totals-line" className="fade-in-up" style={{ animationDelay: "0.08s" }}>
          {totals && (
            <>
              {totals.lectures_run} lecture{totals.lectures_run === 1 ? "" : "s"} run, {totals.total_submissions}{" "}
              total submission{totals.total_submissions === 1 ? "" : "s"} &middot;{" "}
            </>
          )}
          <a href="history.html">Lecture history &rarr;</a>
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
