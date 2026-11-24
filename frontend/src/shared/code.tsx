import { useState } from "react";
import type { ReactNode } from "react";
import { cx } from "./cx";

export interface CodeBlockProps {
  /** The code, or marked-up code (see lecturer/ExampleBlock). */
  children: ReactNode;
  /** Line count of the code, for the height cap. */
  lines: number;
  /** Cap long code's height (scrolls inside, with an Expand toggle). */
  clamp?: boolean;
  className?: string;
}

// Code longer than this many lines starts capped when `clamp` is on.
const CLAMP_LINES = 22;

// Student code, shown the same way on every page: monospace, no wrapping
// (long lines scroll sideways), and long programs capped to a scrollable box.
export function CodeBlock({ children, lines, clamp = true, className }: CodeBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const long = clamp && lines > CLAMP_LINES;
  return (
    <div className={cx("relative", className)}>
      <code
        className={cx(
          "block overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 p-4 font-mono text-[13px] leading-relaxed whitespace-pre text-zinc-900",
          long && !expanded && "max-h-[26rem]",
        )}
      >
        {children}
      </code>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="absolute right-2 bottom-2 rounded-md border border-zinc-200 bg-white/95 px-2 py-1 text-xs font-medium text-zinc-600 shadow-sm backdrop-blur transition-colors hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
        >
          {expanded ? "Collapse" : `Expand · ${lines} lines`}
        </button>
      )}
    </div>
  );
}

export interface FailingTest {
  stdin: string;
  expected: string;
  got: string;
  error?: string | null;
  // Test-graded tasks: which test failed and its message, instead of input/output.
  testName?: string | null;
  message?: string | null;
}

export interface FailingTestStripProps {
  test: FailingTest;
  className?: string;
}

export function FailingTestStrip({ test, className }: FailingTestStripProps) {
  const rows: Array<[string, string, boolean]> = test.testName
    ? [
        ["Test", test.testName, false],
        ["Failed", test.message?.trim() || "(no message)", true],
      ]
    : [
        ["Input", test.stdin.trimEnd() || "(none)", false],
        ["Expected", test.expected.trimEnd(), false],
        ["Got", test.got.trim() || "(nothing)", true],
      ];
  if (test.error && !test.testName) rows.push(["Error", test.error.trim().split("\n").pop() ?? "", true]);
  // A small two-column table: labels left, values in monospace. Long values
  // wrap inside their cell instead of stretching the page.
  return (
    <dl className={cx("grid grid-cols-[max-content_minmax(0,1fr)] gap-x-5 gap-y-1 text-xs", className)}>
      {rows.map(([label, value, bad]) => (
        <div key={label} className="contents">
          <dt className="pt-px text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">{label}</dt>
          <dd className={cx("max-h-24 overflow-auto font-mono break-words whitespace-pre-wrap", bad ? "text-red-700" : "text-zinc-900")}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
