import { useEffect, useRef, useState } from "react";
import type { ActivityStatus, QuestionRow } from "../shared/types";
import { Menu } from "../shared/Menu";
import type { MenuEntry } from "../shared/Menu";
import { Button, Eyebrow, formatMMSS } from "../shared/ui";
import { ACTIVITY_LABEL, isSolved } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { CATEGORY_FILL, CATEGORY_LABEL, CATEGORY_ORDER, categoryCounts } from "../shared/categories";
import { cx } from "../shared/cx";
import { ROUTES } from "../shared/routes";

export interface LiveHeroProps {
  title: string;
  // "Introduction to Programming · Task 3 of 4" -- each part optional.
  lectureLabel: string | null;
  taskNumber: number | null;
  taskCount: number | null;
  question: QuestionRow | null;
  secondsRemaining: number | null;
  joinCode: string | null;
  // No draft left to start after this one -- Next task goes away.
  lastTask: boolean;
  advancing: boolean;
  advanceMessage: string | null;
  onNextTask: () => void;
  onEndTaskNow: () => void;
  // Opens the "end the whole lecture?" confirm.
  onEndLecture: () => void;
  // This is the live task, so its buttons move the lecture on.
  controls: boolean;
  // The task belongs to the active lecture, so "End session..." ends the right one.
  canEndLecture: boolean;
  // Not the live task: an earlier one, or one from a past lecture.
  pastTask: boolean;
  // Where a past task's page points the lecturer instead.
  pastLink: { href: string; label: string } | null;
  submitted: number;
  expected: number | null;
  tracks: StudentTrack[];
  // Activity only means something while students can still type.
  showActivity: boolean;
  // Where the "scroll for more" cue jumps to.
  contentId: string;
}

// Same white-on-purple button as the home page's "Lecture in progress" panel.
const ON_ACCENT_BUTTON =
  "bg-white text-brand-700 shadow-brand-900/20 hover:bg-brand-50 active:bg-brand-100 focus-visible:outline-white";

