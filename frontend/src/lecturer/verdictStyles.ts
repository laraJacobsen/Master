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

// The big class bar on the live dashboard: same hues as VERDICT_FILL, with
// the error hatch drawn as light stripes over solid red so a count can sit on top.
export const HERO_FILL: Record<Verdict | "none", string> = {
  correct: "bg-emerald-600 text-white",
  partially_correct: "bg-amber-400 text-amber-950",
  incorrect: "bg-red-600 text-white",
  error:
    "bg-red-800 text-white bg-[repeating-linear-gradient(135deg,transparent_0_7px,rgb(255_255_255/0.16)_7px_14px)]",
  none: "bg-zinc-100 text-zinc-500",
};

// Student tiles: a light tint of the verdict hue, solid in the score line.
export const TILE_TONE: Record<Verdict | "none", string> = {
  correct: "border-emerald-200 bg-emerald-50 text-emerald-900 hover:border-emerald-400",
  partially_correct: "border-amber-200 bg-amber-50 text-amber-900 hover:border-amber-400",
  incorrect: "border-red-200 bg-red-50 text-red-900 hover:border-red-400",
  error:
    "border-red-300 text-red-900 hover:border-red-500 bg-red-50 bg-[repeating-linear-gradient(135deg,transparent_0_5px,rgb(220_38_38/0.08)_5px_10px)]",
  none: "border-dashed border-zinc-300 bg-white text-zinc-500 hover:border-zinc-400",
};

export const SCORE_LINE: Record<Verdict, string> = {
  correct: "bg-emerald-600",
  partially_correct: "bg-amber-500",
  incorrect: "bg-red-600",
  error: "bg-red-700",
};
