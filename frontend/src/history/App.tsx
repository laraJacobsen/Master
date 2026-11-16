import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { LectureHistoryRow, LectureReview, LectureReviewTask } from "../shared/types";
import { archiveLecture, fetchLectureHistory, fetchLectureReview, unarchiveLecture } from "../shared/api";
import { NavBar } from "../shared/NavBar";
import {
  Button,
  Card,
  Checkbox,
  Code,
  EmptyState,
  Eyebrow,
  PageHeader,
  Page,
  SectionTitle,
  SegmentedControl,
  Skeleton,
  TextLink,
} from "../shared/ui";
import { cx } from "../shared/cx";
import { TrendChart } from "./TrendChart";
import type { TrendPoint } from "./TrendChart";

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
// Time windows for the "Solved per lecture" chart: a calendar month, or a
// semester -- Spring is January-July, Autumn August-December. Both can be
// stepped back and forth with the arrows next to the toggle.
type TrendRange = "month" | "semester";
const TREND_RANGES: ReadonlyArray<{ value: TrendRange; label: string }> = [
  { value: "month", label: "Month" },
  { value: "semester", label: "Semester" },
];
const AUTUMN_START_MONTH = 7; // August, 0-based

interface Period {
  start: Date; // inclusive
  end: Date; // exclusive
  label: string;
}

/** The month or semester that contains `at`. */
function periodAt(range: TrendRange, at: Date): Period {
  const y = at.getFullYear();
  if (range === "month") {
    return {
      start: new Date(y, at.getMonth(), 1),
      end: new Date(y, at.getMonth() + 1, 1),
      label: at.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
    };
  }
  return at.getMonth() >= AUTUMN_START_MONTH
    ? { start: new Date(y, AUTUMN_START_MONTH, 1), end: new Date(y + 1, 0, 1), label: `Autumn ${y}` }
    : { start: new Date(y, 0, 1), end: new Date(y, AUTUMN_START_MONTH, 1), label: `Spring ${y}` };
}

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

export interface MeterProps {
  rate: number;
  size?: "sm" | "md";
  className?: string;
}

// One neutral hue on every bar -- a low share says "go back over this", not
// "failed", so no red/amber/green here.
function Meter({ rate, size = "md", className }: MeterProps) {
  return (
    <span
      className={cx(
        "inline-block overflow-hidden rounded-sm bg-zinc-200 align-middle",
        size === "md" ? "h-1.5 w-28" : "h-1 w-full",
        className,
      )}
      role="img"
      aria-label={`${percent(rate)} solved`}
    >
      <span className="block h-full rounded-sm bg-brand-500" style={{ width: percent(rate) }} />
    </span>
  );
}

// What went wrong, as concretely as the data allows: for a wrong answer, the
// actual output most of them printed; otherwise the error kind and its line.
export interface IssueLineProps {
  task: LectureReviewTask;
}

function IssueLine({ task }: IssueLineProps) {
  const issue = task.top_issue;
  if (!issue) {
    return task.submitted === 0 ? <p className="mt-2 text-[13px] text-zinc-500">No submissions</p> : null;
  }
  const ex = issue.example;
  if (ex) {
    return (
      <p className="mt-2 text-[13px] leading-relaxed text-zinc-700">
        <strong className="font-semibold text-zinc-900">{plural(ex.students, "student")}</strong> printed{" "}
        <Code>{ex.stdout || "(nothing)"}</Code> for input <Code>{ex.stdin.trim() || "(empty)"}</Code>, expected{" "}
        <Code>{ex.expected_stdout.trim()}</Code>
      </p>
    );
  }
  return (
    <p className="mt-2 text-[13px] leading-relaxed text-zinc-700">
      <strong className="font-semibold text-zinc-900">{plural(issue.students, "student")}</strong>:{" "}
      {issueName(issue.exec_verdict, issue.error_type)}
      {issue.discussion_point && <span className="text-zinc-500"> {issue.discussion_point}</span>}
    </p>
  );
}

export interface TaskRowProps {
  task: LectureReviewTask;
}

