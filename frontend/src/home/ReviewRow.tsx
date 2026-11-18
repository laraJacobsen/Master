import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { CarryForwardPoint, LectureReview, LectureReviewTask } from "../shared/types";
import { fetchLectureSummary } from "../shared/api";
import { Card, SectionTitle, Skeleton, TextLink } from "../shared/ui";
import { TrendChart } from "../shared/TrendChart";
import { Delta, IssueLine, TopicItem } from "../shared/reviewUi";
import { formatDate, parseDate, percent, plural, shortDate, topicsFrom } from "../shared/review";
import { ROUTES, lectureSummaryUrl } from "../shared/routes";

// The home page's second row: what a lecturer wants before walking into the
// next class. Last lecture (how it went, against the one before), what to
// bring up next time (its recurring issues, then its weakest tasks), and the
// topics that have gone worst across all lectures. Same data as the history
// page (GET /api/lecturer/lectures/review + the last lecture's summary).

const TREND_POINTS = 8;
const ITEMS_SHOWN = 3;

function byDate(a: LectureReview, b: LectureReview): number {
  return parseDate(a.started_at).getTime() - parseDate(b.started_at).getTime();
}

function summaryHref(lectureId: number): string {
  return lectureSummaryUrl(lectureId);
}

// ------------------------------------------------------------ Last lecture

export interface LastLectureCardProps {
  last: LectureReview;
  previous: LectureReview | null;
  recent: LectureReview[];
}

function LastLectureCard({ last, previous, recent }: LastLectureCardProps) {
  const delta = previous?.solve_rate != null && last.solve_rate != null ? last.solve_rate - previous.solve_rate : null;
  return (
    <Card className="flex min-w-0 flex-col">
      <SectionTitle
        actions={
          <TextLink href={summaryHref(last.lecture_id)} className="text-[13px]">
            Summary &rarr;
          </TextLink>
        }
      >
        Last lecture
      </SectionTitle>
      <p className="mt-3 truncate text-sm font-semibold text-zinc-900">{last.display_label}</p>
      <p className="text-[13px] text-zinc-500">
        {formatDate(last.started_at)} · {plural(last.students, "student")}
      </p>
      <div className="mt-4 flex items-baseline gap-2">
        <span className="font-mono text-4xl font-semibold tracking-tight text-zinc-950 tabular-nums">
          {percent(last.solve_rate ?? 0)}
        </span>
        <span className="text-sm text-zinc-500">solved</span>
      </div>
      {delta !== null && <Delta value={delta} label="vs. the lecture before" className="mt-1" />}
      {recent.length > 1 && (
        <TrendChart
          className="mt-auto pt-5"
          height={170}
          points={recent.map((r) => ({
            id: r.lecture_id,
            label: r.display_label,
            date: shortDate(r.started_at),
            rate: r.solve_rate ?? 0,
            detail: plural(r.students, "student"),
          }))}
          selectedId={last.lecture_id}
          tooltipOnSelect={false}
          onSelect={(id) => {
            window.location.href = summaryHref(id);
          }}
        />
      )}
    </Card>
  );
}

// ------------------------------------------------------ Bring up next time

interface NextTimeItem {
  key: string;
  title: ReactNode;
  body: ReactNode;
}

function nextTimeItems(last: LectureReview, carry: CarryForwardPoint[]): NextTimeItem[] {
  // Issues that recurred across tasks come first -- they're the strongest
  // signal -- then the weakest tasks that have a concrete issue to show.
  const recurring: NextTimeItem[] = carry.map((c, i) => ({
    key: `carry-${i}`,
    title: c.discussion_point,
    body: <p className="mt-1 text-xs text-zinc-500">Came up in {c.task_titles.join(", ")}</p>,
  }));
  const weakTasks: NextTimeItem[] = [...last.tasks]
    .filter((t): t is LectureReviewTask & { solve_rate: number } => t.solve_rate !== null && t.solve_rate < 1 && t.top_issue !== null)
    .sort((a, b) => a.solve_rate - b.solve_rate)
    .map((t) => ({
      key: `task-${t.question_id}`,
      title: (
        <span className="flex items-baseline justify-between gap-3">
          <span>{t.title}</span>
          <span className="font-mono text-[13px] font-normal text-zinc-500 tabular-nums">{percent(t.solve_rate)}</span>
        </span>
      ),
      body: <IssueLine task={t} className="line-clamp-2" />,
    }));
  return [...recurring, ...weakTasks].slice(0, ITEMS_SHOWN);
}

