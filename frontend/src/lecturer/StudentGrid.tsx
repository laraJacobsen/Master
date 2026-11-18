import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import type { StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import { LABEL, activityText, activityTitle, attemptTitle, buildTracks, isSolved, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { SubmissionDetail } from "./ExampleBlock";
import { ActivityDot } from "./ClassProgress";
import { SCORE_LINE, TILE_HOVER, TILE_TONE, VERDICT_BORDER } from "../shared/verdictStyles";
import { Drawer } from "../shared/Drawer";
import { readShowNames, saveShowNames, studentLabeler } from "./studentNames";
import { Badge } from "../shared/ui";
import type { Tone } from "../shared/ui";
import { cx } from "../shared/cx";

// The live dashboard's per-student view: one tile per student, coloured by
// their best result so far and ordered worst first, so the students worth a
// look cluster at the top. A thin line in each tile is their best share of
// tests passed. Clicking a tile opens their attempts and full code in a side
// drawer -- code can be long, and the page shouldn't jump around for it.


export type Group = Verdict | "none";

// Worst first: the students worth a look sit at the top.
const GROUP_ORDER: Group[] = ["error", "incorrect", "partially_correct", "none", "correct"];

const VERDICT_TONE: Record<Verdict, Tone> = {
  correct: "success",
  partially_correct: "warning",
  incorrect: "danger",
  error: "danger",
};

function groupOf(t: StudentTrack): Group {
  return t.best ? verdictOf(t.best) : "none";
}

// "Add to queue" for a single attempt in the code drawer: puts it (no name) in
// the screen queue for the students' waiting screens and the projector -- any
// verdict, so a correct solution can go up too. The projector steps through it.
/** Students in the order a grid shows them: worst outcome first, alphabetical within. */
export function orderStudents(tracks: StudentTrack[], only?: Set<string>): StudentTrack[] {
  return GROUP_ORDER.flatMap((g) => tracks.filter((t) => groupOf(t) === g)).filter((t) => !only || only.has(t.name));
}

export interface ShowCodeControl {
  shownIds: Set<number>;
  busyId: number | null;
  taskRunning: boolean;
  onToggle: (sub: SubmissionRow) => void;
}

export interface StudentGridProps {
  subs: SubmissionRow[];
  // Null once the task isn't running -- activity would read "away" for everyone.
  activity: StudentActivity[] | null;
  // Only these students (numbering still counts the whole class, so a
  // student's number is the same in every grid on the page).
  only?: Set<string>;
  // Controlled names toggle -- the caller owns it and the header is hidden.
  showNames?: boolean;
  showCode?: ShowCodeControl;
  // Controlled selection: the caller owns which student's code is open and
  // renders the StudentDrawer itself. Needed when the grid can unmount under
  // the lecturer (an outcome row empties as students submit) -- the open
  // drawer must outlive it.
  selected?: string | null;
  onSelect?: (name: string) => void;
}

export function StudentGrid({
  subs,
  activity,
  only,
  showNames: showNamesProp,
  showCode,
  selected: selectedProp,
  onSelect,
}: StudentGridProps) {
  const [ownShowNames, setShowNames] = useState(readShowNames);
  const showNames = showNamesProp ?? ownShowNames;
  const bare = showNamesProp !== undefined;
  const [ownSelected, setOwnSelected] = useState<string | null>(null);
  const controlled = onSelect !== undefined;
  const selected = controlled ? (selectedProp ?? null) : ownSelected;
  const close = useCallback(() => setOwnSelected(null), []);

  function toggleNames() {
    setShowNames((prev) => {
      saveShowNames(!prev);
      return !prev;
    });
  }

  // Alphabetical numbering, so a student's number (names hidden) only
  // changes when someone new joins, never when they move between groups.
  const tracks = buildTracks(subs, activity);
  const label = studentLabeler(tracks, showNames);
  const ordered = orderStudents(tracks, only);

  function select(name: string) {
    if (onSelect) onSelect(name);
    else setOwnSelected((prev) => (prev === name ? null : name));
  }

  return (
    <section aria-label="Students">
      {!bare && (
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
            className="ml-auto rounded-md px-2 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            {showNames ? "Hide names" : "Show names"}
          </button>
        )}
      </div>
      )}

      {ordered.length === 0 ? (
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
                <StudentTile
                  label={label(t)}
                  mono={!showNames}
                  verdict={group}
                  share={share}
                  pressed={selected === t.name}
                  onClick={() => select(t.name)}
                  title={
                    `${label(t)}: ` +
                    (t.best
                      ? `best ${LABEL[verdictOf(t.best)]}, ${t.best.tests_passed}/${t.best.tests_total} tests, ${t.attempts.length} attempt(s)`
                      : "no attempts yet") +
                    (a ? ` · ${activityTitle(a)}` : "")
                  }
                >
                  {dot && (
                    <span className="absolute top-1.5 right-1.5 flex" role="img" aria-label={activityText(dot)}>
                      <ActivityDot status={dot.status} />
                    </span>
                  )}
                </StudentTile>
              </li>
            );
          })}
        </ul>
      )}

      {!controlled && (
        <StudentDrawer
          key={selected ?? ""}
          tracks={tracks}
          selected={selected}
          onClose={close}
          label={label}
          activity={activity}
          showCode={showCode}
        />
      )}
    </section>
  );
}

