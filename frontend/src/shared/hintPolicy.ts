import type { HintPolicy, HintUnlock } from "./types";

// Same defaults as backend/hint_policy.py's HintPolicy -- keep the two in step.
export const DEFAULT_HINT_POLICY: HintPolicy = {
  free_attempts: 1,
  unlock: "both",
  interval_seconds: 60,
  duplicate_similarity: 1,
  penalty: false,
};

export const UNLOCK_LABEL: Record<HintUnlock, string> = {
  attempt: "After each attempt",
  timer: "After a wait, if they tried since",
  both: "After an attempt made after the wait",
};

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** The policy in one plain sentence, for the setup page. */
export function describeHintPolicy(p: HintPolicy): string {
  const start =
    p.free_attempts === 0
      ? "A wrong first attempt gets the first hint"
      : `The first ${plural(p.free_attempts, "attempt")} get${p.free_attempts === 1 ? "s" : ""} results but no hint`;
  const wait = plural(p.interval_seconds, "second");
  const next =
    p.unlock === "attempt"
      ? "then each new attempt unlocks the next hint"
      : p.unlock === "timer"
        ? `then the next hint unlocks ${wait} after the last, if they submitted something in between`
        : `then the next hint needs a new attempt made at least ${wait} after the last hint`;
  return `${start}; ${next}. Resubmitting the same code doesn't count.`;
}