export interface NextTimeCardProps {
  last: LectureReview;
}

function NextTimeCard({ last }: NextTimeCardProps) {
  const [carry, setCarry] = useState<CarryForwardPoint[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchLectureSummary(last.lecture_id)
      .then((s) => !cancelled && setCarry(s.carry_forward_discussion_points))
      .catch(() => !cancelled && setCarry([])); // the weak tasks below still work without it
    return () => {
      cancelled = true;
    };
  }, [last.lecture_id]);

  const items = carry ? nextTimeItems(last, carry) : null;
  return (
    <Card className="min-w-0">
      <SectionTitle>Bring up next time</SectionTitle>
      <p className="mt-1 text-[13px] text-zinc-500">From {last.display_label}</p>
      {items === null ? (
        <div className="mt-4 grid gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i}>
              <Skeleton className="h-3.5 w-3/5" />
              <Skeleton className="mt-2 h-3 w-full" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">Nothing stood out. The class handled every task.</p>
      ) : (
        <ul className="mt-2 divide-y divide-zinc-200">
          {items.map((item) => (
            <li key={item.key} className="py-3.5 last:pb-0">
              <div className="line-clamp-3 text-sm font-semibold text-zinc-900">{item.title}</div>
              {item.body}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// -------------------------------------------------------- Topics to revisit

export interface TopicsCardProps {
  ranked: LectureReview[];
}

function TopicsCard({ ranked }: TopicsCardProps) {
  const topics = topicsFrom(ranked).slice(0, ITEMS_SHOWN);
  return (
    <Card className="min-w-0">
      <SectionTitle
        actions={
          <TextLink href={ROUTES.history} className="text-[13px]">
            All &rarr;
          </TextLink>
        }
      >
        Topics to revisit
      </SectionTitle>
      {topics.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">Not enough lectures yet.</p>
      ) : (
        <ol className="mt-3 divide-y divide-zinc-200">
          {topics.map((t) => (
            <TopicItem key={t.title} topic={t} />
          ))}
        </ol>
      )}
    </Card>
  );
}

// --------------------------------------------------------------------- Row

export interface ReviewRowProps {
  /** null while loading. */
  reviews: LectureReview[] | null;
  /** The running lecture, if any -- never counted as "last lecture". */
  activeLectureId: number | null;
}

export function ReviewRow({ reviews, activeLectureId }: ReviewRowProps) {
  if (reviews === null) {
    return (
      <div className="grid gap-6 lg:grid-cols-3" role="status" aria-label="Loading recent lectures">
        {[0, 1, 2].map((i) => (
          <Card key={i}>
            <Skeleton className="h-4 w-32" />
            <Skeleton className="mt-5 h-3.5 w-3/4" />
            <Skeleton className="mt-2 h-3 w-1/2" />
            <Skeleton className="mt-6 h-24 w-full rounded-lg" />
          </Card>
        ))}
      </div>
    );
  }

  const ranked = reviews
    .filter((r) => r.enough_data && r.solve_rate !== null && r.lecture_id !== activeLectureId)
    .sort(byDate);
  if (ranked.length === 0) return null; // nothing finished yet -- the top row says enough

  const last = ranked[ranked.length - 1];
  const previous = ranked.length > 1 ? ranked[ranked.length - 2] : null;
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <LastLectureCard last={last} previous={previous} recent={ranked.slice(-TREND_POINTS)} />
      <NextTimeCard last={last} />
      <TopicsCard ranked={ranked} />
    </div>
  );
}
