import { useEffect, useState } from "react";
import type { LectureHistoryRow, LectureReview, LectureReviewTask } from "../shared/types";
import { archiveLecture, fetchLectureHistory, fetchLectureReview, unarchiveLecture } from "../shared/api";
import { NavBar } from "../shared/NavBar";
import { Button, Card, Checkbox, Code, EmptyState, Eyebrow, PageHeader, Page, SectionTitle, TextLink } from "../shared/ui";
import { cx } from "../shared/cx";

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
const TREND_LECTURES = 10;

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
      <span className="block h-full rounded-sm bg-zinc-900" style={{ width: percent(rate) }} />
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
    <li className="border-t border-zinc-200 first:border-t-0">
      <button
        type="button"
        className="group -mx-3 flex w-[calc(100%+1.5rem)] items-center gap-4 rounded-lg px-3 py-3.5 text-left transition-colors hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-zinc-900"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span
          className={cx(
            "grid size-7 flex-none place-items-center rounded-md font-mono text-xs font-semibold",
            rank === 1 ? "bg-zinc-950 text-white" : "border border-zinc-200 text-zinc-600",
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

export interface TrendProps {
  ranked: LectureReview[];
}

function Trend({ ranked }: TrendProps) {
  const chronological = [...ranked]
    .sort((a, b) => parseDate(a.started_at).getTime() - parseDate(b.started_at).getTime())
    .slice(-TREND_LECTURES);
  const weakest = ranked[0]?.lecture_id;
  return (
    <div className="mt-6" role="img" aria-label="Share of tasks solved per lecture, oldest to newest">
      <div className="relative flex h-36 items-end justify-evenly gap-1.5 border-b border-zinc-300 pr-10 sm:gap-3">
        {[0.25, 0.5, 0.75, 1].map((y) => (
          <span key={y} className="absolute inset-x-0 border-t border-dashed border-zinc-200" style={{ bottom: percent(y) }} />
        ))}
        {[0.5, 1].map((y) => (
          <span
            key={y}
            className="absolute right-0 translate-y-1/2 bg-white pl-1 font-mono text-[11px] text-zinc-400"
            style={{ bottom: percent(y) }}
          >
            {percent(y)}
          </span>
        ))}
        {chronological.map((r) => (
          <div
            key={r.lecture_id}
            className="group relative flex h-full max-w-24 flex-1 flex-col items-center justify-end"
            title={`${r.display_label}: ${percent(r.solve_rate ?? 0)} solved`}
          >
            {r.lecture_id === weakest && (
              <span className="mb-1 font-mono text-xs font-semibold text-zinc-950">{percent(r.solve_rate ?? 0)}</span>
            )}
            <span
              className={cx(
                "min-h-0.5 w-full rounded-t-sm transition-colors",
                r.lecture_id === weakest ? "bg-zinc-950" : "bg-zinc-300 group-hover:bg-zinc-400",
              )}
              style={{ height: percent(r.solve_rate ?? 0) }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-evenly gap-1.5 pr-10 sm:gap-3">
        {chronological.map((r) => (
          <span key={r.lecture_id} className="max-w-24 flex-1 text-center font-mono text-[11px] whitespace-nowrap text-zinc-500">
            {shortDate(r.started_at)}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [reviews, setReviews] = useState<LectureReview[] | null>(null);
  const [reviewError, setReviewError] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const [history, setHistory] = useState<LectureHistoryRow[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState<number | null>(null);

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

  return (
    <>
      <NavBar />
      <Page>
        <PageHeader
          eyebrow="Review"
          title="Lecture history"
          description="What should a review lecture go back over? Lectures and topics, worst first."
        />

        <div className="grid gap-6">
          {reviewError && <EmptyState title="Couldn't load the ranking." />}
          {reviews && ranked.length === 0 && !reviewError && (
            <EmptyState title={`No finished lectures with ${MIN_STUDENTS_FOR_REVIEW}+ students yet.`} />
          )}

          {ranked.length > 0 && (
            <>
              <section
                className="grid grid-cols-1 divide-y divide-zinc-200 rounded-xl border border-zinc-200 bg-white sm:grid-cols-[1fr_1.4fr_1fr] sm:divide-x sm:divide-y-0"
                aria-label="Overview"
              >
                <div className="min-w-0 p-5 sm:p-6">
                  <Eyebrow>Weakest lecture</Eyebrow>
                  <div className="mt-2 font-mono text-3xl font-semibold tracking-tight tabular-nums">
                    {percent(ranked[0].solve_rate ?? 0)}
                  </div>
                  <div className="mt-1 truncate text-[13px] text-zinc-500">{ranked[0].display_label}</div>
                </div>
                {topics[0] && (
                  <div className="min-w-0 p-5 sm:p-6">
                    <Eyebrow>Hardest topic</Eyebrow>
                    <div className="mt-2 text-xl leading-tight font-bold tracking-tight text-zinc-950">{topics[0].title}</div>
                    <div className="mt-1 truncate text-[13px] text-zinc-500">
                      {percent(topics[0].rate)} solved · {plural(topics[0].lectures, "lecture")}
                    </div>
                  </div>
                )}
                {average !== null && (
                  <div className="min-w-0 p-5 sm:p-6">
                    <Eyebrow>Average</Eyebrow>
                    <div className="mt-2 font-mono text-3xl font-semibold tracking-tight tabular-nums">{percent(average)}</div>
                    <div className="mt-1 truncate text-[13px] text-zinc-500">{plural(ranked.length, "lecture")}</div>
                  </div>
                )}
              </section>

              <Card>
                <SectionTitle>Solved per lecture</SectionTitle>
                <Trend ranked={ranked} />
              </Card>

              <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
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
                      className="group flex min-w-0 flex-1 flex-col gap-0.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
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
