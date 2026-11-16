// The outcome categories the live dashboard shows (Correct, Wrong answer,
// Syntax error, ...), from the Judge0-derived exec_verdict. One palette for
// the verdict breakdown and the discussion-point pills.

export type Category = "correct" | "wrong_answer" | "syntax_error" | "runtime_error" | "timeout" | "rejected" | "other";

export const CATEGORY_ORDER: Category[] = [
  "correct",
  "wrong_answer",
  "syntax_error",
  "runtime_error",
  "timeout",
  "rejected",
  "other",
];

export function categoryOf(execVerdict: string | null | undefined): Category {
  switch (execVerdict) {
    case "pass":
      return "correct";
    case "wrong_answer":
    case "ignores_input":
    case "missing_output_file":
      return "wrong_answer";
    case "syntax_error":
    case "compile_error":
      return "syntax_error";
    case "runtime_error":
    case "function_not_found":
      return "runtime_error";
    case "timeout":
    case "oom":
    case "output_limit_exceeded":
      return "timeout";
    case "rejected":
      return "rejected";
    default:
      return "other";
  }
}

// Each student's best result, counted per category (students without a
// submission yet are left out).
export function categoryCounts(bests: Array<{ exec_verdict: string | null } | null>): Map<Category, number> {
  const counts = new Map<Category, number>();
  for (const b of bests) {
    if (!b) continue;
    const c = categoryOf(b.exec_verdict);
    counts.set(c, (counts.get(c) ?? 0) + 1);
  }
  return counts;
}

export const CATEGORY_LABEL: Record<Category, string> = {
  correct: "Correct",
  wrong_answer: "Wrong answer",
  syntax_error: "Syntax error",
  runtime_error: "Runtime error",
  timeout: "Timeout",
  rejected: "Rejected",
  other: "Other",
};

// Only the verdict palette (shared/verdictStyles.ts): emerald = correct,
// amber = wrong answer, red = the code didn't run properly -- told apart by
// a hatch (syntax error) and a darker red (timeout), never by a new hue.
// Rejected/other aren't about the code at all, so they stay neutral.
export const CATEGORY_FILL: Record<Category, string> = {
  correct: "bg-emerald-600",
  wrong_answer: "bg-amber-400",
  syntax_error:
    "bg-[repeating-linear-gradient(135deg,var(--color-red-600)_0_2px,#fff_2px_4px)] shadow-[inset_0_0_0_1px_var(--color-red-600)]",
  runtime_error: "bg-red-600",
  timeout: "bg-red-800",
  rejected: "bg-zinc-300",
  other: "bg-zinc-300",
};

// Tinted pill for a discussion point's category.
export const CATEGORY_PILL: Record<Category, string> = {
  correct: "bg-emerald-50 text-emerald-800",
  wrong_answer: "bg-amber-50 text-amber-900",
  syntax_error: "bg-red-50 text-red-800",
  runtime_error: "bg-red-50 text-red-800",
  timeout: "bg-red-50 text-red-900",
  rejected: "bg-zinc-100 text-zinc-700",
  other: "bg-zinc-100 text-zinc-700",
};