function TaskRow({ task }: TaskRowProps) {
  const notSubmitted = task.students - task.submitted;
  return (
    <li className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-zinc-900">{task.title}</span>
        <TextLink className="text-[13px] whitespace-nowrap" href={`lecturer.html?question_id=${encodeURIComponent(task.question_id)}`}>
          View task
        </TextLink>
      </div>
      {task.solve_rate !== null && (
        <div className="mt-2 flex items-center gap-3">
          <Meter rate={task.solve_rate} size="sm" className="max-w-36" />
          <span className="text-[13px] whitespace-nowrap text-zinc-700">
            <span className="font-mono tabular-nums">
              {task.solved}/{task.students}
            </span>{" "}
            solved
            {notSubmitted > 0 && <span className="text-zinc-500"> · {notSubmitted} didn't submit</span>}
          </span>
        </div>
      )}
      <IssueLine task={task} />
    </li>
  );
}

export interface LectureItemProps {
  review: LectureReview;
  rank: number;
  open: boolean;
  onToggle: () => void;
}

function LectureItem({ review, rank, open, onToggle }: LectureItemProps) {
  const panelId = `lecture-panel-${review.lecture_id}`;
  return (
    <li id={`lecture-item-${review.lecture_id}`} className="scroll-mt-24 border-t border-zinc-200 first:border-t-0">
      <button
        type="button"
        className={cx(
          "group -mx-3 flex w-[calc(100%+1.5rem)] items-center gap-4 rounded-lg px-3 py-3.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500",
          open ? "bg-brand-50/70" : "hover:bg-zinc-50",
        )}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span
          className={cx(
            "grid size-7 flex-none place-items-center rounded-md font-mono text-xs font-semibold",
            rank === 1 ? "bg-brand-500 text-white" : "border border-zinc-200 text-zinc-600",
          )}
        >
          {rank}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-sm font-semibold text-zinc-900">{review.display_label}</span>
          <span className="text-[13px] text-zinc-500">
            {formatDate(review.started_at)} · {plural(review.students, "student")} · {plural(review.tasks.length, "task")}
          </span>
        </span>
        {review.solve_rate !== null && (
          <span
            className="flex flex-none items-center gap-3"
            title="Share of students who solved each task, averaged. Not submitting counts as not solved."
          >
            <span className="min-w-10 text-right font-mono text-sm font-semibold tabular-nums">
              {percent(review.solve_rate)}
            </span>
            <Meter rate={review.solve_rate} className="max-sm:hidden" />
          </span>
        )}
        <svg
          className={cx("size-4 flex-none text-zinc-400 transition-transform group-hover:text-zinc-700", open && "rotate-180")}
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="pb-5 sm:pl-11" id={panelId}>
          <ul className="grid gap-2.5">
            {review.tasks.map((t) => (
              <TaskRow key={t.question_id} task={t} />
            ))}
          </ul>
          <TextLink className="mt-4 inline-block text-[13px]" href={`lecturer.html?lecture_id=${review.lecture_id}`}>
            Lecture summary &rarr;
          </TextLink>
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

export interface PeriodArrowProps {
  dir: "prev" | "next";
  label: string;
  disabled: boolean;
  onClick: () => void;
}

function PeriodArrow({ dir, label, disabled, onClick }: PeriodArrowProps) {
  return (
    <Button variant="ghost" size="sm" className="w-8 px-0" aria-label={label} disabled={disabled} onClick={onClick}>
      <svg className="size-4" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d={dir === "prev" ? "M10 4L6 8l4 4" : "M6 4l4 4-4 4"}
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </Button>
  );
}

export interface TrendProps {
  ranked: LectureReview[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function Trend({ ranked, selectedId, onSelect }: TrendProps) {
  const [range, setRange] = useState<TrendRange>("semester");
  // Any date inside the period on screen; switching Month <-> Semester keeps
  // you in the same stretch of time (October -> Autumn -> October).
  const [cursor, setCursor] = useState(() => new Date());
  const period = periodAt(range, cursor);
  const earliest = ranked.reduce<number>((min, r) => Math.min(min, parseDate(r.started_at).getTime()), Infinity);
  const canPrev = earliest < period.start.getTime();
  const canNext = period.end.getTime() <= Date.now();

  function changeRange(next: TrendRange) {
    // Stepping between semesters leaves the cursor on its first day; going back
    // to Month from there, show the latest month of it that has happened.
    if (next === "month" && range === "semester") {
      const now = new Date();
      setCursor(period.end.getTime() > now.getTime() ? now : new Date(period.end.getTime() - 1));
    }
    setRange(next);
  }

  const points: TrendPoint[] = ranked
    .filter((r) => {
      const t = parseDate(r.started_at).getTime();
      return t >= period.start.getTime() && t < period.end.getTime();
    })
    .sort((a, b) => parseDate(a.started_at).getTime() - parseDate(b.started_at).getTime())
    .map((r) => ({
      id: r.lecture_id,
      label: r.display_label,
      date: shortDate(r.started_at),
      rate: r.solve_rate ?? 0,
      detail: plural(r.students, "student"),
    }));
  return (
    <>
      <SectionTitle
        actions={
          <>
            <div className="flex items-center gap-0.5">
              <PeriodArrow
                dir="prev"
                label={`Previous ${range}`}
                disabled={!canPrev}
                onClick={() => setCursor(new Date(period.start.getTime() - 1))}
              />
              <span className="min-w-32 text-center text-[13px] font-semibold text-zinc-900 tabular-nums" aria-live="polite">
                {period.label}
              </span>
              <PeriodArrow
                dir="next"
                label={`Next ${range}`}
                disabled={!canNext}
                onClick={() => setCursor(new Date(period.end))}
              />
            </div>
            <SegmentedControl label="Time range" options={TREND_RANGES} value={range} onChange={changeRange} />
          </>
        }
      >
        Solved per lecture
      </SectionTitle>
      {points.length > 0 ? (
        <TrendChart className="mt-6" points={points} selectedId={selectedId} onSelect={onSelect} />
      ) : (
        <EmptyState className="mt-6" title={`No ranked lectures in ${period.label}.`} />
      )}
    </>
  );
}

// ---------------------------------------------------------------- Loading

/** The page's own layout in grey, shown until the ranking arrives. */
function ReviewSkeleton() {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6" role="status" aria-label="Loading lecture history">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} className="relative">
            <Skeleton className="absolute -top-3 -right-3 size-10 rounded-full ring-4 ring-zinc-50" />
            <Skeleton className="h-3 w-28" />
            <Skeleton className="mt-6 h-11 w-24" />
            <Skeleton className="mt-3 h-2.5 w-32" />
          </Card>
        ))}
      </div>

      <Card>
        <div className="flex items-center gap-3">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="ml-auto h-7 w-40" />
          <Skeleton className="h-8 w-40 rounded-lg" />
        </div>
        <Skeleton className="mt-6 h-[220px] w-full rounded-lg" />
        <Skeleton className="mt-3 h-3 w-full" />
      </Card>

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <Card>
          <Skeleton className="mb-5 h-4 w-44" />
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center gap-4 border-t border-zinc-200 py-4 first:border-t-0">
              <Skeleton className="size-7 flex-none" />
              <div className="flex-1">
                <Skeleton className="h-3.5 w-3/5" />
                <Skeleton className="mt-2 h-3 w-2/5" />
              </div>
              <Skeleton className="h-3 w-24 max-sm:hidden" />
            </div>
          ))}
        </Card>
        <Card>
          <Skeleton className="mb-5 h-4 w-36" />
          {[0, 1, 2].map((i) => (
            <div key={i} className="border-t border-zinc-200 py-4 first:border-t-0 first:pt-0">
              <Skeleton className="h-3.5 w-1/2" />
              <Skeleton className="mt-3 h-1.5 w-full" />
              <Skeleton className="mt-3 h-3 w-4/5" />
            </div>
          ))}
        </Card>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

