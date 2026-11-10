import { useState } from "react";
import { fetchTestFile } from "../shared/api";
import type { VisibleTestFile } from "../shared/types";

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
    <div className="test-files">
      {groups.map((g) => (
        <div className="test-files-group" key={g.label ?? "all"}>
          {g.label && <div className="test-files-group-label">{g.label}</div>}
          <div className="test-files-list">
            {g.files.map((f) => (
              <button
                type="button"
                key={keyOf(f)}
                className={"test-file" + (openKey === keyOf(f) ? " open" : "")}
                aria-expanded={openKey === keyOf(f)}
                onClick={() => void toggle(f)}
              >
                <span className="test-file-name">{f.name}</span>
                <span className="test-file-size">{formatBytes(f.size)}</span>
              </button>
            ))}
          </div>
        </div>
      ))}

      {open && (
        <div className="file-viewer" role="region" aria-label={`Contents of ${open.name}`}>
          <div className="file-viewer-head">
            <span className="test-file-name">{open.name}</span>
            {openText !== undefined && (
              <span className="file-viewer-meta">
                {lines.length.toLocaleString()} line{lines.length === 1 ? "" : "s"}
              </span>
            )}
            <span className="file-viewer-actions">
              {openText !== undefined && (
                <button type="button" className="secondary small" onClick={() => download(open, openText)}>
                  Download
                </button>
              )}
              <button type="button" className="secondary small" onClick={() => setOpenKey(null)}>
                Close
              </button>
            </span>
          </div>
          {loadingKey === keyOf(open) && <div className="file-viewer-note">Loading...</div>}
          {error && <div className="error-box">{error}</div>}
          {openText !== undefined && (
            <>
              <pre className="file-viewer-body">
                {truncated ? lines.slice(0, PREVIEW_LINES).join("\n") : openText || "(empty file)"}
              </pre>
              {truncated && (
                <div className="file-viewer-note">
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
