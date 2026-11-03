import { useState } from "react";
import type { StudentActivity, SubmissionRow } from "../shared/types";
import {
  LABEL,
  RANK,
  activityText,
  activityTitle,
  attemptTitle,
  buildTracks,
  isSolved,
  verdictOf,
} from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { SubmissionDetail } from "./ExampleBlock";

// The live dashboard's per-student view: one tile per student, coloured by
// their best result, with a square per attempt -- replaces the old
// one-row-per-attempt submissions table, which grew without bound on a long
// task and said the same thing in text. Clicking a tile opens that student's
// attempts and code underneath the grid.

// Tiles are cut to their latest squares so a busy student can't widen theirs.
const MAX_SQUARES = 8;

// Names are hidden by default (anonymous tiles) -- this dashboard can end up
// on a shared screen. Remembered per browser so it doesn't reset every task.
const NAMES_KEY = "lecturer.studentGrid.names";

function readShowNames(): boolean {
  try {
    return window.localStorage.getItem(NAMES_KEY) === "1";
  } catch {
    return false;
  }
}

// Worst first: not submitted, error, incorrect, partial, then correct -- the
// students worth a look sit at the top. Alphabetical within a result, so a
// tile only moves when that student's best result changes.
function rank(t: StudentTrack): number {
  return t.best ? RANK[verdictOf(t.best)] : -1;
}

export function StudentGrid({
  subs,
  activity,
}: {
  subs: SubmissionRow[];
  // Null once the task isn't running -- activity would read "away" for everyone.
  activity: StudentActivity[] | null;
}) {
  const [showNames, setShowNames] = useState(readShowNames);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null);

  function toggleNames() {
    setShowNames((prev) => {
      try {
        window.localStorage.setItem(NAMES_KEY, prev ? "0" : "1");
      } catch {
        // Storage blocked -- the toggle still works for this page view.
      }
      return !prev;
    });
  }

  const tracks = buildTracks(subs, activity).sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  const attempts = subs.length;
  const track = tracks.find((t) => t.name === selected) ?? null;
  const shownSub = track
    ? track.attempts.find((s) => s.id === selectedAttempt) ?? track.attempts[track.attempts.length - 1] ?? null
    : null;

  function select(name: string) {
    setSelected((prev) => (prev === name ? null : name));
    setSelectedAttempt(null);
  }

  return (
    <div className="card" id="students-card">
      <div className="card-head">
        <h2>
          Students
          <span className="card-head-count">
            {tracks.length} · {attempts} attempt{attempts === 1 ? "" : "s"}
          </span>
        </h2>
        {tracks.length > 0 && (
          <button className="view-example-btn" aria-pressed={showNames} onClick={toggleNames}>
            {showNames ? "Hide names" : "Show names"}
          </button>
        )}
      </div>
      {tracks.length === 0 ? (
        <div className="card-empty">No one yet.</div>
      ) : (
        <ul className="sg-grid">
          {tracks.map((t, i) => {
            const verdict = t.best ? verdictOf(t.best) : "none";
            const a = activity && !isSolved(t) ? t.activity : null;
            const hidden = Math.max(0, t.attempts.length - MAX_SQUARES);
            const label = showNames ? t.name : `Student ${i + 1}`;
            return (
              <li key={t.name}>
                <button
                  className={`sg-tile sg-${verdict}`}
                  aria-pressed={selected === t.name}
                  onClick={() => select(t.name)}
                  title={
                    `${label}: ` +
                    (t.best ? `best ${LABEL[verdictOf(t.best)]}, ${t.attempts.length} attempt(s)` : "no attempts yet") +
                    (a ? ` · ${activityTitle(a)}` : "")
                  }
                >
                  <span className="sg-top">
                    <span className="sg-score">{t.best ? `${t.best.tests_passed}/${t.best.tests_total}` : "–"}</span>
                    {a && <span className={`sg-act cp-act-${a.status}`} aria-label={activityText(a)} />}
                  </span>
                  {showNames && <span className="sg-name">{t.name}</span>}
                  <span className="sg-strip" aria-hidden="true">
                    {hidden > 0 && <span className="cp-more">+{hidden}</span>}
                    {t.attempts.slice(hidden).map((s) => (
                      <span key={s.id} className={`cp-sq cp-${verdictOf(s)}`} />
                    ))}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {track && (
        <div className="sg-detail">
          <div className="sg-detail-head">
            <strong>{showNames ? track.name : "This student"}</strong>
            {track.attempts.length > 0 && (
              <span className="sg-attempts" role="group" aria-label="Attempts">
                {track.attempts.map((s) => (
                  <button
                    key={s.id}
                    className={`sg-attempt cp-${verdictOf(s)}`}
                    aria-pressed={shownSub?.id === s.id}
                    title={attemptTitle(s)}
                    onClick={() => setSelectedAttempt(s.id)}
                  >
                    {s.attempt_number}
                  </button>
                ))}
              </span>
            )}
            <button className="sg-close" aria-label="Close" onClick={() => setSelected(null)}>
              ×
            </button>
          </div>
          {shownSub ? <SubmissionDetail sub={shownSub} /> : <div className="card-empty">No attempts yet.</div>}
        </div>
      )}
    </div>
  );
}
