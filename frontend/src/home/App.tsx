import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ActiveLectureResponse, LectureTotals, ProgressResponse, QuestionRow } from "../shared/types";
import {
  createLecture,
  deleteLecture,
  fetchActiveLecture,
  fetchJoinedCount,
  fetchLectureTotals,
  fetchProgress,
  fetchQuestionList,
} from "../shared/api";
import { activeLectureAction } from "../shared/lectureNav";
import { NavBar } from "../shared/NavBar";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { Button, Card, ErrorText, Eyebrow, Input, Label, Skeleton, TextLink } from "../shared/ui";
import { cx } from "../shared/cx";

// Lecturer home: today's date, a greeting, then the lecture that's on right
// now as one wide brand-gradient panel (name, tasks done, submissions on the
// live task, join code, resume). With nothing running, the same slot holds
// the "start a new lecture" form.

// There are no lecturer accounts (README: "No auth"), so the name for the
// greeting lives in this browser only.
const NAME_KEY = "il.lecturerName";
const POLL_MS = 5000;

function greeting(now: Date): string {
  const h = now.getHours();
  return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

// ------------------------------------------------------------------ Name

export interface GreetingNameProps {
  name: string;
  onChange: (name: string) => void;
}

/** The name in "Good morning, Lara" -- click to edit, stored in localStorage. */
function GreetingName({ name, onChange }: GreetingNameProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  function commit() {
    onChange(draft.trim());
    setEditing(false);
  }

  if (editing) {
    return (
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault();
          commit();
        }}
      >
        <input
          ref={inputRef}
          aria-label="Your name"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setDraft(name);
              setEditing(false);
            }
          }}
          placeholder="Your name"
          size={Math.max(6, draft.length + 1)}
          className="rounded-md border-b-2 border-brand-400 bg-transparent text-brand-600 outline-none placeholder:text-zinc-300"
        />
      </form>
    );
  }

  return (
    <button
      type="button"
      onClick={() => {
        setDraft(name);
        setEditing(true);
      }}
      title="Change your name"
      className={cx(
        "rounded-md decoration-brand-300 decoration-2 underline-offset-8 transition-colors hover:underline",
        "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-500",
        name ? "text-brand-600" : "text-zinc-300 hover:text-brand-400",
      )}
    >
      {name || "add your name"}
    </button>
  );
}

// ------------------------------------------------------------- Live panel

export interface LiveStatProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  /** 0..1 -- draws a thin bar under the value. */
  progress?: number;
}

function LiveStat({ label, value, sub, progress }: LiveStatProps) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-semibold tracking-[0.08em] text-white/70 uppercase">{label}</div>
      <div className="mt-1.5 font-mono text-3xl font-semibold tracking-tight text-white tabular-nums">{value}</div>
      {progress !== undefined && (
        <div className="mt-2.5 h-1 w-full max-w-40 overflow-hidden rounded-sm bg-white/20">
          <div
            className="h-full rounded-sm bg-white transition-[width] duration-500"
            style={{ width: `${Math.max(0, Math.min(1, progress)) * 100}%` }}
          />
        </div>
      )}
      {sub && <div className="mt-1.5 truncate text-xs text-white/75">{sub}</div>}
    </div>
  );
}

export interface ActiveLecturePanelProps {
  active: ActiveLectureResponse;
  questions: QuestionRow[] | null;
  progress: ProgressResponse | null;
  joined: number | null;
  onResume: () => void;
  onDelete: () => void;
  deleting: boolean;
}

