import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import type { LectureStatus, RunResponse, SharedExample } from "../shared/types";
import { fetchActiveLecture, fetchLectureStatus, runCode } from "../shared/api";
import { Editor, monaco } from "../shared/monaco";
import { BrandMark, Button, Eyebrow } from "../shared/ui";
import { cx } from "../shared/cx";

// The lecturer's projector screen: whatever task is live, a big countdown,
// and -- once time is up -- the attempts the lecturer picked with "Show on
// full screen" on the live dashboard. It follows the lecture on its own (the
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

  // Everything on the projector has to be readable from the back of the room
  // without anyone scrolling: the page is locked to the viewport and the
  // whole thing (text and code) shrinks until it fits. Re-fit from full size
  // whenever what's on screen changes.
  const viewportRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const fitKey = JSON.stringify([
    status?.finished,
    joinCode,
    question?.id,
    question?.title,
    question?.prompt,
    question?.example,
    compact,
    examples.map((ex) => ex.source_code),
  ]);
  const scale = useFitScale(viewportRef, contentRef, fitKey);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-zinc-50">
      <div className="flex items-center justify-between gap-4 border-b border-zinc-200 bg-white px-5 py-3 sm:px-8">
        <BrandMark />
        <div className="flex items-center gap-3">
          {joinCode && question && (
            <span className="flex items-baseline gap-3 text-lg">
              <span className="text-zinc-500">Join code</span>
              <strong className="font-mono font-bold tracking-[0.12em] text-zinc-950">{joinCode}</strong>
            </span>
          )}
          <FullscreenButton />
        </div>
      </div>

      <div ref={viewportRef} className="min-h-0 flex-1 overflow-hidden">
        {/* Only the centred status screens stretch to fill: with a task up, the
            box is the content's own height, so useFitScale can see spare room. */}
        <div ref={contentRef} className={cx("flex flex-col", !question && "min-h-full")}>
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
                      "font-bold tracking-tight text-zinc-950 [overflow-wrap:anywhere]",
                      compact ? "mb-2 text-4xl" : "mb-4 text-6xl",
                    )}
                  >
                    {question.title}
                  </h1>
                  <p
                    className={cx(
                      "leading-snug whitespace-pre-wrap text-zinc-700 [overflow-wrap:anywhere]",
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
                    "flex-none rounded-xl bg-white text-center shadow-card",
                    timeUp && "ring-1 ring-red-200",
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
                        questionId={question.id}
                        scale={scale}
                      />
                    ))}
                  </div>
                </section>
              )}
            </main>
          )}
        </div>
      </div>
    </div>
  );
}

// Low enough that even two long attempts fit on a small screen: the brief
// is that nothing on the projector is ever cut off or needs scrolling.
const MIN_SCALE = 0.1;

