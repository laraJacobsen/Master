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
          className="absolute right-2 bottom-2 rounded-md border border-zinc-200 bg-white/95 px-2 py-1 text-xs font-medium text-zinc-600 shadow-sm backdrop-blur transition-colors hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
        >
          {expanded ? "Collapse" : `Expand · ${lines} lines`}
        </button>
      )}
    </div>
  );
}

export interface IoCellProps {
  label: string;
  value: string;
  /** Mark as the wrong part (got / error). */
  bad?: boolean;
}

// One labelled value of a failing test: input, expected, got, error.
export function IoCell({ label, value, bad = false }: IoCellProps) {
  return (
    <div
      className={cx(
        "flex max-w-full items-baseline gap-2 rounded-md border px-2 py-1 text-xs",
        bad ? "border-red-200 bg-red-50" : "border-zinc-200 bg-zinc-50",
      )}
    >
      <span className="text-[10px] font-semibold tracking-wider text-zinc-500 uppercase">{label}</span>
      <code className={cx("font-mono break-words whitespace-pre-wrap", bad ? "text-red-700" : "text-zinc-900")}>
        {value}
      </code>
    </div>
  );
}

export interface FailingTest {
  stdin: string;
  expected: string;
  got: string;
  error?: string | null;
}

export interface FailingTestStripProps {
  test: FailingTest;
  className?: string;
}

export function FailingTestStrip({ test, className }: FailingTestStripProps) {
  return (
    <div className={cx("flex flex-wrap gap-1.5", className)}>
      <IoCell label="Input" value={test.stdin.trimEnd() || "(none)"} />
      <IoCell label="Expected" value={test.expected.trimEnd()} />
      <IoCell label="Got" value={test.got.trim() || "(nothing)"} bad />
      {test.error && <IoCell label="Error" value={test.error.trim().split("\n").pop() ?? ""} bad />}
    </div>
  );
}
