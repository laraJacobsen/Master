import { useState } from "react";
import { fetchTestFile } from "../shared/api";
import type { VisibleTestFile } from "../shared/types";
import { Button, Callout, Eyebrow } from "../shared/ui";
import { cx } from "../shared/cx";

// Long files are cut here in the viewer; the full file is one click away (Download).
const PREVIEW_LINES = 500;

function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} KB`;
  return `${(n / 1_000_000).toFixed(2)} MB`;
}

const keyOf = (f: VisibleTestFile) => `${f.test}/${f.name}`;

export interface TestFilesProps {
  questionId: string;
  files: VisibleTestFile[];
  // Label the files by test ("Example (test 1)", "Test 2", ...) -- used once
  // time is up and every test's files are open.
  groupByTest?: boolean;
}

// The data files a student's program opens by name (backend/test_files.py),
// listed by name and size; clicking one shows its content below the list.
// Content is fetched on first open, not sent with the 2 s status poll.
export function TestFiles({ questionId, files, groupByTest = false }: TestFilesProps) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [contents, setContents] = useState<Record<string, string>>({});
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(f: VisibleTestFile) {
    const key = keyOf(f);
    if (openKey === key) {
      setOpenKey(null);
      return;
    }
    setOpenKey(key);
    setError(null);
    if (key in contents) return;
    setLoadingKey(key);
    try {
      const text = await fetchTestFile(questionId, f.test, f.name);
      setContents((prev) => ({ ...prev, [key]: text }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the file.");
    } finally {
      setLoadingKey(null);
    }
  }

  function download(f: VisibleTestFile, text: string) {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = f.name.split("/").pop() || f.name;
    a.click();
    URL.revokeObjectURL(url);
  }

  const groups: { label: string | null; files: VisibleTestFile[] }[] = groupByTest
    ? Array.from(new Set(files.map((f) => f.test))).map((test) => ({
        label: test === 0 ? "Example (test 1)" : `Test ${test + 1}`,
        files: files.filter((f) => f.test === test),
      }))
    : [{ label: null, files }];

  const open = files.find((f) => keyOf(f) === openKey) ?? null;
  const openText = open ? contents[keyOf(open)] : undefined;
  const lines = openText?.split("\n") ?? [];
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const truncated = lines.length > PREVIEW_LINES;

  return (
    <div className="grid gap-3">
      {groups.map((g) => (
        <div className="grid gap-1.5" key={g.label ?? "all"}>
          {g.label && <Eyebrow>{g.label}</Eyebrow>}
          <div className="flex flex-wrap gap-1.5">
            {g.files.map((f) => {
              const isOpen = openKey === keyOf(f);
              return (
                <button
                  type="button"
                  key={keyOf(f)}
                  className={cx(
                    "inline-flex max-w-full items-baseline gap-2 rounded-lg border px-2.5 py-1.5 text-[13px] transition-colors",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
                    isOpen
                      ? "border-zinc-900 bg-zinc-900 text-white"
                      : "border-zinc-200 bg-white text-zinc-900 hover:border-zinc-300 hover:bg-zinc-50",
                  )}
                  aria-expanded={isOpen}
                  onClick={() => void toggle(f)}
                >
                  <span className="truncate font-mono">{f.name}</span>
                  <span className={cx("font-mono text-[11px]", isOpen ? "text-zinc-400" : "text-zinc-500")}>
                    {formatBytes(f.size)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {open && (
        <div
          className="animate-fade-in overflow-hidden rounded-lg border border-zinc-200"
          role="region"
          aria-label={`Contents of ${open.name}`}
        >
          <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 bg-zinc-50 py-1.5 pr-1.5 pl-3 text-[13px]">
            <span className="truncate font-mono font-medium text-zinc-900">{open.name}</span>
            {openText !== undefined && (
              <span className="font-mono text-xs text-zinc-500">
                {lines.length.toLocaleString()} line{lines.length === 1 ? "" : "s"}
              </span>
            )}
            <span className="ml-auto flex gap-1">
              {openText !== undefined && (
                <Button variant="ghost" size="sm" onClick={() => download(open, openText)}>
                  Download
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => setOpenKey(null)}>
                Close
              </Button>
            </span>
          </div>
          {loadingKey === keyOf(open) && <div className="px-3 py-2 text-[13px] text-zinc-500">Loading...</div>}
          {error && (
            <Callout tone="danger" role="alert" className="m-3">
              {error}
            </Callout>
          )}
          {openText !== undefined && (
            <>
              <pre className="max-h-80 overflow-auto bg-white px-3 py-2.5 font-mono text-[13px] leading-relaxed whitespace-pre text-zinc-900">
                {truncated ? lines.slice(0, PREVIEW_LINES).join("\n") : openText || "(empty file)"}
              </pre>
              {truncated && (
                <div className="border-t border-zinc-200 px-3 py-2 text-[13px] text-zinc-500">
                  Showing the first {PREVIEW_LINES.toLocaleString()} of {lines.length.toLocaleString()} lines.
                  Download the file to see all of it.
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
