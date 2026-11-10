import type { ActivityStatus, Verdict } from "../shared/types";

// One palette for every verdict mark on the lecturer pages (progress bar,
// attempt squares, roster bars). Amber is stepped lighter than red so the two
// separate at square size, including for colour-blind viewers, and "error"
// also gets a hatch so it never relies on colour alone.
export const VERDICT_FILL: Record<Verdict | "none", string> = {
  correct: "bg-emerald-600",
  partially_correct: "bg-amber-400",
  incorrect: "bg-red-600",
  error:
    "bg-[repeating-linear-gradient(135deg,var(--color-red-600)_0_2px,#fff_2px_4px)] shadow-[inset_0_0_0_1px_var(--color-red-600)]",
  none: "bg-zinc-200",
};

// Underline colour for an attempt chip.
export const VERDICT_BORDER: Record<Verdict, string> = {
  correct: "border-b-emerald-600",
  partially_correct: "border-b-amber-400",
  incorrect: "border-b-red-600",
  error: "border-b-red-600",
};

// Activity is shape, not hue: whether someone is typing isn't good or bad,
// and the verdict colours are taken. Active = filled, idle = ring, away = faint.
export const ACTIVITY_DOT: Record<ActivityStatus, string> = {
  active: "bg-zinc-900",
  idle: "shadow-[inset_0_0_0_2px_var(--color-zinc-900)]",
  away: "bg-zinc-300",
};
