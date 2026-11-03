import type { ActivityStatus, StudentActivity, SubmissionRow, Verdict } from "../shared/types";

// Per-student model behind the class-progress chart (ClassProgress.tsx) and
// the live dashboard's student tiles (StudentGrid.tsx).

export const ORDER: Verdict[] = ["correct", "partially_correct", "incorrect", "error"];

export const LABEL: Record<Verdict, string> = {
  correct: "correct",
  partially_correct: "partial",
  incorrect: "incorrect",
  error: "error",
};

export const ACTIVITY_LABEL: Record<ActivityStatus, string> = {
  active: "active",
  idle: "idle",
  away: "away",
};

// Higher is better -- picks each student's best attempt for the summary bar.
export const RANK: Record<Verdict, number> = { error: 0, incorrect: 1, partially_correct: 2, correct: 3 };

export interface StudentTrack {
  name: string;
  attempts: SubmissionRow[]; // oldest first; empty if they haven't submitted yet
  best: SubmissionRow | null;
  activity: StudentActivity | null;
}

export function verdictOf(s: SubmissionRow): Verdict {
  return s.verdict ?? "error";
}

function isBetter(a: SubmissionRow, b: SubmissionRow): boolean {
  const ra = RANK[verdictOf(a)];
  const rb = RANK[verdictOf(b)];
  if (ra !== rb) return ra > rb;
  return a.tests_passed >= b.tests_passed; // ties go to the later attempt
}

export function isSolved(t: StudentTrack): boolean {
  return t.best != null && verdictOf(t.best) === "correct";
}

// Everyone who submitted, plus (while activity is known) everyone who joined
// or opened the editor without submitting -- alphabetical, so rows stay put
// across polls.
export function buildTracks(subs: SubmissionRow[], activity: StudentActivity[] | null): StudentTrack[] {
  const byName = new Map<string, SubmissionRow[]>();
  for (const sub of [...subs].sort((a, b) => a.id - b.id)) {
    byName.set(sub.student_name, [...(byName.get(sub.student_name) ?? []), sub]);
  }
  const activityByName = new Map((activity ?? []).map((a) => [a.student_name, a]));
  const names = new Set([...byName.keys(), ...activityByName.keys()]);
  return [...names]
    .map((name) => {
      const attempts = byName.get(name) ?? [];
      return {
        name,
        attempts,
        best: attempts.length ? attempts.reduce((best, s) => (isBetter(s, best) ? s : best)) : null,
        activity: activityByName.get(name) ?? null,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function attemptTitle(s: SubmissionRow): string {
  const time = (s.created_at || "").split(" ")[1] || s.created_at;
  const result = s.rejection_reason
    ? `rejected (${s.rejection_reason})`
    : `${LABEL[verdictOf(s)]}, ${s.tests_passed}/${s.tests_total} tests`;
  const kind = s.error_type && s.error_type !== "none" ? ` · ${s.error_type}` : "";
  return `Attempt ${s.attempt_number} at ${time}: ${result}${kind}`;
}

function formatIdle(seconds: number): string {
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m`;
}

export function activityText(a: StudentActivity): string {
  if (a.status === "idle" && a.idle_seconds != null) return `idle ${formatIdle(a.idle_seconds)}`;
  return ACTIVITY_LABEL[a.status];
}

export function activityTitle(a: StudentActivity): string {
  const base =
    a.status === "away"
      ? a.idle_seconds == null
        ? "Joined, but hasn't opened this task"
        : "No signal from their editor (tab closed, asleep or offline)"
      : a.idle_seconds != null && a.idle_seconds >= 60
      ? `Last typed ${formatIdle(a.idle_seconds)} ago`
      : "Typing";
  return a.nudged ? `${base} · got an automatic nudge` : base;
}

