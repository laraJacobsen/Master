import type { HiddenTestsSummary, TestRunResult } from "../shared/types";
import { cx } from "../shared/cx";

// A test-graded submission's tests in the result card: every visible test by name
// with its message when it failed, the hidden tests only as a count.

export interface TestResultsListProps {
  results: TestRunResult[];
  hidden?: HiddenTestsSummary;
  className?: string;
}

export function TestResultsList({ results, hidden, className }: TestResultsListProps) {
  return (
    <div className={cx("grid gap-1.5", className)}>
      <ul className="grid gap-1" aria-label="Visible tests">
        {results.map((t) => (
          <li key={`${t.file}::${t.name}`} className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-1.5 text-[13px]">
            <span
              aria-label={t.passed ? "passed" : "failed"}
              className={cx("font-mono", t.passed ? "text-emerald-600" : "text-red-600")}
            >
              {t.passed ? "✓" : "✗"}
            </span>
            <span className="min-w-0">
              <span className="font-mono text-xs text-zinc-800">{t.name}</span>
              {!t.passed && t.message && (
                <span className="mt-0.5 block font-mono text-xs break-words text-red-700">{t.message}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {hidden && hidden.total > 0 && (
        <p className={cx("text-xs", hidden.failed ? "text-amber-800" : "text-zinc-500")}>
          {hidden.failed
            ? `${hidden.failed} of ${hidden.total} hidden test${hidden.total === 1 ? "" : "s"} failed.`
            : `All ${hidden.total} hidden test${hidden.total === 1 ? "" : "s"} passed.`}
        </p>
      )}
    </div>
  );
}
