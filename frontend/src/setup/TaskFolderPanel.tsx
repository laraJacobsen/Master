import { useState } from "react";
import type { TaskFile, TaskMeta, ValidationTestResult, WrongSolutionCheck } from "../shared/types";
import { Button } from "../shared/ui";
import { cx } from "../shared/cx";

// Step 2 of the setup editor for a test-graded task (imported from a task folder):
// what's in the folder, read-only -- the folder is the source of truth, edited in
// the lecturer's own editor and re-imported -- and the "Check solution" result per test.

function formatSize(n: number): string {
  if (n < 1000) return `${n} B`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} KB`;
  return `${(n / 1_000_000).toFixed(2)} MB`;
}

const GROUPS: { key: string; label: string; note: string; match: (f: TaskFile, editable: Set<string>) => boolean; folder: string }[] = [
  { key: "edit", label: "Students edit", note: "", folder: "", match: (f, e) => f.role === "starter" && e.has(f.path) },
  { key: "ro", label: "Read-only for students", note: "", folder: "", match: (f, e) => f.role === "starter" && !e.has(f.path) },
  { key: "test", label: "Visible tests", note: "Students see these and their results.", folder: "tests/", match: (f) => f.role === "test" },
  { key: "hidden", label: "Hidden tests", note: "Students see how many failed, plus the sentences below if there are any.", folder: "hidden_tests/", match: (f) => f.role === "hidden_test" },
  { key: "data", label: "Data", note: "", folder: "data/", match: (f) => f.role === "data" },
  { key: "ref", label: "Reference solution", note: "Never sent to students.", folder: "reference/", match: (f) => f.role === "reference" },
  {
    key: "wrong",
    label: "Wrong solutions",
    note: "Mistakes the tests must catch. Never sent to students.",
    folder: "wrong/",
    match: (f) => f.role === "wrong",
  },
];

export interface TaskFolderSummaryProps {
  files: TaskFile[];
  meta: TaskMeta;
}

// The viewer shows this many lines of a big file (a data file can be megabytes).
const VIEWER_MAX_LINES = 400;

export interface TaskFileViewerProps {
  label: string;
  content: string;
  onClose: () => void;
}

/** One task file, read-only, under the file list -- so the tests can be read before the
 * task is started in front of the class. */
function TaskFileViewer({ label, content, onClose }: TaskFileViewerProps) {
  const lines = content.split("\n");
  const shown = lines.length > VIEWER_MAX_LINES ? lines.slice(0, VIEWER_MAX_LINES).join("\n") : content;
  return (
    <div className="mt-4 animate-fade-in overflow-hidden rounded-lg border border-zinc-200" role="region" aria-label={label}>
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 bg-zinc-50 px-3 py-1.5">
        <span className="truncate font-mono text-xs text-zinc-800">{label}</span>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <pre className="max-h-96 overflow-auto bg-white px-3 py-2.5 font-mono text-xs leading-relaxed text-zinc-800">
        {shown}
      </pre>
      {lines.length > VIEWER_MAX_LINES && (
        <p className="border-t border-zinc-200 px-3 py-1.5 text-xs text-zinc-500">
          First {VIEWER_MAX_LINES} of {lines.length} lines.
        </p>
      )}
    </div>
  );
}

export function TaskFolderSummary({ files, meta }: TaskFolderSummaryProps) {
  const editable = new Set(meta.editable ?? []);
  const testCount = meta.test_ids?.length ?? null;
  const hiddenHints = Object.entries(meta.hidden_test_hints ?? {});
  // The file open in the viewer, as "<folder><path>".
  const [openLabel, setOpenLabel] = useState<string | null>(null);
  const openFile = GROUPS.flatMap((g) =>
    files.filter((f) => g.match(f, editable)).map((f) => ({ label: g.folder + f.path, file: f })),
  ).find((x) => x.label === openLabel);
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-[13px] font-semibold text-zinc-900">Task folder</div>
        <div className="text-xs text-zinc-500">
          Graded by <span className="font-mono text-zinc-700">pytest</span>
          {testCount !== null && (
            <>
              {" "}&middot; <span className="font-mono tabular-nums text-zinc-700">{testCount}</span> tests
            </>
          )}
          {meta.test_timeout_s ? (
            <>
              {" "}&middot; <span className="font-mono tabular-nums text-zinc-700">{meta.test_timeout_s}s</span> per test
            </>
          ) : null}
        </div>
      </div>
      <p className="mt-1 text-[13px] leading-relaxed text-zinc-500">
        Imported from a task folder. To change files or tests, edit the folder and import it again.
      </p>
      <dl className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {GROUPS.map((group) => {
          const inGroup = files.filter((f) => group.match(f, editable));
          if (!inGroup.length) return null;
          return (
            <div key={group.key} className="min-w-0">
              <dt className="text-xs font-semibold text-zinc-700">{group.label}</dt>
              {group.note && <dd className="text-xs text-zinc-500">{group.note}</dd>}
              <dd className="mt-1.5">
                <ul className="grid gap-1">
                  {inGroup.map((f) => (
                    <li key={f.path} className="flex min-w-0 items-baseline justify-between gap-3 text-[13px]">
                      <button
                        type="button"
                        onClick={() => setOpenLabel((cur) => (cur === group.folder + f.path ? null : group.folder + f.path))}
                        aria-pressed={openLabel === group.folder + f.path}
                        title="Show this file"
                        className={cx(
                          "min-w-0 truncate rounded-sm text-left font-mono underline-offset-4 transition-colors hover:underline",
                          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
                          openLabel === group.folder + f.path ? "text-brand-700 underline" : "text-zinc-800",
                        )}
                      >
                        <span className="text-zinc-400">{group.folder}</span>
                        {f.path}
                      </button>
                      <span className="flex-none font-mono text-[11px] tabular-nums text-zinc-400">
                        {formatSize(new TextEncoder().encode(f.content).length)}
                      </span>
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          );
        })}
      </dl>
      {(meta.requirements?.length || meta.markers) && (
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-zinc-200 pt-3 text-xs text-zinc-500">
          {meta.requirements?.length ? (
            <span>
              Needs <span className="font-mono text-zinc-700">{meta.requirements.join(", ")}</span>
            </span>
          ) : null}
          {meta.markers && (
            <span>
              Students edit between <span className="font-mono text-zinc-700">{meta.markers.begin}</span> and{" "}
              <span className="font-mono text-zinc-700">{meta.markers.end}</span>
            </span>
          )}
        </div>
      )}
      {hiddenHints.length > 0 && (
        <div className="mt-4 border-t border-zinc-200 pt-3">
          <div className="text-xs font-semibold text-zinc-700">What students see when a hidden test fails</div>
          <dl className="mt-1.5 grid gap-1 text-xs">
            {hiddenHints.map(([name, hint]) => (
              <div key={name} className="grid gap-x-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
                <dt className="truncate font-mono text-zinc-500">{name}</dt>
                <dd className="text-zinc-800">{hint}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {openFile && (
        <TaskFileViewer label={openFile.label} content={openFile.file.content} onClose={() => setOpenLabel(null)} />
      )}
    </div>
  );
}

export interface TestCheckResultsProps {
  results: ValidationTestResult[];
  /** Whether the tests catch each wrong solution in the folder (wrong/). */
  wrongChecks?: WrongSolutionCheck[];
}

/** The reference solution's run, one row per test: every test must pass. Then one
 * row per wrong solution: each must fail the tests task.yaml says it should. */
export function TestCheckResults({ results, wrongChecks = [] }: TestCheckResultsProps) {
  const failing = results.filter((r) => !r.passed);
  const ok = results.length > 0 && failing.length === 0 && wrongChecks.every((c) => c.ok);
  return (
    <div
      className={cx(
        "mt-4 animate-fade-in rounded-lg border px-4 py-3 text-[13px] leading-relaxed",
        ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-900",
      )}
      role="status"
    >
      <strong className="font-semibold">
        {ok
          ? `The reference solution passes all ${results.length} tests.`
          : `${failing.length} of ${results.length} tests fail on the reference solution.`}
      </strong>
      <ul className="mt-2 grid gap-1">
        {results.map((r, i) => (
          <li key={`${r.test_file}-${r.test_name}-${i}`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2">
            <span aria-hidden className={cx("font-mono", r.passed ? "text-emerald-600" : "text-red-600")}>
              {r.passed ? "✓" : "✗"}
            </span>
            <span className="min-w-0">
              <span className="font-mono">{r.test_name}</span>
              <span className="ml-2 text-xs opacity-70">{r.visibility === "hidden" ? "hidden" : "visible"}</span>
              {!r.passed && r.message && <span className="block truncate font-mono text-xs">{r.message}</span>}
            </span>
          </li>
        ))}
      </ul>
      {wrongChecks.length > 0 && (
        <div className="mt-3 border-t border-current/10 pt-2.5">
          <strong className="font-semibold">
            {wrongChecks.every((c) => c.ok)
              ? `The tests catch all ${wrongChecks.length} wrong solutions.`
              : `${wrongChecks.filter((c) => !c.ok).length} of ${wrongChecks.length} wrong solutions slip through.`}
          </strong>
          <ul className="mt-2 grid gap-1">
            {wrongChecks.map((c) => (
              <li key={c.name} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2">
                <span aria-hidden className={cx("font-mono", c.ok ? "text-emerald-600" : "text-red-600")}>
                  {c.ok ? "✓" : "✗"}
                </span>
                <span className="min-w-0">
                  <span className="font-mono">{c.name}</span>
                  <span className="block text-xs opacity-80">{c.message}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
