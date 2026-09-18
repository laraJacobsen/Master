import { useEffect, useState } from "react";
import type { ActiveLectureResponse, LectureHistoryRow, LectureTotals } from "../shared/types";
import {
  archiveLecture,
  createLecture,
  fetchActiveLecture,
  fetchLectureHistory,
  fetchLectureTotals,
  unarchiveLecture,
} from "../shared/api";

// A short, aggregate-only snapshot -- total distinct-student submissions and
// a correct-count, never a per-student breakdown (see the product decision
// against any per-student identification on this dashboard).
function statsSnapshot(row: LectureHistoryRow): string {
  if (row.submitted_total === 0) return "No submissions.";
  const correct = row.verdict_counts.correct || 0;
  return `${row.submitted_total} submission${row.submitted_total === 1 ? "" : "s"} -- ${correct} correct`;
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

  function handleResume() {
    if (active?.live_question_id) {
      window.location.href = `lecturer.html?question_id=${encodeURIComponent(active.live_question_id)}`;
    } else if (active?.lecture?.lobby_opened_at) {
      // Lobby's open but nothing's live yet (right after "Open lobby", or
      // between "Next task" clicks with no drafts left) -- back to the lobby,
      // not setup, since students may already be sitting in it.
      window.location.href = `lecturer.html?lobby=${active.lecture.id}`;
    } else {
      // Lecture exists but the lobby was never opened -- still prepping.
      window.location.href = "setup.html";
    }
  }

  function resumeLabel(): string {
    if (active?.live_question_id) return "Resume live lecture";
    if (active?.lecture?.lobby_opened_at) return "Back to lobby";
    return "Continue setup";
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
      <header>
        <h1>Interactive Lecture -- Home</h1>
        <p>Start a new lecture, resume one in progress, or browse past ones.</p>
      </header>
      <main>
        <div className="card" id="start-card">
          {activeLoading ? (
            <div className="muted-note">Loading...</div>
          ) : hasActive ? (
            <>
              <h2>Lecture in progress</h2>
              <p className="muted-note">
                {active!.lecture!.display_label} is currently active -- this backend supports one lecture at a
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
                  Still being prepared -- nothing is joinable yet. Add your questions on setup, then open the
                  lobby when you're ready for students to join.
                </p>
              )}
              <button onClick={handleResume}>{resumeLabel()}</button>
            </>
          ) : (
            <>
              <h2>Start a new lecture</h2>
              <label htmlFor="f-label">
                Label <span className="hint">optional -- defaults to today's date if left blank</span>
              </label>
              <input
                type="text"
                id="f-label"
                placeholder="e.g. Week 3 -- Recursion"
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
          <div id="totals-line">
            {totals.lectures_run} lecture{totals.lectures_run === 1 ? "" : "s"} run -- {totals.total_submissions}{" "}
            total submission{totals.total_submissions === 1 ? "" : "s"}
          </div>
        )}

        <div className="card" id="history-card">
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
            <div className="muted-note">No lectures yet -- start one above.</div>
          )}
          {history && history.length > 0 && (
            <ul id="lecture-list">
              {history.map((row) => (
                <li key={row.id} className={row.archived ? "archived" : ""}>
                  <a className="lecture-row-link" href={`lecturer.html?lecture_id=${row.id}`}>
                    <div className="lecture-row-main">
                      <div className="lecture-title">{row.display_label}</div>
                      <div className="lecture-meta">
                        {formatDate(row.started_at)} -- {row.task_count} task{row.task_count === 1 ? "" : "s"}
                        {" -- "}
                        {statsSnapshot(row)}
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
