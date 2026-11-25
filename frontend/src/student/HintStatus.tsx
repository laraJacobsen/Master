import { useEffect, useState } from "react";
import type { HintStateView } from "../shared/types";
import { formatMMSS } from "../shared/ui";

// Under the student's result: how many attempts counted, and when the next hint
// unlocks (backend/hint_policy.py). The countdown runs locally from the server's
// seconds_until_unlock, so it doesn't depend on the student's clock.
export interface HintStatusProps {
  state: HintStateView;
  // The hint shown with the result (0/null = none yet) and how many there are.
  hintTier: number | null | undefined;
  hintCeiling: number | null | undefined;
  // Called once the countdown reaches zero, to fetch the unlocked hint.
  onCountdownDone: () => void;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function useCountdown(seconds: number | null, onDone: () => void): number | null {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    setLeft(seconds);
    if (seconds == null) return;
    const end = Date.now() + seconds * 1000;
    const t = window.setInterval(() => {
      const s = Math.max(0, Math.ceil((end - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) {
        window.clearInterval(t);
        onDone();
      }
    }, 1000);
    return () => window.clearInterval(t);
    // Restart only when the server sends a new countdown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seconds]);
  return left;
}

/** The next-hint line, or null when there's nothing more to unlock. */
function nextHintText(state: HintStateView, left: number | null, allUnlocked: boolean): string | null {
  if (state.level === 0) {
    return state.free_attempts_left > 0
      ? `Your first hint comes after ${plural(state.free_attempts_left, "more attempt")}.`
      : null;
  }
  if (allUnlocked) return null;
  const wait = left != null && left > 0 ? formatMMSS(left) : null;
  switch (state.policy.unlock) {
    case "attempt":
      return "Your next attempt unlocks the next hint.";
    case "both":
      return wait
        ? `Next hint: keep working, then submit a new attempt after ${wait}.`
        : "Your next attempt unlocks the next hint.";
    case "timer":
      if (!state.needs_attempt) return wait ? `Next hint in ${wait}.` : "Next hint any moment now.";
      return wait
        ? `Next hint in ${wait}, once you've submitted a new attempt.`
        : "Submit a new attempt to unlock the next hint.";
  }
}

export function HintStatus({ state, hintTier, hintCeiling, onCountdownDone }: HintStatusProps) {
  const left = useCountdown(state.seconds_until_unlock, onCountdownDone);
  const allUnlocked = hintCeiling != null && hintCeiling > 0 && (hintTier ?? 0) >= hintCeiling;
  const next = nextHintText(state, left, allUnlocked);
  const counts = [
    plural(state.counted_attempts, "attempt") + " counted",
    state.duplicates > 0 && `${state.duplicates} resubmitted unchanged`,
    state.penalty != null && `penalty ${state.penalty}`,
  ].filter(Boolean);

  return (
    <div className="mt-3 grid gap-1 border-t border-black/5 pt-3 text-[13px] leading-relaxed">
      {next && <p className="font-medium text-zinc-900">{next}</p>}
      {allUnlocked && <p className="text-zinc-600">You&apos;ve unlocked every hint for this kind of mistake.</p>}
      {/* Only while the release is what got them their current hint. */}
      {state.released_level > 0 && state.released_level >= state.level && (
        <p className="text-zinc-600">Your lecturer released hint {state.released_level} to everyone.</p>
      )}
      <p className="font-mono text-xs text-zinc-500 tabular-nums">{counts.join(" · ")}</p>
    </div>
  );
}