// Sizes the page's root font size (everything here is sized in rem, via
// Tailwind) so that `content` fills `viewport` without overflowing it, and
// returns the factor so the code editors can scale their pixel font sizes to
// match. Shrinks while the content overflows and grows back while there's
// room (never back up to a scale already seen to overflow, so it settles
// instead of flip-flopping as text rewraps). Starts again from full size when
// `resetKey` or the window size changes.
function useFitScale(
  viewportRef: RefObject<HTMLDivElement | null>,
  contentRef: RefObject<HTMLDivElement | null>,
  resetKey: string,
): number {
  const [scale, setScale] = useState(1);
  const [windowSize, setWindowSize] = useState(() => `${window.innerWidth}x${window.innerHeight}`);
  // The smallest scale seen to overflow since the last reset.
  const ceilingRef = useRef(Infinity);

  useEffect(() => {
    const onResize = () => setWindowSize(`${window.innerWidth}x${window.innerHeight}`);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useLayoutEffect(() => {
    ceilingRef.current = Infinity;
    setScale(1);
  }, [resetKey, windowSize]);

  useLayoutEffect(() => {
    document.documentElement.style.fontSize = `${16 * scale}px`;
  }, [scale]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return;
    const check = () => {
      const vh = Math.max(1, viewport.clientHeight);
      const overH = content.scrollHeight / vh;
      const overW = content.scrollWidth / Math.max(1, viewport.clientWidth);
      const over = Math.max(overH, overW);
      if (over > 1.001) {
        // Wrapped text shrinks roughly with the square of the font size, so a
        // square-root step rarely overshoots; the 0.98 cap guarantees progress.
        setScale((s) => {
          ceilingRef.current = Math.min(ceilingRef.current, s);
          return Math.max(MIN_SCALE, s * Math.min(0.98, Math.sqrt(1 / over)));
        });
      } else if (over < 0.95) {
        setScale((s) => {
          const next = Math.min(1, ceilingRef.current * 0.99, s * Math.min(1.3, Math.sqrt(1 / over)));
          return next > s * 1.01 ? next : s;
        });
      }
    };
    check();
    // Monaco sizes itself after mount, and wrapped lines reflow as the font
    // changes -- re-check whenever either box changes size.
    const ro = new ResizeObserver(check);
    ro.observe(viewport);
    ro.observe(content);
    for (const child of Array.from(content.children)) ro.observe(child);
    return () => ro.disconnect();
  }, [viewportRef, contentRef, scale, resetKey, windowSize]);

  return scale;
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
            <code className="block border-l-2 border-zinc-300 pl-4 font-mono whitespace-pre-wrap text-zinc-950 [overflow-wrap:anywhere]">
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
// selection (or the cursor's line), rewrite the code live while talking it
// through, and run it on the failing test's input to show what the fix
// changes. Edits only live on this screen -- students' own waiting screens
// keep showing the original attempt.
export interface ExampleCardProps {
  example: SharedExample;
  label: string | null;
  language: string;
  questionId: string;
  // The projector's fit-to-screen factor (see useFitScale).
  scale: number;
}

function ExampleCard({ example, label, language, questionId, scale }: ExampleCardProps) {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const highlightsRef = useRef<monaco.editor.IEditorDecorationsCollection[]>([]);
  // Monaco won't go below a 6px font, and reads a lineHeight under 8 as a
  // multiple of the font size rather than pixels.
  const fontSize = Math.max(6, Math.round(FONT_SIZE * scale));
  const lineHeight = Math.max(8, Math.round(fontSize * (LINE_HEIGHT / FONT_SIZE)));
  const padding = Math.round(12 * scale);
  // The editor is always as tall as its (wrapped) content, so every line is
  // on screen and it never scrolls; useFitScale shrinks the page instead.
  const [height, setHeight] = useState(() => example.source_code.split("\n").length * lineHeight + 2 * padding);
  const [edited, setEdited] = useState(false);
  const [highlightCount, setHighlightCount] = useState(0);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<RunResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

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
    setRun(null);
    setRunError(null);
  };

  // Ungraded and not stored (the student page's Run endpoint), on the input
  // of the test this attempt failed -- so "Got" can be compared before/after.
  const runIt = async () => {
    const editor = editorRef.current;
    if (!editor || running) return;
    setRunning(true);
    setRunError(null);
    try {
      setRun(
        await runCode({
          student_name: "Lecturer (projector)",
          question_id: questionId,
          source_code: editor.getValue(),
          stdin: example.failing_test?.stdin ?? "",
        }),
      );
    } catch (e) {
      setRun(null);
      setRunError(e instanceof Error ? e.message : "Could not run the code.");
    } finally {
      setRunning(false);
    }
  };

  // The editor's actions are registered once at mount, so route them through
  // refs to always call the current handlers.
  const highlightRef = useRef(highlight);
  highlightRef.current = highlight;
  const runRef = useRef(runIt);
  runRef.current = runIt;

  const failing = example.failing_test;

  return (
    <div className="rounded-xl bg-white p-5 shadow-card">
      <div className="mb-4 flex items-center justify-between gap-4">
        {label && <span className="text-xl font-bold tracking-tight text-zinc-950">{label}</span>}
        <div className="ml-auto flex gap-2">
          <Button onClick={() => void runIt()} disabled={running} title="Run this code on the failing test's input (Ctrl+Enter)">
            {running ? "Running..." : "Run"}
          </Button>
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
              if (editor.getLayoutInfo().contentWidth > 100) setHeight(editor.getContentHeight());
              editor.onDidContentSizeChange((e) => {
                // Monaco's first layout can be a few px wide, which word-wraps
                // every character onto its own line -- don't let that
                // momentary height make the page shrink to fit it.
                if (e.contentHeightChanged && editor.getLayoutInfo().contentWidth > 100) setHeight(e.contentHeight);
              });
              editor.addAction({
                id: "projector-highlight",
                label: "Highlight",
                keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB],
                contextMenuGroupId: "navigation",
                contextMenuOrder: 0,
                run: () => highlightRef.current(),
              });
              editor.addAction({
                id: "projector-run",
                label: "Run",
                keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
                contextMenuGroupId: "navigation",
                contextMenuOrder: 1,
                run: () => void runRef.current(),
              });
            }}
            onChange={(v) => {
              const value = v ?? "";
              setEdited(value !== example.source_code);
            }}
            loading="Loading editor..."
            options={{
              minimap: { enabled: false },
              fontSize,
              lineHeight,
              wordWrap: "on",
              wrappingIndent: "same",
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
              padding: { top: padding, bottom: padding },
              overviewRulerLanes: 0,
              hideCursorInOverviewRuler: true,
              scrollbar: {
                vertical: "hidden",
                horizontal: "hidden",
                handleMouseWheel: false,
                alwaysConsumeMouseWheel: false,
              },
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
      {(run || runError) && <RunResult run={run} error={runError} expected={failing?.expected_stdout ?? null} />}
      {edited && <p className="mt-3 text-[15px] text-zinc-500">Edited here only. Students still see the original.</p>}
    </div>
  );
}

export interface RunResultProps {
  run: RunResponse | null;
  error: string | null;
  // The failing test's expected output, to say whether the run now matches.
  expected: string | null;
}

function RunResult({ run, error, expected }: RunResultProps) {
  if (error || !run) {
    return <p className="mt-4 text-xl text-red-600">{error}</p>;
  }
  if (run.rejected !== null) {
    return <p className="mt-4 text-xl text-red-600">Not run: {run.rejected}</p>;
  }
  const output = run.output_file ? run.output_file_content : run.stdout;
  const errorText =
    (run.compile_output || run.stderr).trim().split("\n").pop() || (run.accepted ? "" : run.message || run.status);
  const matches = expected != null && output != null && output.trimEnd() === expected.trimEnd();
  return (
    <div className="mt-4 border-t border-zinc-200 pt-4">
      <div className="mb-3 flex items-center gap-3 text-xl font-bold tracking-tight">
        Run result
        {expected != null && (
          <span className={cx("text-lg font-semibold", matches ? "text-emerald-600" : "text-red-600")}>
            {matches ? "✓ Matches expected" : "✗ Doesn't match expected"}
          </span>
        )}
      </div>
      <IoTable
        className="text-xl"
        rows={[
          [
            run.output_file ? `Now writes to ${run.output_file}` : "Now gets",
            output == null ? "(file not created)" : output.trim() || "(nothing)",
          ],
          ...(errorText ? ([["Error", errorText]] as Array<[string, string]>) : []),
        ]}
      />
    </div>
  );
}
