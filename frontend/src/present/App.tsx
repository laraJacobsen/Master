import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { LectureStatus, SharedExample } from "../shared/types";
import { fetchActiveLecture, fetchLectureStatus } from "../shared/api";
import { Editor, monaco } from "../shared/monaco";
import { BrandMark, Button, Eyebrow } from "../shared/ui";
import { cx } from "../shared/cx";

// The lecturer's projector screen: whatever task is live, a big countdown,
// and -- once time is up -- the attempts the lecturer picked with "Show to
// students" on the live dashboard. It follows the lecture on its own (the
// same /api/lecture/status poll the student page uses, so it shows exactly
// what students are allowed to see, when they're allowed to see it); the
// lecturer drives everything from lecturer.html in another window.

const POLL_MS = 2000;

function formatMMSS(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

export default function App() {
  const [status, setStatus] = useState<LectureStatus | null>(null);
  const [joinCode, setJoinCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Anchored to the poll's seconds_remaining rather than started_at, so a
  // projector laptop whose clock is off from the server's still counts right.
  const [endMs, setEndMs] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const poll = () => {
      fetchLectureStatus()
        .then((s) => {
          setStatus(s);
          setError(null);
          // `now` moves with endMs: against a tick up to 250ms stale, a time's-up
          // task would read 0:01 for a moment -- unmounting the shown examples
          // (and the lecturer's edits to them) on every poll.
          const t = Date.now();
          setNow(t);
          setEndMs(s.question ? t + s.question.seconds_remaining * 1000 : null);
        })
        .catch((e: Error) => setError(e.message));
      fetchActiveLecture()
        .then((a) => {
          const lecture = a.lecture;
          setJoinCode(lecture && lecture.lobby_opened_at && !lecture.ended_at ? lecture.join_code : null);
        })
        .catch(() => {
          // The status poll above already reports an unreachable server.
        });
    };
    poll();
    const t = window.setInterval(poll, POLL_MS);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, []);

  const question = status?.question ?? null;
  const secondsRemaining = endMs != null ? Math.max(0, Math.ceil((endMs - now) / 1000)) : null;
  const timeUp = secondsRemaining === 0;
  const examples = status?.shown_examples ?? [];

  const compact = timeUp && examples.length > 0;

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50">
      <div className="flex items-center justify-between gap-4 border-b border-zinc-200 bg-white px-5 py-3 sm:px-8">
        <BrandMark />
        <div className="flex items-center gap-3">
          {joinCode && question && (
            <span className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-1.5 text-lg">
              <span className="text-zinc-500">Join code</span>
              <strong className="font-mono font-bold tracking-[0.12em] text-zinc-950">{joinCode}</strong>
            </span>
          )}
          <FullscreenButton />
        </div>
      </div>

      {error && !status && <ProjectorEmpty>{error}</ProjectorEmpty>}

      {status && status.finished && !question && (
        <ProjectorEmpty>
          <h1 className="text-5xl font-bold tracking-tight">That's the lecture. Thanks!</h1>
        </ProjectorEmpty>
      )}

      {status && !status.finished && !question && (
        <ProjectorEmpty>
          {joinCode ? (
            <>
              <p className="text-3xl text-zinc-500">
                Go to <strong className="font-semibold text-zinc-950">{window.location.host}/student.html</strong> and
                enter
              </p>
              <div className="my-6 font-mono text-[clamp(5rem,16vw,12rem)] leading-none font-bold tracking-[0.12em] text-zinc-950">
                {joinCode}
              </div>
              <p className="flex items-center gap-2.5 text-xl text-zinc-500">
                <span className="size-2 animate-pulse-dot rounded-[2px] bg-emerald-500" aria-hidden="true" />
                Waiting for the first task to start.
              </p>
            </>
          ) : (
            <h1 className="text-5xl font-bold tracking-tight">Waiting for the lecture to start.</h1>
          )}
        </ProjectorEmpty>
      )}

      {question && (
        <main className="mx-auto flex w-full max-w-[1500px] flex-col gap-8 p-5 sm:p-10">
          <section className="flex flex-col items-start justify-between gap-10 lg:flex-row">
            <div className="min-w-0 flex-1">
              <h1
                className={cx(
                  "font-bold tracking-tight text-zinc-950",
                  compact ? "mb-2 text-4xl" : "mb-4 text-6xl",
                )}
              >
                {question.title}
              </h1>
              <p
                className={cx(
                  "leading-snug whitespace-pre-wrap text-zinc-700",
                  compact ? "text-2xl" : "mb-8 text-[2rem]",
                )}
              >
                {question.prompt}
              </p>
              {question.example && !compact && (
                <IoTable
                  className="text-2xl"
                  rows={[
                    ["Example input", question.example.stdin.trimEnd() || "(none)"],
                    ["Expected output", question.example.expected_stdout.trimEnd()],
                  ]}
                />
              )}
            </div>
            <div
              className={cx(
                "flex-none rounded-xl border bg-white text-center",
                timeUp ? "border-red-200" : "border-zinc-200",
                compact ? "min-w-44 px-6 py-3" : "min-w-64 px-8 py-5",
              )}
            >
              <Eyebrow className={cx("text-sm", timeUp && "text-red-600")}>{timeUp ? "Time's up" : "Time left"}</Eyebrow>
              <div
                className={cx(
                  "font-mono leading-none font-bold tracking-tight tabular-nums",
                  timeUp ? "text-red-600" : "text-zinc-950",
                  compact ? "mt-2 text-5xl" : "mt-3 text-[5.5rem]",
                )}
              >
                {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
              </div>
            </div>
          </section>

          {compact && (
            <section>
              <h2 className="mb-5 text-4xl font-bold tracking-tight">Let's look at this together</h2>
              <div className="grid gap-6">
                {examples.map((ex, i) => (
                  <ExampleCard
                    // Keyed by content, not just position, so a poll never
                    // remounts (and wipes the lecturer's edits/highlights on) an
                    // example that's still up.
                    key={`${question.id}:${i}:${ex.source_code}`}
                    example={ex}
                    label={examples.length > 1 ? `Example ${i + 1}` : null}
                    language={question.language}
                  />
                ))}
              </div>
            </section>
          )}
        </main>
      )}
    </div>
  );
}

export interface ProjectorEmptyProps {
  children: ReactNode;
}

function ProjectorEmpty({ children }: ProjectorEmptyProps) {
  return (
    <div className="flex flex-1 animate-fade-in flex-col items-center justify-center p-8 text-center">{children}</div>
  );
}

export interface IoTableProps {
  rows: Array<[label: string, value: string]>;
  className?: string;
}

function IoTable({ rows, className }: IoTableProps) {
  return (
    <dl className={cx("grid grid-cols-[max-content_1fr] items-start gap-x-6 gap-y-3", className)}>
      {rows.map(([label, value]) => (
        <Fragment key={label}>
          <dt className="pt-1 font-medium text-zinc-500">{label}</dt>
          <dd>
            <code className="inline-block rounded-lg border border-zinc-200 bg-white px-3 py-1 font-mono whitespace-pre-wrap text-zinc-950">
              {value}
            </code>
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}

function FullscreenButton() {
  const [full, setFull] = useState(() => !!document.fullscreenElement);
  useEffect(() => {
    const onChange = () => setFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  return (
    <Button
      variant="secondary"
      onClick={() => {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen();
      }}
    >
      {full ? "Exit full screen" : "Full screen"}
    </Button>
  );
}

const FONT_SIZE = 20;
const LINE_HEIGHT = 30;

// One shown attempt, in an editable editor: the lecturer can highlight a
// selection (or the cursor's line) and rewrite the code live while talking
// it through. Edits only live on this screen -- students' own waiting
// screens keep showing the original attempt.
export interface ExampleCardProps {
  example: SharedExample;
  label: string | null;
  language: string;
}

function ExampleCard({ example, label, language }: ExampleCardProps) {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const highlightsRef = useRef<monaco.editor.IEditorDecorationsCollection[]>([]);
  const [lineCount, setLineCount] = useState(() => example.source_code.split("\n").length);
  const [edited, setEdited] = useState(false);
  const [highlightCount, setHighlightCount] = useState(0);

  const highlight = () => {
    const editor = editorRef.current;
    const selection = editor?.getSelection();
    if (!editor || !selection) return;
    const decoration: monaco.editor.IModelDeltaDecoration = selection.isEmpty()
      ? {
          range: new monaco.Range(selection.startLineNumber, 1, selection.startLineNumber, 1),
          options: { isWholeLine: true, className: "projector-highlight-line" },
        }
      : {
          range: selection,
          options: { inlineClassName: "projector-highlight" },
        };
    highlightsRef.current.push(editor.createDecorationsCollection([decoration]));
    setHighlightCount(highlightsRef.current.length);
    // Collapse the selection so the yellow isn't hidden under the selection colour.
    editor.setSelection(new monaco.Selection(selection.endLineNumber, selection.endColumn, selection.endLineNumber, selection.endColumn));
    editor.focus();
  };

  const clearHighlights = () => {
    highlightsRef.current.forEach((c) => c.clear());
    highlightsRef.current = [];
    setHighlightCount(0);
  };

  const reset = () => {
    editorRef.current?.setValue(example.source_code);
    clearHighlights();
    setEdited(false);
  };

  // The editor's action registration captures `highlight` once at mount, so
  // route it through a ref to always call the current one.
  const highlightRef = useRef(highlight);
  highlightRef.current = highlight;

  const height = Math.min(Math.max(lineCount, 3), 18) * LINE_HEIGHT + 24;
  const failing = example.failing_test;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        {label && <span className="text-xl font-bold tracking-tight text-zinc-950">{label}</span>}
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={highlight} title="Highlight the selection, or the cursor's line (Ctrl+B)">
            Highlight
          </Button>
          <Button variant="secondary" onClick={clearHighlights} disabled={highlightCount === 0}>
            Clear highlights
          </Button>
          <Button variant="secondary" onClick={reset} disabled={!edited && highlightCount === 0}>
            Reset
          </Button>
        </div>
      </div>
      <div className="flex flex-col items-start gap-8 lg:flex-row">
        <div className="w-full min-w-0 flex-1 overflow-hidden rounded-lg border border-zinc-200">
          <Editor
            height={height}
            defaultLanguage={language}
            defaultValue={example.source_code}
            onMount={(editor) => {
              editorRef.current = editor;
              editor.addAction({
                id: "projector-highlight",
                label: "Highlight",
                keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB],
                contextMenuGroupId: "navigation",
                contextMenuOrder: 0,
                run: () => highlightRef.current(),
              });
            }}
            onChange={(v) => {
              const value = v ?? "";
              setLineCount(value.split("\n").length);
              setEdited(value !== example.source_code);
            }}
            loading="Loading editor..."
            options={{
              minimap: { enabled: false },
              fontSize: FONT_SIZE,
              lineHeight: LINE_HEIGHT,
              tabSize: 4,
              insertSpaces: true,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              lineNumbersMinChars: 2,
              renderLineHighlight: "none",
              quickSuggestions: false,
              suggestOnTriggerCharacters: false,
              wordBasedSuggestions: "off",
              parameterHints: { enabled: false },
              padding: { top: 12, bottom: 12 },
              overviewRulerLanes: 0,
              hideCursorInOverviewRuler: true,
              scrollbar: { vertical: "auto", horizontal: "auto" },
              ariaLabel: "Example code",
            }}
          />
        </div>
        {failing && (
          <IoTable
            className="flex-none text-xl lg:max-w-[40%]"
            rows={[
              ["Input", failing.stdin.trimEnd() || "(none)"],
              ["Expected", failing.expected_stdout.trimEnd()],
              ["Got", failing.stdout.trim() || "(nothing)"],
              ...(failing.stderr
                ? ([["Error", failing.stderr.trim().split("\n").pop() ?? ""]] as Array<[string, string]>)
                : []),
            ]}
          />
        )}
      </div>
      {edited && <p className="mt-3 text-[15px] text-zinc-500">Edited here only. Students still see the original.</p>}
    </div>
  );
}
