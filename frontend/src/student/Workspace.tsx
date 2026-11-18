import { useEffect, useImperativeHandle, useRef, useState } from "react";
import type { ReactNode, Ref } from "react";
import { Editor, monaco } from "../shared/monaco";
import { fetchTestFile, runCode } from "../shared/api";
import type { RunResponse, SubmitResponse, VisibleTestFile } from "../shared/types";
import { Button, Spinner } from "../shared/ui";
import { cx } from "../shared/cx";
import { loadDraft, saveDraft } from "./drafts";

// The student's editor, laid out like a small VS Code: one or two editor
// groups with tabs (split to see two files side by side) and a terminal
// underneath that shows Run output and submissions. It opens with just the
// student's program; the task's data files are listed in the task panel
// (student/App.tsx), which opens them here through the WorkspaceHandle.
//
// Files: the student's program (the one file that's graded -- /api/submit
// takes a single source), the "Run input" fed to it as stdin when they press
// Run, the task's example data files (read-only), and, for tasks graded on an
// output file, what the last run wrote to it (read-only).
//
// Monaco keeps one model per file path (@monaco-editor/react's `path` prop),
// so switching tabs keeps each file's undo history and scroll position, and
// the same file open in both groups stays in sync. Paths include the question
// id so a new task never inherits the last one's buffers.

const MAX_GROUPS = 2;

type FileKind = "code" | "input" | "data" | "output";

interface WsFile {
  id: string;
  name: string;
  kind: FileKind;
  readOnly: boolean;
  language: string;
  /** Data files: which test they belong to (always the example, 0). */
  test?: number;
}

interface Group {
  tabs: string[];
  active: string | null;
}

type TermEntry =
  | { id: number; kind: "run"; command: string; pending: boolean; res?: RunResponse; error?: string; check?: ExampleCheck | null }
  | { id: number; kind: "submit"; result: SubmitResponse }
  | { id: number; kind: "submit-error"; message: string };

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: Date }
  | { kind: "restored" }
  | { kind: "failed" };

export interface SaveIndicatorProps {
  state: SaveState;
}