function ActiveLecturePanel({ active, questions, progress, joined, onResume, onDelete, deleting }: ActiveLecturePanelProps) {
  const lecture = active.lecture!;
  const live = active.live_question_id;
  const liveTask = questions?.find((q) => q.id === live) ?? null;
  const total = questions?.length ?? 0;
  const done = questions?.filter((q) => q.status === "closed" || q.status === "skipped").length ?? 0;
  const open = lecture.lobby_opened_at != null;
  const action = activeLectureAction(active);
  const resumeLabel = live || open ? "Resume live lecture" : action.label;
  const expected = progress?.expected ?? null;

  return (
    <section
      aria-label="Lecture in progress"
      className={cx(
        "relative isolate animate-fade-in-up overflow-hidden rounded-2xl p-6 text-white sm:p-9",
        "bg-linear-to-br from-brand-500 via-brand-500 to-violet-500 shadow-xl shadow-brand-500/25",
      )}
    >
      {/* Soft light from the top right -- depth without decoration. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(40rem_20rem_at_100%_0%,rgb(255_255_255/0.22),transparent_70%)]"
      />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] font-medium text-white/85">
        {live ? (
          <span className="inline-flex items-center gap-1.5 text-white">
            <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-white" aria-hidden="true" />
            Live now
          </span>
        ) : open ? (
          <span>Lobby open</span>
        ) : (
          <span>Not open to students yet</span>
        )}
        {liveTask && (
          <>
            <span className="text-white/40" aria-hidden="true">
              /
            </span>
            <span className="truncate">{liveTask.title}</span>
          </>
        )}
      </div>

      <h2 className="mt-3 max-w-3xl text-3xl font-bold tracking-tight text-balance sm:text-4xl">
        {lecture.display_label}
      </h2>

      <div className="mt-8 grid grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-3 lg:max-w-3xl">
        <LiveStat
          label="Tasks completed"
          value={
            questions ? (
              <>
                {done}
                <span className="text-white/60">/{total}</span>
              </>
            ) : (
              "–"
            )
          }
          progress={total ? done / total : 0}
        />
        {live ? (
          <LiveStat
            label="Submitted"
            value={
              progress ? (
                <>
                  {progress.submitted}
                  {expected !== null && <span className="text-white/60">/{expected}</span>}
                </>
              ) : (
                "–"
              )
            }
            progress={progress && expected ? progress.submitted / expected : undefined}
            sub="on the current task"
          />
        ) : (
          <LiveStat label="Joined" value={open ? (joined ?? "–") : "–"} sub={open ? "students in the lobby" : "lobby not open"} />
        )}
        {open && lecture.join_code && (
          <LiveStat
            label="Join code"
            value={<span className="tracking-[0.12em]">{lecture.join_code}</span>}
            sub="for the student page"
          />
        )}
      </div>

      <div className="mt-9 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onResume}
          className={cx(
            "inline-flex h-11 items-center gap-2 rounded-lg bg-white px-5 text-[15px] font-semibold text-brand-700",
            "shadow-sm shadow-brand-900/20 transition-colors hover:bg-brand-50 active:bg-brand-100",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white",
          )}
        >
          {resumeLabel}
          <span aria-hidden="true">&rarr;</span>
        </button>
        {!live && (
          <button
            type="button"
            onClick={onDelete}
            disabled={deleting}
            className={cx(
              "inline-flex h-11 items-center rounded-lg px-4 text-sm font-medium text-white/80 transition-colors",
              "hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-60",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white",
            )}
          >
            {deleting ? "Deleting..." : "Delete lecture"}
          </button>
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------- Page

export default function App() {
  const [now] = useState(() => new Date());
  const [name, setName] = useState(() => window.localStorage.getItem(NAME_KEY) ?? "");

  const [active, setActive] = useState<ActiveLectureResponse | null>(null);
  const [activeLoading, setActiveLoading] = useState(true);
  const [questions, setQuestions] = useState<QuestionRow[] | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [joined, setJoined] = useState<number | null>(null);

  const [label, setLabel] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [totals, setTotals] = useState<LectureTotals | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  function saveName(next: string) {
    setName(next);
    if (next) window.localStorage.setItem(NAME_KEY, next);
    else window.localStorage.removeItem(NAME_KEY);
  }

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
        // Optional stats -- fine to just not show them.
      });
  }, []);

  // The panel's numbers move while students work, so refresh them.
  const lectureId = active?.lecture?.id ?? null;
  const liveId = active?.live_question_id ?? null;
  const lobbyOpen = active?.lecture?.lobby_opened_at != null;
  useEffect(() => {
    if (lectureId === null) return;
    let cancelled = false;
    function refresh() {
      fetchQuestionList()
        .then((q) => !cancelled && setQuestions(q))
        .catch(() => {});
      if (liveId) {
        fetchProgress(liveId)
          .then((p) => !cancelled && setProgress(p))
          .catch(() => {});
      } else if (lobbyOpen && lectureId !== null) {
        fetchJoinedCount(lectureId)
          .then((j) => !cancelled && setJoined(j.joined))
          .catch(() => {});
      }
    }
    refresh();
    const t = window.setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [lectureId, liveId, lobbyOpen]);

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

  // Only ever offered before anything's started -- once a question's gone
  // live there's real history, and the backend itself refuses the delete at
  // that point anyway (see api_lecturer_delete_lecture in main.py).
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
      <main className="mx-auto w-full max-w-6xl px-5 pt-12 pb-20 sm:px-8 sm:pt-16">
        <header>
          <p className="text-sm font-medium text-zinc-500">
            {now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight text-zinc-950 sm:text-5xl">
            {greeting(now)}, <GreetingName name={name} onChange={saveName} />
          </h1>
        </header>

        <div className="mt-10">
          {activeLoading ? (
            <Skeleton className="h-72 w-full rounded-2xl" />
          ) : hasActive ? (
            <>
              <ActiveLecturePanel
                active={active!}
                questions={questions}
                progress={progress}
                joined={joined}
                onResume={handleResume}
                onDelete={() => setConfirmDeleteOpen(true)}
                deleting={deleting}
              />
              {deleteError && <ErrorText className="mt-3">{deleteError}</ErrorText>}
            </>
          ) : (
            <Card className="animate-fade-in-up p-6 sm:p-9">
              <form
                className="max-w-xl"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleNewLecture();
                }}
              >
                <h2 className="text-2xl font-bold tracking-tight text-zinc-950">No lecture running</h2>
                <p className="mt-1 text-sm text-zinc-500">
                  Start one and add questions before opening it to students.
                </p>
                <div className="mt-6">
                  <Label htmlFor="f-label" hint="optional">
                    Name
                  </Label>
                  <Input
                    type="text"
                    id="f-label"
                    placeholder="e.g. Week 3: Recursion"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                  />
                </div>
                <Button type="submit" size="lg" className="mt-5" disabled={starting}>
                  {starting ? "Starting..." : "New lecture"}
                </Button>
                {startError && <ErrorText className="mt-3">{startError}</ErrorText>}
              </form>
            </Card>
          )}
        </div>

        {/* Past lectures live on their own page (nav bar "History"). */}
        <section className="mt-8 flex flex-wrap items-end gap-x-12 gap-y-4" aria-label="So far">
          {totals && (
            <>
              <div>
                <Eyebrow>Lecture{totals.lectures_run === 1 ? "" : "s"} run</Eyebrow>
                <div className="mt-1 font-mono text-2xl font-semibold text-zinc-950 tabular-nums">
                  {totals.lectures_run}
                </div>
              </div>
              <div>
                <Eyebrow>Submission{totals.total_submissions === 1 ? "" : "s"}</Eyebrow>
                <div className="mt-1 font-mono text-2xl font-semibold text-zinc-950 tabular-nums">
                  {totals.total_submissions}
                </div>
              </div>
            </>
          )}
          <TextLink href="history.html" className="pb-1 text-sm">
            Lecture history &rarr;
          </TextLink>
        </section>
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