function ListSkeleton() {
  return (
    <ul className="mt-3" role="status" aria-label="Loading lectures">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="flex items-center gap-3 border-t border-zinc-200 py-3.5 first:border-t-0">
          <div className="flex-1">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="mt-2 h-3 w-1/2" />
          </div>
          <Skeleton className="h-8 w-20 rounded-lg" />
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------ Overview cards

function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

/** Share of the lecture's students who submitted anything, averaged over its tasks. */
function participationOf(r: LectureReview): number {
  const shares = r.tasks.filter((t) => t.students > 0).map((t) => t.submitted / t.students);
  return shares.length ? mean(shares) : 0;
}

function monthIndex(d: Date): number {
  return d.getFullYear() * 12 + d.getMonth();
}

/** This calendar month's average of `metric` minus last month's, or null if
 *  either month had no ranked lectures. */
function monthDelta(ranked: LectureReview[], metric: (r: LectureReview) => number): number | null {
  const now = monthIndex(new Date());
  const inMonth = (m: number) => ranked.filter((r) => monthIndex(parseDate(r.started_at)) === m).map(metric);
  const cur = inMonth(now);
  const prev = inMonth(now - 1);
  return cur.length && prev.length ? mean(cur) - mean(prev) : null;
}

export interface DeltaProps {
  /** Difference as a share (0.05 = 5 percentage points). */
  value: number;
}

/** "+5 pts since last month" -- green up, red down, grey when flat. */
function Delta({ value }: DeltaProps) {
  const pts = Math.round(value * 100);
  const tone = pts > 0 ? "text-emerald-700" : pts < 0 ? "text-red-600" : "text-zinc-500";
  const sign = pts > 0 ? "+" : pts < 0 ? "\u2212" : "\u00b1";
  return (
    <div className={cx("mt-2 text-[11px] font-normal", tone)}>
      {sign}
      {Math.abs(pts)} pts since last month
    </div>
  );
}

export interface OverviewCardProps {
  label: string;
  icon: ReactNode;
  value: ReactNode;
  /** Render the value as a heading (a name) rather than a big number. */
  valueIsText?: boolean;
  delta?: number | null;
}

function OverviewCard({ label, icon, value, valueIsText = false, delta = null }: OverviewCardProps) {
  return (
    <Card className="relative flex min-w-0 flex-col">
      {/* Sits on the card's top-right corner, half over the edge. */}
      <span
        className="absolute -top-3 -right-3 grid size-10 place-items-center rounded-full bg-brand-50 text-brand-600 shadow-card ring-4 ring-zinc-50"
        aria-hidden="true"
      >
        {icon}
      </span>
      <Eyebrow className="pr-6 text-xs">{label}</Eyebrow>
      <div
        className={cx(
          "mt-5",
          valueIsText
            ? "flex min-h-14 items-center text-3xl leading-tight font-bold tracking-tight text-balance text-zinc-950"
            : "font-mono text-5xl leading-[3.5rem] font-semibold tracking-tight text-zinc-950 tabular-nums",
        )}
      >
        {value}
      </div>
      {delta !== null && <Delta value={delta} />}
    </Card>
  );
}

const iconProps = {
  className: "size-[18px]",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function IconTrendDown() {
  return (
    <svg {...iconProps}>
      <path d="M3 7l6 6 4-4 8 8" />
      <path d="M15 17h6v-6" />
    </svg>
  );
}

function IconTarget() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <circle cx="12" cy="12" r="0.8" fill="currentColor" />
    </svg>
  );
}

function IconGauge() {
  return (
    <svg {...iconProps}>
      <path d="M4.5 17a8.5 8.5 0 1 1 15 0" />
      <path d="M12 13l3.5-4" />
      <circle cx="12" cy="13" r="1.2" fill="currentColor" />
    </svg>
  );
}

function IconUsers() {
  return (
    <svg {...iconProps}>
      <circle cx="9" cy="8.5" r="3.2" />
      <path d="M3.5 19c.6-3 2.8-4.6 5.5-4.6s4.9 1.6 5.5 4.6" />
      <path d="M15.5 5.6a3 3 0 0 1 0 5.8" />
      <path d="M17.5 14.6c1.7.5 2.8 2 3.1 4.4" />
    </svg>
  );
}

export default function App() {
  const [reviews, setReviews] = useState<LectureReview[] | null>(null);
  const [reviewError, setReviewError] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const [history, setHistory] = useState<LectureHistoryRow[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState<number | null>(null);

  // Clicking a point on the trend opens that lecture in the ranked list and
  // brings it into view; clicking the selected point again closes it.
  function selectFromTrend(id: number) {
    const opening = openId !== id;
    setOpenId(opening ? id : null);
    if (opening) {
      requestAnimationFrame(() =>
        document.getElementById(`lecture-item-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    }
  }

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
  const participation = ranked.length ? mean(ranked.map(participationOf)) : null;

  return (
    <>
      <NavBar />
      <Page>
        <PageHeader
          eyebrow="Review"
          title="Lecture history"
          description="What should a review lecture go back over? Lectures and topics, worst first."
        />

        <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
          {reviews === null && !reviewError && <ReviewSkeleton />}
          {reviewError && <EmptyState title="Couldn't load the ranking." />}
          {reviews && ranked.length === 0 && !reviewError && (
            <EmptyState title={`No finished lectures with ${MIN_STUDENTS_FOR_REVIEW}+ students yet.`} />
          )}

          {ranked.length > 0 && (
            <>
              <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Overview">
                <OverviewCard
                  label="Weakest lecture"
                  icon={<IconTrendDown />}
                  value={percent(ranked[0].solve_rate ?? 0)}
                />
                {topics[0] && (
                  <OverviewCard
                    label="Hardest topic"
                    icon={<IconTarget />}
                    value={topics[0].title}
                    valueIsText
                  />
                )}
                {average !== null && (
                  <OverviewCard
                    label="Average solved"
                    icon={<IconGauge />}
                    value={percent(average)}
                    delta={monthDelta(ranked, (r) => r.solve_rate ?? 0)}
                  />
                )}
                {participation !== null && (
                  <OverviewCard
                    label="Participation"
                    icon={<IconUsers />}
                    value={percent(participation)}
                    delta={monthDelta(ranked, participationOf)}
                  />
                )}
              </section>

              <Card>
                <Trend ranked={ranked} selectedId={openId} onSelect={selectFromTrend} />
              </Card>

              <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
                <Card>
                  <SectionTitle className="mb-2">Lectures, worst first</SectionTitle>
                  <ol>
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
                    <p className="mt-4 border-t border-zinc-200 pt-4 text-[13px] text-zinc-500">
                      {plural(unranked, "lecture")} with under {MIN_STUDENTS_FOR_REVIEW} students not ranked.
                    </p>
                  )}
                </Card>

                <Card>
                  <SectionTitle className="mb-4">Topics to revisit</SectionTitle>
                  <ol className="grid divide-y divide-zinc-200">
                    {topics.slice(0, TOPICS_SHOWN).map((t) => (
                      <li key={t.title} className="grid gap-1.5 py-4 first:pt-0 last:pb-0">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="text-sm font-semibold text-zinc-900">{t.title}</span>
                          <span className="font-mono text-sm font-semibold tabular-nums">{percent(t.rate)}</span>
                        </div>
                        <Meter rate={t.rate} size="sm" />
                        <span className="text-xs text-zinc-500">{plural(t.lectures, "lecture")}</span>
                        <IssueLine task={t.worst} />
                      </li>
                    ))}
                  </ol>
                </Card>
              </div>
            </>
          )}

          <Card>
            <SectionTitle
              actions={
                <Checkbox
                  label="Show archived"
                  checked={showArchived}
                  onChange={(e) => setShowArchived(e.target.checked)}
                />
              }
            >
              All lectures
            </SectionTitle>
            {history === null && <ListSkeleton />}
            {history && history.length === 0 && <p className="mt-3 text-sm text-zinc-500">No lectures yet.</p>}
            {history && history.length > 0 && (
              <ul className="mt-3">
                {history.map((row) => (
                  <li
                    key={row.id}
                    className={cx(
                      "flex items-center justify-between gap-3 border-t border-zinc-200 py-3 first:border-t-0",
                      row.archived && "opacity-50",
                    )}
                  >
                    <a
                      className="group flex min-w-0 flex-1 flex-col gap-0.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
                      href={`lecturer.html?lecture_id=${row.id}`}
                    >
                      <span className="truncate text-sm font-semibold text-zinc-900 group-hover:underline group-hover:underline-offset-4">
                        {row.display_label}
                      </span>
                      <span className="text-[13px] text-zinc-500">
                        {formatDate(row.started_at)} · {plural(row.task_count, "task")} · {statsSnapshot(row)}
                      </span>
                    </a>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={archiving === row.id}
                      onClick={() => handleArchiveToggle(row)}
                    >
                      {row.archived ? "Unarchive" : "Archive"}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </Page>
    </>
  );
}