// The top of the live dashboard: a full-width band, purple (slowly drifting)
// while students work and white once time is up, holding the task, the clock,
// submissions and the verdict bar. Once it's scrolled past, a slim copy sticks
// under the nav -- a separate strip rather than a shrinking sticky band, so the
// page never jumps while it collapses.
export function LiveHero(props: LiveHeroProps) {
  const {
    title,
    lectureLabel,
    taskNumber,
    taskCount,
    question,
    secondsRemaining,
    joinCode,
    lastTask,
    advancing,
    advanceMessage,
    onNextTask,
    onEndTaskNow,
    onEndLecture,
    controls,
    canEndLecture,
    pastTask,
    pastLink,
    submitted,
    expected,
    tracks,
    showActivity,
    contentId,
  } = props;
  const [showTask, setShowTask] = useState(false);
  const [compact, setCompact] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    // 56px = the nav bar (h-14) the strip sits under. Only "scrolled past"
    // counts, not "not yet scrolled into view".
    const io = new IntersectionObserver(
      ([entry]) => setCompact(!entry.isIntersecting && entry.boundingClientRect.top < 56),
      { rootMargin: "-56px 0px 0px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const running = secondsRemaining != null && secondsRemaining > 0;
  const ended = secondsRemaining === 0;
  const timeFraction =
    question && secondsRemaining != null && question.duration_seconds > 0
      ? Math.min(1, Math.max(0, secondsRemaining / question.duration_seconds))
      : 0;
  const notSubmitted = expected != null ? Math.max(0, expected - submitted) : null;
  const unsolved = tracks.filter((t) => !isSolved(t));
  const activityCounts = (["active", "idle", "away"] as ActivityStatus[]).map(
    (st) => [st, unsolved.filter((t) => (t.activity?.status ?? "away") === st).length] as const,
  );
  const example = question?.test_cases[0] ?? null;
  const eyebrow = [
    lectureLabel,
    taskNumber != null && (taskCount != null ? `Task ${taskNumber} of ${taskCount}` : `Task ${taskNumber}`),
  ].filter(Boolean);

  const taskItems: MenuEntry[] = [
    ...(question ? [{ label: showTask ? "Hide task text" : "Show task text", onSelect: () => setShowTask((v) => !v) }] : []),
  ];
  const menuItems: MenuEntry[] = [
    ...taskItems,
    ...(taskItems.length ? ["separator" as const] : []),
    { label: "Projector view ↗", href: ROUTES.present, newTab: true },
    { label: "Question setup", href: ROUTES.setup },
    // Ends the whole lecture for everyone -- kept in here, not on the page,
    // so it isn't clicked by accident (and it still asks to confirm).
    ...(canEndLecture
      ? (["separator", { label: "End session...", tone: "danger", disabled: advancing, onSelect: onEndLecture }] as MenuEntry[])
      : []),
  ];
  const menu = (
    <Menu
      label="More actions"
      items={menuItems}
      header={
        joinCode && (
          <>
            <Eyebrow>Join code</Eyebrow>
            <div className="mt-1 font-mono text-2xl font-bold tracking-[0.16em] text-zinc-950">{joinCode}</div>
          </>
        )
      }
    />
  );
  // While students are still working, the main button ends the task early;
  // only once it has ended does it move on. On the last task, ending the
  // lecture takes Next task's place (it still asks to confirm, same as the
  // menu's "End session...").
  const nextButton = (size: "md" | "lg") =>
    !controls ? null : running ? (
      <Button size={size} onClick={onEndTaskNow} disabled={advancing} className={ON_ACCENT_BUTTON}>
        End task early
      </Button>
    ) : lastTask ? (
      <Button size={size} onClick={onEndLecture} disabled={advancing} className={onBand ? ON_ACCENT_BUTTON : undefined}>
        End lecture
      </Button>
    ) : (
      <Button size={size} onClick={onNextTask} disabled={advancing} className={onBand ? ON_ACCENT_BUTTON : undefined}>
        Next task
        <span aria-hidden="true">&rarr;</span>
      </Button>
    );

  // White text on the band both while running (purple) and once ended (deep purple).
  const onBand = running || ended;
  const muted = onBand ? "text-white/75" : "text-zinc-500";
  const RUNNING_BG =
    "animate-gradient-drift bg-linear-to-br from-brand-500 via-violet-500 to-brand-600 bg-size-[200%_200%] text-white motion-reduce:animate-none";
  const ENDED_BG =
    "animate-gradient-drift-slow bg-linear-to-br from-brand-900 via-brand-950 to-violet-950 bg-size-[200%_200%] text-white motion-reduce:animate-none";

  return (
    <>
      <section
        id={onBand ? "live-band" : undefined}
        aria-label="Task status"
        className={cx(
          "relative isolate overflow-hidden",
          running ? RUNNING_BG : ended ? ENDED_BG : "border-b border-zinc-200 bg-white text-zinc-950",
        )}
      >
        {onBand && (
          // Soft light from the top right -- depth without decoration. Once the
          // task has ended it slowly breathes, so the band still reads as alive.
          <div
            aria-hidden="true"
            className={cx(
              "pointer-events-none absolute inset-0 -z-10",
              running
                ? "bg-[radial-gradient(40rem_20rem_at_100%_0%,rgb(255_255_255/0.2),transparent_70%)]"
                : "animate-breathe bg-[radial-gradient(48rem_24rem_at_85%_0%,rgb(139_92_246/0.45),transparent_70%)] motion-reduce:animate-none",
            )}
          />
        )}
        {/* On the band, the nav bar sits over its top (NavBar overlayBandId), so
            the band's own padding starts 3.5rem (the bar's height) lower. */}
        <div
          className={cx(
            "mx-auto w-full max-w-[112rem] px-5 pb-6 sm:px-8",
            onBand ? "pt-24 sm:pt-28" : "pt-10 sm:pt-14",
          )}
        >
          {pastTask && (
            <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-bold tracking-tight text-zinc-950">This task has finished</p>
                <p className="text-[13px] text-zinc-500">
                  You're looking at its results. The lecture is moved on from the live task, not from here.
                </p>
              </div>
              {pastLink && (
                <a
                  href={pastLink.href}
                  className="rounded-sm text-[13px] font-medium whitespace-nowrap text-zinc-900 underline decoration-brand-300 underline-offset-4 transition-colors hover:text-brand-700 hover:decoration-brand-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
                >
                  {pastLink.label} &rarr;
                </a>
              )}
            </div>
          )}
          {ended && controls && (
            <div className="mb-6 flex flex-wrap items-center gap-x-3.5 gap-y-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3">
              <span className="grid size-8 place-items-center rounded-lg bg-white/15 text-white" aria-hidden="true">
                <span className="size-2.5 rounded-[2px] bg-current" />
              </span>
              <div>
                <p className="font-bold tracking-tight">Task ended</p>
                <p className="text-[13px] text-white/70">
                  Students are waiting and the queued examples are on screen.{" "}
                  {lastTask ? "End the lecture" : "Start the next task"} when you're done.
                </p>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
            <div className="min-w-0 flex-1 basis-80">
              {eyebrow.length > 0 && <Eyebrow className={muted}>{eyebrow.join(" · ")}</Eyebrow>}
              <h1 className="mt-2 text-4xl font-bold tracking-tight text-balance lg:text-5xl">{title}</h1>
            </div>
            <div className="flex items-center gap-2">
              {nextButton("lg")}
              {menu}
            </div>
          </div>
          {advanceMessage && (
            <p className={cx("mt-3 text-[13px] font-medium", onBand ? "text-white" : "text-red-600")}>{advanceMessage}</p>
          )}

          <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] lg:items-end">
            <div className="flex items-end justify-between gap-8">
              <div>
                <div className="flex items-center gap-2">
                  {running ? (
                    <span className="grid size-3.5 place-items-center rounded-full border border-white" aria-hidden="true">
                      <span className="size-1.5 animate-pulse-dot rounded-full bg-white" />
                    </span>
                  ) : (
                    <span className="size-2 rounded-full bg-zinc-300" aria-hidden="true" />
                  )}
                  <Eyebrow className={muted}>
                    {running ? "Live submissions" : ended ? "Final submissions" : "Submissions"}
                  </Eyebrow>
                </div>
                <p className="mt-2 flex items-baseline gap-1.5">
                  <span className="font-mono text-6xl leading-none font-semibold tracking-tight tabular-nums lg:text-7xl">{submitted}</span>
                  {expected != null && submitted <= expected && (
                    <span className={cx("text-3xl tabular-nums", onBand ? "text-white/60" : "text-zinc-400")}>
                      / {expected}
                    </span>
                  )}
                </p>
                <p className={cx("mt-2 text-sm", muted)}>
                  {expected != null && submitted > expected
                    ? `submitted · more than the ${expected} expected`
                    : notSubmitted != null
                      ? `submitted · ${notSubmitted} ${ended ? "didn't submit" : "still to go"}`
                      : "submitted"}
                </p>
              </div>
              <div className="text-right">
                <Eyebrow className={muted}>{ended ? "Time's up" : "Time remaining"}</Eyebrow>
                <div
                  role="timer"
                  className={cx(
                    "mt-2 font-mono text-6xl leading-none font-semibold tracking-tight tabular-nums lg:text-7xl",
                    ended && "text-white/50",
                  )}
                >
                  {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
                </div>
                <div
                  className={cx("mt-4 ml-auto h-1.5 w-40 overflow-hidden rounded-full", onBand ? "bg-white/25" : "bg-zinc-100")}
                  aria-hidden="true"
                >
                  <div
                    className={cx(
                      "ml-auto h-full rounded-full transition-[width] duration-1000 ease-linear",
                      running ? "bg-white" : ended ? "bg-white/40" : "bg-zinc-400",
                    )}
                    style={{ width: `${timeFraction * 100}%` }}
                  />
                </div>
              </div>
            </div>

            <VerdictTray tracks={tracks} expected={expected} />
          </div>

          {showActivity && unsolved.length > 0 && (
            <ul
              className={cx("mt-5 flex flex-wrap gap-x-5 gap-y-1 text-[13px]", muted)}
              aria-label="Students who haven't solved it, by activity"
              title="Students who haven't solved it yet. Idle: no typing for a few minutes. Away: editor not open."
            >
              {activityCounts.map(([st, n]) => (
                <li key={st} className={cx("flex items-center gap-1.5", st === "idle" && n > 0 && "font-semibold text-white")}>
                  <span
                    className={cx(
                      "inline-block size-2 flex-none rounded-[2px]",
                      st === "active" ? "bg-white" : st === "idle" ? "shadow-[inset_0_0_0_2px_white]" : "bg-white/35",
                    )}
                    aria-hidden="true"
                  />
                  <span className="font-mono tabular-nums">{n}</span> {ACTIVITY_LABEL[st]}
                </li>
              ))}
            </ul>
          )}

          {showTask && question && (
            <div className="mt-6 grid animate-fade-in gap-8 rounded-xl bg-white p-6 text-zinc-950 shadow-card lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <div className="min-w-0">
                <Eyebrow>Task</Eyebrow>
                <p className="mt-2 max-h-72 overflow-y-auto pr-2 text-[15px] leading-relaxed whitespace-pre-wrap text-zinc-800">
                  {question.prompt}
                </p>
                {question.grading_mode === "tests" && (
                  <p className="mt-3 text-[13px] text-zinc-500">
                    Graded by <span className="font-mono text-zinc-900">pytest</span>:{" "}
                    {question.task_meta.test_ids
                      ? `${question.task_meta.test_ids.filter((t) => t.visibility === "visible").length} visible and ${
                          question.task_meta.test_ids.filter((t) => t.visibility === "hidden").length
                        } hidden tests. Students see hidden tests only as a count.`
                      : "tests from the task folder."}
                  </p>
                )}
                {question.output_file && (
                  <p className="mt-3 text-[13px] text-zinc-500">
                    Graded on the file <span className="font-mono text-zinc-900">{question.output_file}</span>, not
                    printed output.
                  </p>
                )}
              </div>
              {example && (
                <div className="grid min-w-0 content-start gap-4">
                  <div>
                    <Eyebrow>Example input</Eyebrow>
                    <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[13px] text-zinc-900">
                      {example.stdin.trimEnd() || "(none)"}
                    </pre>
                  </div>
                  <div>
                    <Eyebrow>{question.output_file ? `Expected ${question.output_file}` : "Expected output"}</Eyebrow>
                    <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[13px] text-zinc-900">
                      {example.expected_stdout.trimEnd()}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          <div ref={sentinel} className={cx("flex justify-center", onBand ? "mt-28" : "mt-8")}>
            <a
              href={`#${contentId}`}
              className={cx(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors",
                "focus-visible:outline-2 focus-visible:outline-offset-2",
                onBand
                  ? "text-white/80 hover:bg-white/10 hover:text-white focus-visible:outline-white"
                  : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-brand-500",
              )}
            >
              Breakdown &amp; discussion points
              <svg className="size-3.5 motion-safe:animate-bounce" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* The collapsed copy, stuck under the nav once the band is scrolled past. */}
      <div
        aria-hidden={!compact}
        inert={!compact}
        className={cx(
          "fixed inset-x-0 top-14 z-40 transition-[transform,opacity] duration-200 ease-out",
          compact ? "translate-y-0 opacity-100" : "pointer-events-none -translate-y-2 opacity-0",
          running
            ? "animate-gradient-drift bg-linear-to-r from-brand-500 via-violet-500 to-brand-600 bg-size-[200%_200%] text-white shadow-lg shadow-brand-500/20 motion-reduce:animate-none"
            : ended
              ? "animate-gradient-drift-slow bg-linear-to-r from-brand-900 via-brand-950 to-violet-950 bg-size-[200%_200%] text-white shadow-lg shadow-brand-950/30 motion-reduce:animate-none"
              : "border-b border-zinc-200 bg-white/95 text-zinc-950 shadow-sm backdrop-blur-md",
        )}
      >
        <div className="mx-auto flex h-14 w-full max-w-[112rem] items-center gap-5 px-5 sm:px-8">
          <p className="min-w-0 flex-1 truncate text-[15px] font-bold tracking-tight">
            {title}
            {ended && <span className="ml-2 font-medium text-white/60">· Task ended</span>}
          </p>
          <span className="hidden font-mono text-sm tabular-nums sm:inline">
            {submitted}
            {expected != null && <span className={onBand ? "text-white/60" : "text-zinc-400"}>/{expected}</span>}
          </span>
          <div className="hidden w-40 md:block">
            <VerdictBar tracks={tracks} expected={expected} thin onAccent={onBand} />
          </div>
          <span className={cx("font-mono text-lg font-semibold tabular-nums", ended && "text-white/50")}>
            {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
          </span>
          {nextButton("md")}
          {menu}
        </div>
      </div>
    </>
  );
}

export interface VerdictTrayProps {
  tracks: StudentTrack[];
  expected: number | null;
}

// The verdict bar on a white tray, so the verdict colours read the same as
// everywhere else even on the purple band.
function VerdictTray({ tracks, expected }: VerdictTrayProps) {
  const counts = categoryCounts(tracks.map((t) => t.best));
  const shown = CATEGORY_ORDER.filter((c) => counts.get(c));
  return (
    <div className="rounded-xl bg-white p-5 text-zinc-950 shadow-card sm:p-6">
      <Eyebrow>Verdict breakdown</Eyebrow>
      <div className="mt-4">
        <VerdictBar tracks={tracks} expected={expected} />
      </div>
      {shown.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-zinc-600">
          {shown.map((c) => (
            <li key={c} className="flex items-center gap-1.5">
              <span className={cx("size-3 rounded-[3px]", CATEGORY_FILL[c])} aria-hidden="true" />
              <span className="font-mono font-semibold text-zinc-950 tabular-nums">{counts.get(c)}</span>
              {CATEGORY_LABEL[c]}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface VerdictBarProps {
  tracks: StudentTrack[];
  expected: number | null;
  thin?: boolean;
  // Sitting directly on the purple band (the collapsed strip) -- gets a white
  // frame so the verdict colours still read.
  onAccent?: boolean;
}

function VerdictBar({ tracks, expected, thin = false, onAccent = false }: VerdictBarProps) {
  const counts = categoryCounts(tracks.map((t) => t.best));
  const shown = CATEGORY_ORDER.filter((c) => counts.get(c));
  const withResult = shown.reduce((n, c) => n + (counts.get(c) ?? 0), 0);
  const notYet = expected != null ? Math.max(0, expected - withResult) : 0;
  return (
    <div
      className={cx(
        "flex gap-0.5 overflow-hidden rounded-md",
        thin ? "h-2.5" : "h-7",
        onAccent && "bg-white p-0.5",
      )}
      role="img"
      aria-label={withResult ? shown.map((c) => `${counts.get(c)} ${CATEGORY_LABEL[c]}`).join(", ") : "No submissions yet"}
    >
      {withResult + notYet === 0 ? (
        <span className="flex-1 rounded-[3px] bg-zinc-100" />
      ) : (
        <>
          {shown.map((c) => (
            <span
              key={c}
              className={cx("min-w-1 basis-0 rounded-[3px] transition-[flex-grow] duration-500", CATEGORY_FILL[c])}
              style={{ flexGrow: counts.get(c) }}
              title={`${counts.get(c)} ${CATEGORY_LABEL[c]}`}
            />
          ))}
          {notYet > 0 && (
            <span
              className="min-w-1 basis-0 rounded-[3px] bg-zinc-100 transition-[flex-grow] duration-500"
              style={{ flexGrow: notYet }}
              title={`${notYet} not yet submitted`}
            />
          )}
        </>
      )}
    </div>
  );
}