export interface StudentDrawerProps {
  // Every student (not just one grid's), so the drawer keeps showing the
  // student even after their new result moves them to another outcome.
  tracks: StudentTrack[];
  selected: string | null;
  onClose: () => void;
  label: (t: StudentTrack) => string;
  activity: StudentActivity[] | null;
  showCode?: ShowCodeControl;
}

// One student's attempts and full code. Key it by the selected student so the
// chosen attempt resets when a different student is opened.
export function StudentDrawer({ tracks, selected, onClose, label, activity, showCode }: StudentDrawerProps) {
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null);
  const track = tracks.find((t) => t.name === selected) ?? null;
  const shownSub = track
    ? (track.attempts.find((s) => s.id === selectedAttempt) ?? track.attempts[track.attempts.length - 1] ?? null)
    : null;

  return (
    <Drawer
      open={track != null}
      onClose={onClose}
      title={track ? label(track) : ""}
      meta={
        track && (
          <>
            {track.best ? (
              <Badge tone={VERDICT_TONE[verdictOf(track.best)]}>
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
          <div className="-mb-3 flex flex-wrap items-end gap-1" role="group" aria-label="Attempts">
            <span className="mr-2 pb-2.5 text-xs text-zinc-500">Attempt</span>
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
                    "min-w-9 border-b-2 px-2 pt-1 pb-2 font-mono text-sm transition-colors",
                    "rounded-t-sm focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500",
                    VERDICT_BORDER[verdictOf(s)],
                    pressed ? "font-bold text-zinc-950 border-b-[3px]" : "text-zinc-400 opacity-60 hover:text-zinc-900 hover:opacity-100",
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
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <p className="min-w-0 flex-1 text-xs text-zinc-500">{attemptTitle(shownSub)}</p>
            {showCode && <ShowCodeButton sub={shownSub} control={showCode} />}
          </div>
          <SubmissionDetail sub={shownSub} clamp={false} />
        </>
      ) : (
        <p className="text-sm text-zinc-500">Nothing submitted yet.</p>
      )}
    </Drawer>
  );
}

export interface StudentTileProps {
  label: string;
  // Numbers ("#04") are set in mono; names aren't.
  mono: boolean;
  verdict: Group;
  // Share of tests passed, drawn as the thin line at the bottom.
  share: number;
  pressed: boolean;
  onClick: () => void;
  title: string;
  // Corner marks (the activity dot).
  children?: ReactNode;
}

// One student's box, coloured by a verdict. Shared with a discussion point's
// list of students (IssueList.tsx) so both look the same.
export function StudentTile({ label, mono, verdict, share, pressed, onClick, title, children }: StudentTileProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      title={title}
      className={cx(
        "relative flex h-12 w-full flex-col justify-between rounded-md border px-2 pt-1.5 pb-2 text-left transition-[border-color,box-shadow]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
        TILE_TONE[verdict],
        TILE_HOVER[verdict],
        pressed && "ring-2 ring-brand-500 ring-offset-1",
      )}
    >
      <span className={cx("truncate pr-2.5 text-xs leading-tight", mono ? "font-mono" : "font-medium")}>{label}</span>
      {verdict !== "none" && (
        <span className="block h-[3px] overflow-hidden rounded-sm bg-black/10" aria-hidden="true">
          <span
            className={cx("block h-full rounded-sm", SCORE_LINE[verdict])}
            style={{ width: `${Math.max(share, 0.04) * 100}%` }}
          />
        </span>
      )}
      {children}
    </button>
  );
}

export interface ShowCodeButtonProps {
  sub: SubmissionRow;
  control: ShowCodeControl;
}

// Same look and states as a discussion point snippet's "Add to queue" (IssueList.tsx).
function ShowCodeButton({ sub, control }: ShowCodeButtonProps) {
  const shown = control.shownIds.has(sub.id);
  const busy = control.busyId === sub.id;
  const { taskRunning } = control;
  return (
    <button
      type="button"
      aria-pressed={shown}
      disabled={busy}
      onClick={() => control.onToggle(sub)}
      title={
        shown
          ? "Take this attempt out of the screen queue (and off the screens if it's showing)"
          : `Add this attempt to the screen queue, without the name. ${
              taskRunning ? "It goes up when the task ends; " : ""
            }the projector steps through the queue.`
      }
      className={cx(
        "inline-flex h-8 flex-none items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium whitespace-nowrap transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-wait",
        shown
          ? "border-brand-500 bg-brand-500 text-white hover:bg-brand-600"
          : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300 hover:bg-zinc-100 disabled:text-zinc-400",
      )}
    >
      {busy ? (
        shown ? "Removing..." : "Queueing..."
      ) : shown ? (
        <>
          <svg className="size-3" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <path d="M2.5 6.2l2.3 2.3L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Queued
        </>
      ) : (
        "Add to queue"
      )}
    </button>
  );
}
