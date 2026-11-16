import type { LectureReview, LectureReviewTask } from "./types";

// Review helpers shared by the history page and the lecturer home: date and
// number formatting, topics grouped across lectures, month-over-month deltas.
// The matching components (Meter, IssueLine, Delta) are in reviewUi.tsx.

export function parseDate(isoLike: string): Date {
  // Server timestamps are "YYYY-MM-DD HH:MM:SS" UTC with no offset marker.
  return new Date(isoLike.replace(" ", "T") + "Z");
}
export function formatDate(isoLike: string): string {
  return parseDate(isoLike).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
export function shortDate(isoLike: string): string {
  return parseDate(isoLike).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
export function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}
export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function issueName(execVerdict: string | null, errorType: string | null): string {
  if (execVerdict === "rejected") return "Rejected before running";
  const verdict = (execVerdict || "unknown").replace(/_/g, " ");
  const label = verdict.charAt(0).toUpperCase() + verdict.slice(1);
  return errorType && errorType !== "none" ? `${label} (${errorType})` : label;
}

export interface Topic {
  title: string;
  rate: number;
  lectures: number;
  worst: LectureReviewTask; // its weakest run, for the concrete issue
}

// Same task title across lectures = same topic (the demo and real lectures
// reuse exercises), averaged so a topic that's hard every time stands out.
export function topicsFrom(ranked: LectureReview[]): Topic[] {
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

export function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

export function monthIndex(d: Date): number {
  return d.getFullYear() * 12 + d.getMonth();
}

/** This calendar month's average of `metric` minus last month's, or null if
 *  either month had no ranked lectures. */
export function monthDelta(ranked: LectureReview[], metric: (r: LectureReview) => number): number | null {
  const now = monthIndex(new Date());
  const inMonth = (m: number) => ranked.filter((r) => monthIndex(parseDate(r.started_at)) === m).map(metric);
  const cur = inMonth(now);
  const prev = inMonth(now - 1);
  return cur.length && prev.length ? mean(cur) - mean(prev) : null;
}
