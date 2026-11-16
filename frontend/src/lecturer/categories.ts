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

export const CATEGORY_LABEL: Record<Category, string> = {
  correct: "Correct",
  wrong_answer: "Wrong answer",
  syntax_error: "Syntax error",
  runtime_error: "Runtime error",
  timeout: "Timeout",
  rejected: "Rejected",
  other: "Other",
};

// Solid fill: bar segments and legend dots.
export const CATEGORY_FILL: Record<Category, string> = {
  correct: "bg-emerald-600",
  wrong_answer: "bg-amber-600",
  syntax_error: "bg-violet-500",
  runtime_error: "bg-red-600",
  timeout: "bg-slate-500",
  rejected: "bg-zinc-400",
  other: "bg-zinc-400",
};

// Tinted pill for a discussion point's category.
export const CATEGORY_PILL: Record<Category, string> = {
  correct: "bg-emerald-50 text-emerald-800",
  wrong_answer: "bg-amber-50 text-amber-800",
  syntax_error: "bg-violet-50 text-violet-800",
  runtime_error: "bg-red-50 text-red-800",
  timeout: "bg-slate-100 text-slate-700",
  rejected: "bg-zinc-100 text-zinc-700",
  other: "bg-zinc-100 text-zinc-700",
};