/** "Saved 10:42" next to the Run button -- autosave is local to this browser. */
function SaveIndicator({ state }: SaveIndicatorProps) {
  const text =
    state.kind === "saving"
      ? "Saving..."
      : state.kind === "saved"
        ? `Saved ${state.at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`
        : state.kind === "restored"
          ? "Restored your saved code"
          : state.kind === "failed"
            ? "Couldn't autosave in this browser"
            : "Autosave on";
  return (
    <span
      className={cx(
        "flex items-center gap-1.5 text-xs",
        state.kind === "failed" ? "text-amber-700" : state.kind === "restored" ? "text-brand-700" : "text-zinc-500",
      )}
      title="Your work is saved in this browser as you type, so a reload doesn't lose it."
      aria-live="polite"
    >
      {state.kind === "saving" ? (
        <Spinner className="size-3" />
      ) : (
        <svg className="size-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M4.5 12.5h7a3 3 0 0 0 .4-5.97A4 4 0 0 0 4.2 7.6 2.5 2.5 0 0 0 4.5 12.5z"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
          {state.kind !== "failed" && (
            <path d="M6.2 9.6l1.3 1.2 2.4-2.6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          )}
        </svg>
      )}
      {text}
    </span>
  );
}

interface ExampleCheck {
  matches: boolean;
  expected: string;
}

const CODE_FILE_NAMES: Record<string, string> = { python: "main.py", c: "main.c", java: "Main.java" };

function runCommand(language: string, file: string, hasInput: boolean): string {
  const base =
    language === "c"
      ? `gcc ${file} && ./a.out`
      : language === "java"
        ? `javac ${file} && java ${file.replace(/\.java$/, "")}`
        : `python ${file}`;
  return hasInput ? `${base} < input` : base;
}

/** Same comparison idea as the grader: ignore trailing spaces and blank lines at the end. */
function normalizeOutput(text: string): string {
  return text
    .split("\n")
    .map((l) => l.replace(/\s+$/, ""))
    .join("\n")
    .replace(/\n+$/, "");
}

const editorOptions: monaco.editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  fontSize: 14,
  fontFamily: '"JetBrains Mono Variable", ui-monospace, "SF Mono", Menlo, Consolas, monospace',
  tabSize: 4,
  insertSpaces: true,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  lineNumbersMinChars: 3,
  renderLineHighlight: "none",
  overviewRulerLanes: 0,
  overviewRulerBorder: false,
  hideCursorInOverviewRuler: true,
  padding: { top: 10, bottom: 10 },
  // No autocomplete: it would suggest code, and this is an exercise.
  quickSuggestions: false,
  suggestOnTriggerCharacters: false,
  wordBasedSuggestions: "off",
  parameterHints: { enabled: false },
};

// ------------------------------------------------------------------- Icons

function FileIcon({ kind }: { kind: FileKind }) {
  const tone =
    kind === "code" ? "text-brand-500" : kind === "input" ? "text-violet-500" : kind === "output" ? "text-emerald-600" : "text-zinc-400";
  return (
    <svg className={cx("size-3.5 flex-none", tone)} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3 1.5h5l3 3v8H3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M8 1.5v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg className="size-3 flex-none text-zinc-400" viewBox="0 0 12 12" fill="none" aria-label="Read-only">
      <rect x="2.5" y="5.5" width="7" height="5" rx="1" stroke="currentColor" strokeWidth="1.1" />
      <path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}

function IconButton({
  label,
  onClick,
  children,
  active = false,
  className,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  active?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active || undefined}
      onClick={onClick}
      className={cx(
        "grid size-7 flex-none place-items-center rounded-md transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand-500",
        active ? "bg-brand-50 text-brand-600" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900",
        className,
      )}
    >
      {children}
    </button>
  );
}

// --------------------------------------------------------------- Terminal

export interface TerminalEntryViewProps {
  entry: TermEntry;
  language: string;
  onOpenOutput: () => void;
}

function TerminalEntryView({ entry, language, onOpenOutput }: TerminalEntryViewProps) {
  if (entry.kind === "submit-error") {
    return <div className="text-red-300">Submit failed: {entry.message}</div>;
  }
  if (entry.kind === "submit") {
    const r = entry.result;
    const tone = r.verdict === "correct" ? "text-emerald-300" : r.verdict === "partially_correct" ? "text-amber-300" : "text-red-300";
    return (
      <div>
        <div className="text-zinc-400">
          <span className="text-brand-300">submit</span> attempt {r.attempt_number ?? ""}
        </div>
        <div className={tone}>
          {r.tests_passed}/{r.tests_total} tests passed
          {r.verdict === "correct" ? " -- all correct" : ""}
        </div>
        {r.traceback && <pre className="mt-1 whitespace-pre-wrap text-red-300">{r.traceback}</pre>}
        {r.hidden_crash && (
          <div className="mt-1 text-amber-200">
            Crashed on a hidden test{r.hidden_error ? ` (${r.hidden_error})` : ""}. Its error output isn&apos;t shown.
          </div>
        )}
        {r.verdict !== "correct" && <div className="mt-1 text-zinc-500">See the hint in the task panel.</div>}
      </div>
    );
  }

  const res = entry.res;
  return (
    <div>
      <div className="text-zinc-400">
        <span className="text-emerald-400">$</span> {entry.command}
      </div>
      {entry.pending && (
        <div className="flex items-center gap-2 text-zinc-500">
          <Spinner className="size-3" /> running...
        </div>
      )}
      {entry.error && <div className="text-red-300">{entry.error}</div>}
      {res && res.rejected !== null && (
        <div className="text-amber-200">Not run: {res.rejected.replace(/_/g, " ")}.</div>
      )}
      {res && res.rejected === null && (
        <>
          {res.compile_output && <pre className="whitespace-pre-wrap text-red-300">{res.compile_output}</pre>}
          {res.stdout && <pre className="whitespace-pre-wrap text-zinc-100">{res.stdout}</pre>}
          {res.stderr && <pre className="whitespace-pre-wrap text-red-300">{res.stderr}</pre>}
          {res.output_file && (
            <div className={res.output_file_content === null ? "text-amber-200" : "text-zinc-400"}>
              {res.output_file_content === null ? (
                `Your program didn't create ${res.output_file}.`
              ) : (
                <>
                  Wrote {res.output_file}.{" "}
                  <button
                    type="button"
                    onClick={onOpenOutput}
                    className="rounded-sm text-brand-300 underline underline-offset-2 hover:text-brand-200 focus-visible:outline-2 focus-visible:outline-brand-400"
                  >
                    Open it
                  </button>
                </>
              )}
            </div>
          )}
          {!res.stdout && !res.stderr && !res.compile_output && !res.output_file && (
            <div className="text-zinc-500">(no output)</div>
          )}
          <div className={cx("mt-0.5", res.accepted ? "text-zinc-500" : "text-red-300")}>
            {res.accepted
              ? `Finished${res.time_s ? ` in ${res.time_s}s` : ""}`
              : `${res.status}${res.exit_code != null ? ` (exit code ${res.exit_code})` : ""}`}
            {language === "python" && !res.accepted && res.message ? ` -- ${res.message}` : ""}
          </div>
          {entry.check && (
            <div className={entry.check.matches ? "text-emerald-300" : "text-amber-200"}>
              {entry.check.matches ? (
                "✓ Matches the example's expected output."
              ) : (
                <>
                  ✗ Not the example&apos;s expected output. Expected:
                  <pre className="whitespace-pre-wrap text-zinc-300">{entry.check.expected}</pre>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------- Workspace

export interface WorkspaceProps {
  questionId: string;
  language: string;
  initialCode: string;
  /** Pre-fills the Run input. */
  exampleStdin: string;
  /** The example's expected output -- a run on the example input is checked against it. */
  exampleExpected: string | null;
  outputFile: string | null;
  /** The example's data files (test 0) -- the only ones visible while the task runs. */
  dataFiles: VisibleTestFile[];
  onCodeChange: (code: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  statusText: string;
  /** The latest submission's result; each new one is logged in the terminal. */
  result: SubmitResponse | null;
  submitError: string | null;
  /** Names of the data files currently open in a tab -- the task panel marks them. */
  onOpenDataFilesChange?: (names: string[]) => void;
  /** Where this task's code and Run input are autosaved (see drafts.ts). */
  draftKey: string;
  ref?: Ref<WorkspaceHandle>;
}

/** What the task panel can do to the workspace. */
export interface WorkspaceHandle {
  openDataFile: (name: string) => void;
}

export function Workspace({
  questionId,
  language,
  initialCode,
  exampleStdin,
  exampleExpected,
  outputFile,
  dataFiles,
  onCodeChange,
  onSubmit,
  submitting,
  statusText,
  result,
  submitError,
  onOpenDataFilesChange,
  draftKey,
  ref,
}: WorkspaceProps) {
  const codeName = CODE_FILE_NAMES[language] ?? "main.txt";
  const files: WsFile[] = [
    { id: "code", name: codeName, kind: "code", readOnly: false, language },
    { id: "input", name: "input", kind: "input", readOnly: false, language: "plaintext" },
    ...dataFiles.map((f) => ({
      id: `data:${f.name}`,
      name: f.name,
      kind: "data" as const,
      readOnly: true,
      language: "plaintext",
      test: f.test,
    })),
  ];
  const [lastOutput, setLastOutput] = useState<string | null>(null);
  if (outputFile && lastOutput !== null) {
    files.push({ id: "output", name: outputFile, kind: "output", readOnly: true, language: "plaintext" });
  }
  const fileById = (id: string) => files.find((f) => f.id === id);

  // Just the student's program to start with; everything else is opened on demand.
  const [groups, setGroups] = useState<Group[]>([{ tabs: ["code"], active: "code" }]);
  const [focused, setFocused] = useState(0);
  const [terminalOpen, setTerminalOpen] = useState(true);
  const [dataContent, setDataContent] = useState<Record<string, string>>({});
  const [dataError, setDataError] = useState<Record<string, string>>({});

  const codeRef = useRef(initialCode);
  // Tasks whose example gives nothing on standard input (data comes from the
  // task's files, or there's no input at all) have no use for a Run input:
  // Run just runs the program next to the example's files.
  const usesStdin = exampleStdin.trim() !== "";
  // The Run input, restored from this browser's autosave if there is one.
  const [initialInput] = useState(() => loadDraft(draftKey)?.input || exampleStdin);
  const inputRef = useRef(initialInput);
  const [running, setRunning] = useState(false);
  const [entries, setEntries] = useState<TermEntry[]>([]);
  const nextId = useRef(1);
  const termEndRef = useRef<HTMLDivElement>(null);

  // Each model lives at a per-task path; drop this task's models when leaving it.
  useEffect(() => {
    return () => {
      for (const m of monaco.editor.getModels()) {
        if (m.uri.path.startsWith(`/${questionId}/`)) m.dispose();
      }
    };
  }, [questionId]);

  // A new submission result (or error) goes in the terminal.
  const loggedResult = useRef<SubmitResponse | null>(null);
  useEffect(() => {
    if (!result || loggedResult.current === result) return;
    loggedResult.current = result;
    setEntries((e) => [...e, { id: nextId.current++, kind: "submit", result }]);
    setTerminalOpen(true);
  }, [result]);
  useEffect(() => {
    if (!submitError) return;
    setEntries((e) => [...e, { id: nextId.current++, kind: "submit-error", message: submitError }]);
  }, [submitError]);

  useEffect(() => {
    termEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [entries]);

  // ------------------------------------------------------------ Files/tabs

  async function ensureLoaded(file: WsFile) {
    if (file.kind !== "data" || file.id in dataContent) return;
    try {
      const text = await fetchTestFile(questionId, file.test ?? 0, file.name);
      setDataContent((c) => ({ ...c, [file.id]: text }));
    } catch (e) {
      setDataError((c) => ({ ...c, [file.id]: e instanceof Error ? e.message : "Couldn't load the file." }));
    }
  }

  function openFile(id: string, groupIndex = focused) {
    const file = fileById(id);
    if (!file) return;
    void ensureLoaded(file);
    setGroups((gs) => {
      const g = Math.min(groupIndex, gs.length - 1);
      return gs.map((grp, i) =>
        i === g ? { tabs: grp.tabs.includes(id) ? grp.tabs : [...grp.tabs, id], active: id } : grp,
      );
    });
    setFocused(Math.min(groupIndex, groups.length - 1));
  }

  function closeTab(groupIndex: number, id: string) {
    setGroups((gs) => {
      const next = gs.map((grp, i) => {
        if (i !== groupIndex) return grp;
        const idx = grp.tabs.indexOf(id);
        const tabs = grp.tabs.filter((t) => t !== id);
        const active = grp.active === id ? (tabs[Math.max(0, idx - 1)] ?? null) : grp.active;
        return { tabs, active };
      });
      // An emptied second group goes away, like VS Code.
      return next.length > 1 ? next.filter((g, i) => i === 0 || g.tabs.length > 0) : next;
    });
    setFocused((f) => Math.min(f, groups.length - 1));
  }

  function splitRight(groupIndex: number) {
    const active = groups[groupIndex]?.active;
    if (!active || groups.length >= MAX_GROUPS) return;
    setGroups((gs) => [...gs, { tabs: [active], active }]);
    setFocused(groups.length);
  }

  function closeGroup(groupIndex: number) {
    setGroups((gs) => (gs.length > 1 ? gs.filter((_, i) => i !== groupIndex) : gs));
    setFocused(0);
  }

  useImperativeHandle(ref, () => ({ openDataFile: (name: string) => openFile(`data:${name}`) }));

  const openTabsKey = Array.from(new Set(groups.flatMap((g) => g.tabs))).join("\n");
  useEffect(() => {
    onOpenDataFilesChange?.(
      openTabsKey
        .split("\n")
        .filter((id) => id.startsWith("data:"))
        .map((id) => id.slice("data:".length)),
    );
  }, [openTabsKey, onOpenDataFilesChange]);

  // -------------------------------------------------------------- Autosave

  // "restored" when this task's code came back from an earlier visit.
  const [save, setSave] = useState<SaveState>(() =>
    loadDraft(draftKey) ? { kind: "restored" } : { kind: "idle" },
  );
  const saveTimer = useRef<number | undefined>(undefined);

  function saveNow() {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = undefined;
    const ok = saveDraft(draftKey, { code: codeRef.current, input: inputRef.current });
    setSave(ok ? { kind: "saved", at: new Date() } : { kind: "failed" });
  }

  function scheduleSave() {
    setSave({ kind: "saving" });
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(saveNow, 600);
  }

  // Don't lose the last keystrokes to the debounce: save on leaving the page or the task.
  const saveNowRef = useRef(saveNow);
  saveNowRef.current = saveNow;
  useEffect(() => {
    const flush = () => {
      if (saveTimer.current !== undefined) saveNowRef.current();
    };
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, []);

  // ------------------------------------------------------------------ Run

  async function run() {
    if (running) return;
    const stdin = usesStdin ? inputRef.current : "";
    const entryId = nextId.current++;
    setTerminalOpen(true);
    setRunning(true);
    setEntries((e) => [
      ...e,
      { id: entryId, kind: "run", command: runCommand(language, codeName, stdin.trim() !== ""), pending: true },
    ]);
    const patch = (p: Partial<Extract<TermEntry, { kind: "run" }>>) =>
      setEntries((e) => e.map((x) => (x.id === entryId && x.kind === "run" ? { ...x, ...p } : x)));
    try {
      const res = await runCode({ question_id: questionId, source_code: codeRef.current, stdin });
      let check: ExampleCheck | null = null;
      if (res.rejected === null) {
        if (res.output_file) setLastOutput(res.output_file_content ?? "");
        const produced = res.output_file ? res.output_file_content : res.stdout;
        if (
          res.accepted &&
          exampleExpected !== null &&
          produced !== null &&
          normalizeOutput(stdin) === normalizeOutput(exampleStdin)
        ) {
          check = {
            matches: normalizeOutput(produced) === normalizeOutput(exampleExpected),
            expected: normalizeOutput(exampleExpected),
          };
        }
      }
      patch({ pending: false, res, check });
    } catch (e) {
      patch({ pending: false, error: e instanceof Error ? e.message : "Couldn't run your code." });
    } finally {
      setRunning(false);
    }
  }
  // Ctrl/Cmd+Enter in any editor runs -- through a ref, since the command is
  // registered once per editor mount.
  const runRef = useRef(run);
  runRef.current = run;

  function resetInput() {
    inputRef.current = exampleStdin;
    scheduleSave();
    monaco.editor.getModel(monaco.Uri.parse(`file:///${questionId}/input`))?.setValue(exampleStdin);
  }

  // --------------------------------------------------------------- Render

  function renderGroup(group: Group, gi: number) {
    const file = group.active ? fileById(group.active) : undefined;
    const isFocused = gi === focused;
    let body: ReactNode;
    if (!file) {
      body = (
        <div className="grid h-full place-items-center p-6 text-center text-[13px] text-zinc-400">
          Open a file from the explorer.
        </div>
      );
    } else if (file.kind === "data" && !(file.id in dataContent)) {
      body = (
        <div className="p-4 text-[13px] text-zinc-500">
          {dataError[file.id] ?? (
            <span className="flex items-center gap-2">
              <Spinner /> Loading {file.name}...
            </span>
          )}
        </div>
      );
    } else {
      const readOnlyValue =
        file.kind === "data" ? dataContent[file.id] : file.kind === "output" ? (lastOutput ?? "") : undefined;
      body = (
        <Editor
          height="100%"
          path={`file:///${questionId}/${file.id === "code" || file.id === "input" ? file.id : file.id.replace(/[:/]/g, "_")}`}
          language={file.language}
          defaultValue={file.kind === "code" ? initialCode : file.kind === "input" ? initialInput : undefined}
          value={readOnlyValue}
          loading={<span className="text-sm text-zinc-500">Loading editor...</span>}
          options={{
            ...editorOptions,
            readOnly: file.readOnly,
            domReadOnly: file.readOnly,
            lineNumbers: file.kind === "code" ? "on" : "off",
            placeholder:
              file.kind === "code"
                ? language === "python"
                  ? "# Your code here."
                  : "// Your code here."
                : file.kind === "input"
                  ? "What your program reads when you press Run (stdin)."
                  : undefined,
            ariaLabel: file.kind === "code" ? "Your code" : file.name,
          }}
          onChange={(v) => {
            if (file.kind === "code") {
              codeRef.current = v ?? "";
              onCodeChange(v ?? "");
              scheduleSave();
            } else if (file.kind === "input") {
              inputRef.current = v ?? "";
              scheduleSave();
            }
          }}
          onMount={(ed, m) => {
            ed.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.Enter, () => void runRef.current());
            ed.onDidFocusEditorText(() => setFocused(gi));
          }}
        />
      );
    }

    return (
      <div
        key={gi}
        className={cx("flex min-w-0 flex-1 flex-col", gi > 0 && "border-l border-zinc-200")}
        onMouseDown={() => setFocused(gi)}
      >
        <div className="flex h-9 flex-none items-stretch border-b border-zinc-200 bg-zinc-50">
          <div className="flex min-w-0 flex-1 overflow-x-auto" role="tablist" aria-label={`Editor group ${gi + 1}`}>
            {group.tabs.map((id) => {
              const f = fileById(id);
              if (!f) return null;
              const on = group.active === id;
              return (
                <div
                  key={id}
                  className={cx(
                    "group flex flex-none items-center gap-1.5 border-r border-zinc-200 pr-1 pl-3 text-[13px]",
                    on ? "bg-white text-zinc-900" : "text-zinc-500 hover:bg-white/60 hover:text-zinc-800",
                    on && isFocused && "shadow-[inset_0_2px_0_var(--color-brand-500)]",
                  )}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={on}
                    onClick={() => openFile(id, gi)}
                    className="flex items-center gap-1.5 rounded-sm py-1 focus-visible:outline-2 focus-visible:outline-brand-500"
                  >
                    <FileIcon kind={f.kind} />
                    <span className={cx("font-mono text-xs", f.kind === "input" && "font-sans")}>
                      {f.kind === "input" ? "Run input" : f.name}
                    </span>
                    {f.readOnly && <LockIcon />}
                  </button>
                  {f.kind === "code" && gi === 0 ? (
                    // The program stays pinned in the first group, so it's always one click away.
                    <span className="w-1" aria-hidden="true" />
                  ) : (
                    <button
                      type="button"
                      aria-label={`Close ${f.name}`}
                      onClick={() => closeTab(gi, id)}
                      className={cx(
                        "grid size-5 place-items-center rounded text-zinc-400 hover:bg-zinc-200 hover:text-zinc-800",
                        "focus-visible:outline-2 focus-visible:outline-brand-500",
                        on ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
                      )}
                    >
                      <svg className="size-2.5" viewBox="0 0 10 10" aria-hidden="true">
                        <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                      </svg>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex flex-none items-center gap-0.5 px-1">
            {groups.length < MAX_GROUPS && group.active && (
              <IconButton label="Split editor right" onClick={() => splitRight(gi)}>
                <svg className="size-4" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <rect x="2" y="2.5" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
                  <path d="M8 2.5v11" stroke="currentColor" strokeWidth="1.2" />
                </svg>
              </IconButton>
            )}
            {groups.length > 1 && (
              <IconButton label="Close this editor group" onClick={() => closeGroup(gi)}>
                <svg className="size-3" viewBox="0 0 10 10" aria-hidden="true">
                  <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              </IconButton>
            )}
          </div>
        </div>
        {file?.kind === "input" && (
          <div className="flex items-center gap-2 border-b border-zinc-100 bg-violet-50/50 px-3 py-1.5 text-xs text-zinc-500">
            <span className="flex-1">Typed into your program when you press Run. Starts as the example&apos;s input.</span>
            <button
              type="button"
              onClick={resetInput}
              className="rounded-sm font-medium text-brand-600 hover:underline focus-visible:outline-2 focus-visible:outline-brand-500"
            >
              Reset to example
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 bg-white">{body}</div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl bg-white shadow-card">
      <div className="flex min-h-0 flex-1">{groups.map(renderGroup)}</div>

      {/* Terminal */}
      <div className="flex flex-none flex-col border-t border-zinc-200 bg-zinc-950">
        <div className="flex h-8 flex-none items-center gap-2 px-3">
          <button
            type="button"
            onClick={() => setTerminalOpen((o) => !o)}
            aria-expanded={terminalOpen}
            className="flex items-center gap-1.5 rounded-sm text-[11px] font-semibold tracking-[0.1em] text-zinc-400 uppercase hover:text-zinc-200 focus-visible:outline-2 focus-visible:outline-brand-400"
          >
            <svg className={cx("size-2.5 transition-transform", !terminalOpen && "-rotate-90")} viewBox="0 0 10 10" aria-hidden="true">
              <path d="M2 3.5l3 3 3-3" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
            </svg>
            Terminal
          </button>
          {entries.length > 0 && (
            <button
              type="button"
              onClick={() => setEntries([])}
              className="ml-auto rounded-sm text-[11px] text-zinc-500 hover:text-zinc-200 focus-visible:outline-2 focus-visible:outline-brand-400"
            >
              Clear
            </button>
          )}
        </div>
        {terminalOpen && (
          <div
            className="h-52 overflow-y-auto px-3 pb-3 font-mono text-[12.5px] leading-relaxed"
            role="log"
            aria-live="polite"
            aria-label="Terminal output"
          >
            {entries.length === 0 ? (
              <div className="text-zinc-500">
                Press <span className="text-zinc-300">Run</span> to try your code on{" "}
                {usesStdin ? "the Run input" : dataFiles.length ? "the example's files" : "its own"}. Runs aren&apos;t
                graded or seen by your lecturer, only Submit is.
              </div>
            ) : (
              <div className="grid gap-3">
                {entries.map((e) => (
                  <TerminalEntryView key={e.id} entry={e} language={language} onOpenOutput={() => openFile("output")} />
                ))}
              </div>
            )}
            <div ref={termEndRef} />
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-none flex-wrap items-center gap-x-3 gap-y-2 border-t border-zinc-200 bg-white px-3 py-2.5">
        <SaveIndicator state={save} />
        {usesStdin && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => openFile("input")}
            title="What your program reads when you press Run"
            className={cx(groups.some((g) => g.active === "input") && "bg-brand-50 text-brand-700")}
          >
            <FileIcon kind="input" />
            Run input
          </Button>
        )}
        <div className="ml-auto flex items-center gap-2">
          {submitting && statusText && <span className="hidden text-xs text-zinc-500 lg:inline">{statusText}</span>}
          <Button
            variant="secondary"
            onClick={() => void run()}
            disabled={running || submitting}
            title={`Run your code on ${usesStdin ? "the Run input" : dataFiles.length ? "the example's files" : "its own"} (Ctrl/⌘+Enter). Not graded.`}
          >
            {running ? (
              <Spinner />
            ) : (
              <svg className="size-3 text-emerald-600" viewBox="0 0 12 12" aria-hidden="true">
                <path d="M3 1.8v8.4L10 6z" fill="currentColor" />
              </svg>
            )}
            Run
            <kbd className="ml-0.5 hidden font-sans text-[11px] text-zinc-400 sm:inline">Ctrl+↵</kbd>
          </Button>
          <Button onClick={onSubmit} disabled={submitting}>
            {submitting && <Spinner />}
            {submitting ? "Submitting..." : "Submit"}
          </Button>
        </div>
      </div>
    </div>
  );
}
