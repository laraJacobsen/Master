import { useCallback, useState } from "react";
import type { StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import { LABEL, activityText, activityTitle, attemptTitle, buildTracks, isSolved, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { SubmissionDetail } from "./ExampleBlock";
import { ActivityDot } from "./ClassProgress";
import { SCORE_LINE, TILE_HOVER, TILE_TONE, VERDICT_BORDER } from "../shared/verdictStyles";
import { Drawer } from "../shared/Drawer";
import { Badge } from "../shared/ui";
import type { Tone } from "../shared/ui";
import { cx } from "../shared/cx";

// The live dashboard's per-student view: one tile per student, coloured by
// their best result so far and ordered worst first, so the students worth a
// look cluster at the top. A thin line in each tile is their best share of
// tests passed. Clicking a tile opens their attempts and full code in a side
// drawer -- code can be long, and the page shouldn't jump around for it.

// Names are hidden by default (numbered instead) -- this dashboard can end
// up on a shared screen. Remembered per browser so it doesn't reset every task.
const NAMES_KEY = "lecturer.studentGrid.names";

type Group = Verdict | "none";

// Worst first: the students worth a look sit at the top.
const GROUP_ORDER: Group[] = ["error", "incorrect", "partially_correct", "none", "correct"];

const VERDICT_TONE: Record<Verdict, Tone> = {
  correct: "success",
  partially_correct: "warning",
  incorrect: "danger",
  error: "danger",
};

function readShowNames(): boolean {
  try {
    return window.localStorage.getItem(NAMES_KEY) === "1";
  } catch {
    return false;
  }
}

function groupOf(t: StudentTrack): Group {
  return t.best ? verdictOf(t.best) : "none";
}

export interface StudentGridProps {
  subs: SubmissionRow[];
  // Null once the task isn't running -- activity would read "away" for everyone.
  activity: StudentActivity[] | null;
}

export function StudentGrid({ subs, activity }: StudentGridProps) {
  const [showNames, setShowNames] = useState(readShowNames);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null);
  const close = useCallback(() => setSelected(null), []);

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

  // Alphabetical numbering, so a student's number (names hidden) only
  // changes when someone new joins, never when they move between groups.
  const tracks = buildTracks(subs, activity);
  const number = new Map(tracks.map((t, i) => [t.name, String(i + 1).padStart(2, "0")]));
  const label = (t: StudentTrack) => (showNames ? t.name : `#${number.get(t.name)}`);
  const ordered = GROUP_ORDER.flatMap((g) => tracks.filter((t) => groupOf(t) === g));
  const track = tracks.find((t) => t.name === selected) ?? null;
  const shownSub = track
    ? (track.attempts.find((s) => s.id === selectedAttempt) ?? track.attempts[track.attempts.length - 1] ?? null)
    : null;

  function select(name: string) {
    setSelected((prev) => (prev === name ? null : name));
    setSelectedAttempt(null);
  }

  return (
    <section aria-label="Students">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Class</h2>
        <span className="font-mono text-xs text-zinc-400">
          {tracks.length} · {subs.length} attempts
        </span>
        {tracks.length > 0 && (
          <button
            type="button"
            aria-pressed={showNames}
            onClick={toggleNames}
            className="ml-auto rounded-md px-2 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          >
            {showNames ? "Hide names" : "Show names"}
          </button>
        )}
      </div>

      {tracks.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 px-6 py-12 text-center text-sm text-zinc-400">
          Students appear here as they join.
        </div>
      ) : (
        <ul
          className={cx(
            "grid gap-1.5",
            showNames
              ? "grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))]"
              : "grid-cols-[repeat(auto-fill,minmax(3.25rem,1fr))]",
          )}
        >
          {ordered.map((t) => {
            const group = groupOf(t);
            const a = activity && !isSolved(t) ? t.activity : null;
            // "Away" is most students most of the time -- the class bar counts
            // them; a mark on every tile would just be noise.
            const dot = a && a.status !== "away" ? a : null;
            const share = t.best && t.best.tests_total ? t.best.tests_passed / t.best.tests_total : 0;
            return (
              <li key={t.name}>
                <button
                  type="button"
                  aria-pressed={selected === t.name}
                  onClick={() => select(t.name)}
                  title={
                    `${label(t)}: ` +
                    (t.best
                      ? `best ${LABEL[verdictOf(t.best)]}, ${t.best.tests_passed}/${t.best.tests_total} tests, ${t.attempts.length} attempt(s)`
                      : "no attempts yet") +
                    (a ? ` · ${activityTitle(a)}` : "")
                  }
                  className={cx(
                    "relative flex h-12 w-full flex-col justify-between rounded-md border px-2 pt-1.5 pb-2 text-left transition-[border-color,box-shadow]",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
                    TILE_TONE[group],
                    TILE_HOVER[group],
                    selected === t.name && "ring-2 ring-zinc-900 ring-offset-1",
                  )}
                >
                  <span className={cx("truncate pr-2.5 text-xs leading-tight", showNames ? "font-medium" : "font-mono")}>
                    {label(t)}
                  </span>
                  {t.best && (
                    <span className="block h-[3px] overflow-hidden rounded-sm bg-black/10" aria-hidden="true">
                      <span
                        className={cx("block h-full rounded-sm", SCORE_LINE[verdictOf(t.best)])}
                        style={{ width: `${Math.max(share, 0.04) * 100}%` }}
                      />
                    </span>
                  )}
                  {dot && (
                    <span className="absolute top-1.5 right-1.5 flex" role="img" aria-label={activityText(dot)}>
                      <ActivityDot status={dot.status} />
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <Drawer
        open={track != null}
        onClose={close}
        title={track ? label(track) : ""}
        meta={
          track && (
            <>
              {track.best ? (
                <Badge tone={VERDICT_TONE[verdictOf(track.best)]} dot>
                  Best: {LABEL[verdictOf(track.best)]} · {track.best.tests_passed}/{track.best.tests_total}
                </Badge>
              ) : (
                <Badge>No attempts yet</Badge>
              )}
              <span>
                {track.attempts.length} attempt{track.attempts.length === 1 ? "" : "s"}
              </span>
              {activity && track.activity && !isSolved(track) && <span>{activityTitle(track.activity)}</span>}
            </>
          )
        }
        toolbar={
          track &&
          track.attempts.length > 1 && (
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Attempts">
              <span className="mr-1 text-xs text-zinc-500">Attempt</span>
              {track.attempts.map((s) => {
                const pressed = shownSub?.id === s.id;
                return (
                  <button
                    type="button"
                    key={s.id}
                    aria-pressed={pressed}
                    title={attemptTitle(s)}
                    onClick={() => setSelectedAttempt(s.id)}
                    className={cx(
                      "min-w-8 rounded-md border border-b-[3px] px-2 py-1 font-mono text-xs font-semibold transition-colors",
                      "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
                      VERDICT_BORDER[verdictOf(s)],
                      pressed
                        ? "border-x-zinc-900 border-t-zinc-900 bg-zinc-900 text-white"
                        : "border-x-zinc-200 border-t-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100",
                    )}
                  >
                    {s.attempt_number}
                  </button>
                );
              })}
            </div>
          )
        }
      >
        {shownSub ? (
          <>
            <p className="mb-3 text-xs text-zinc-500">{attemptTitle(shownSub)}</p>
            <SubmissionDetail sub={shownSub} clamp={false} />
          </>
        ) : (
          <p className="text-sm text-zinc-500">Nothing submitted yet.</p>
        )}
      </Drawer>
    </section>
  );
}
