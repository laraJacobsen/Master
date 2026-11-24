import type { TaskFile, TaskMeta, ValidationTestResult } from "../shared/types";
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
  { key: "hidden", label: "Hidden tests", note: "Students only see how many failed.", folder: "hidden_tests/", match: (f) => f.role === "hidden_test" },
  { key: "data", label: "Data", note: "", folder: "data/", match: (f) => f.role === "data" },
  { key: "ref", label: "Reference solution", note: "Never sent to students.", folder: "reference/", match: (f) => f.role === "reference" },
];

export interface TaskFolderSummaryProps {
  files: TaskFile[];
  meta: TaskMeta;
}

export function TaskFolderSummary({ files, meta }: TaskFolderSummaryProps) {
  const editable = new Set(meta.editable ?? []);
  const testCount = meta.test_ids?.length ?? null;
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
                    <li key={f.path} className="flex items-baseline justify-between gap-3 text-[13px]">
                      <span className="truncate font-mono text-zinc-800">
                        <span className="text-zinc-400">{group.folder}</span>
                        {f.path}
                      </span>
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
    </div>
  );
}

export interface TestCheckResultsProps {
  results: ValidationTestResult[];
}

/** The reference solution's run, one row per test: every test must pass. */
export function TestCheckResults({ results }: TestCheckResultsProps) {
  const failing = results.filter((r) => !r.passed);
  const ok = results.length > 0 && failing.length === 0;
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
    </div>
  );
}
