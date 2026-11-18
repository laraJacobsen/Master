import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import type { LectureStatus, LiveQuestion, RunResponse, SharedExample, TestCase } from "../shared/types";
import { fetchActiveLecture, fetchLectureStatus, runCode, setScreenQueueCurrent } from "../shared/api";
import { Editor, monaco } from "../shared/monaco";
import { BrandMark, Button, Eyebrow } from "../shared/ui";
import { cx } from "../shared/cx";

// The lecturer's projector screen: whatever task is live, a big countdown,
// and -- once time is up -- the attempts the lecturer queued on the live
// dashboard, one at a time, with Previous/Next to step through the queue
// (here or on the dashboard). It follows the lecture on its own (the
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

  const pollRef = useRef<() => void>(() => {});
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
    pollRef.current = poll;
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
  const position = status?.shown_position ?? null;

  // Time's up and something to go over: the screen is the shown code alone.
  const compact = timeUp && examples.length > 0;

  // Previous/Next through the lecturer's screen queue. The server keeps which
  // entry is up, so students' screens and the dashboard follow along.
  const [stepping, setStepping] = useState(false);
  const [stepError, setStepError] = useState<string | null>(null);
  const canPrev = compact && !stepping && position != null && position.index > 0;
  const canNext = compact && !stepping && position != null && position.index < position.total - 1;
  const step = (by: number) => {
    if (!question) return;
    setStepping(true);
    setStepError(null);
    setScreenQueueCurrent(question.id, { step: by })
      .then(() => pollRef.current())
      .catch((e: Error) => setStepError(e.message))
      .finally(() => setStepping(false));
  };
  const stepRef = useRef({ step, canPrev, canNext });
  stepRef.current = { step, canPrev, canNext };
  // Which task "Show task" was opened for, so a popup left open doesn't come
  // back by itself when the next task's examples go up.
  const [taskOpenFor, setTaskOpenFor] = useState<string | null>(null);

  // The task screens have to be readable from the back of the room without
  // anyone scrolling: the page is locked to the viewport and the whole thing
  // shrinks until it fits. Re-fit from full size whenever what's on screen
  // changes. Once an example is up, the task itself leaves the screen (it's
  // behind "Show task") and the code stays full size: it can be long, so the
  // page scrolls instead, with the controls staying put in the top bar.
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
  ]);
  useFitScale(viewportRef, contentRef, fitKey, !compact);

  // A new entry starts at its top.
  const exampleKey = compact && question ? `${question.id}:${position?.index}:${examples[0]?.source_code}` : null;
  useLayoutEffect(() => {
    if (exampleKey) viewportRef.current?.scrollTo({ top: 0 });
  }, [exampleKey]);

  // Presentation clickers send PageDown/PageUp; the arrow keys work too, unless
  // the lecturer is typing in the editor (or the task popup is open).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.defaultPrevented) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest(".monaco-editor, input, textarea, [role='dialog']")) return;
      const { step: go, canPrev: prev, canNext: next } = stepRef.current;
      if ((e.key === "PageDown" || e.key === "ArrowRight") && next) {
        e.preventDefault();
        go(1);
      } else if ((e.key === "PageUp" || e.key === "ArrowLeft") && prev) {
        e.preventDefault();
        go(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
          {compact && position && position.total > 1 && (
            <div className="flex items-center gap-2" aria-label="Screen queue">
              <Button variant="secondary" onClick={() => step(-1)} disabled={!canPrev} title="Previous in the queue (Page Up / ←)">
                ← Previous
              </Button>
              <span className="min-w-16 text-center font-mono text-lg text-zinc-500 tabular-nums">
                {position.index + 1} / {position.total}
              </span>
              <Button onClick={() => step(1)} disabled={!canNext} title="Next in the queue (Page Down / →)">
                Next →
              </Button>
            </div>
          )}
          {compact && question && <Button variant="secondary" onClick={() => setTaskOpenFor(question.id)}>Show task</Button>}
          <FullscreenButton />
        </div>
      </div>
      {compact && question && taskOpenFor === question.id && (
        <TaskPopup question={question} onClose={() => setTaskOpenFor(null)} />
      )}

      {stepError && <p className="border-b border-red-200 bg-red-50 px-8 py-2 text-red-700">{stepError}</p>}
      {/* The task screens shrink to fit; shown code scrolls, so a long
          attempt stays readable from the back of the room. */}
      <div ref={viewportRef} className={cx("min-h-0 flex-1", compact ? "overflow-y-auto" : "overflow-hidden")}>
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
              {!compact && (
                <section className="flex flex-col items-start justify-between gap-10 lg:flex-row">
                  <div className="min-w-0 flex-1">
                    <h1 className="mb-4 text-6xl font-bold tracking-tight text-zinc-950 [overflow-wrap:anywhere]">
                      {question.title}
                    </h1>
                    <p className="mb-8 text-[2rem] leading-snug whitespace-pre-wrap text-zinc-700 [overflow-wrap:anywhere]">
                      {question.prompt}
                    </p>
                    {question.example && (
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
                      "min-w-64 flex-none rounded-xl bg-white px-8 py-5 text-center shadow-card",
                      timeUp && "ring-1 ring-red-200",
                    )}
                  >
                    <Eyebrow className={cx("text-sm", timeUp && "text-red-600")}>{timeUp ? "Time's up" : "Time left"}</Eyebrow>
                    <div
                      className={cx(
                        "mt-3 font-mono text-[5.5rem] leading-none font-bold tracking-tight tabular-nums",
                        timeUp ? "text-red-600" : "text-zinc-950",
                      )}
                    >
                      {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
                    </div>
                  </div>
                </section>
              )}

              {compact && examples[0] && (
                <section aria-label="Shown attempt">
                  <ExampleCard
                    // Keyed by content and place in the queue, so a poll never
                    // remounts (and wipes the lecturer's edits/highlights on) the
                    // example that's still up.
                    key={exampleKey}
                    example={examples[0]}
                    label={null}
                    language={question.language}
                    questionId={question.id}
                    exampleTest={question.example}
                  />
                </section>
              )}
            </main>
          )}
        </div>
      </div>
    </div>
  );
}

// Low enough that a long task prompt fits on a small screen: the brief is
// that nothing on the task screens is ever cut off or needs scrolling.
const MIN_SCALE = 0.1;

// Sizes the page's root font size (everything here is sized in rem, via
// Tailwind) so that `content` fills `viewport` without overflowing it.
// Shrinks while the content overflows and grows back while there's room
// (never back up to a scale already seen to overflow, so it settles instead
// of flip-flopping as text rewraps). Starts again from full size when
// `resetKey` or the window size changes. Off (`enabled` false), the page
// stays at full size.
function useFitScale(
  viewportRef: RefObject<HTMLDivElement | null>,
  contentRef: RefObject<HTMLDivElement | null>,
  resetKey: string,
  enabled: boolean,
): void {
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
    document.documentElement.style.fontSize = `${16 * (enabled ? scale : 1)}px`;
  }, [scale, enabled]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!enabled || !viewport || !content) return;
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
  }, [viewportRef, contentRef, scale, resetKey, windowSize, enabled]);
}

export interface TaskPopupProps {
  question: LiveQuestion;
  onClose: () => void;
}

// "Show task" while the shown code has the screen: the task on top of it.
// Sized in px, not rem, like the code under it -- whatever useFitScale last
// did to the page's rem doesn't reach it.
function TaskPopup({ question, onClose }: TaskPopupProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex animate-fade-in items-center justify-center bg-zinc-950/40 p-[32px] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-popup-title"
        className="max-h-full w-full max-w-[1200px] animate-fade-in-up overflow-y-auto rounded-xl border border-zinc-200 bg-white p-[48px] shadow-2xl shadow-zinc-950/10"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-[20px] flex items-start justify-between gap-[24px]">
          <h2
            id="task-popup-title"
            className="text-[48px] leading-tight font-bold tracking-tight text-zinc-950 [overflow-wrap:anywhere]"
          >
            {question.title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            autoFocus
            className="flex-none rounded-lg border border-zinc-200 bg-white px-[16px] py-[8px] text-[18px] font-medium text-zinc-700 transition-colors hover:border-zinc-300 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            Close
          </button>
        </div>
        <p className="mb-[32px] text-[30px] leading-snug whitespace-pre-wrap text-zinc-700 [overflow-wrap:anywhere]">
          {question.prompt}
        </p>
        {question.example && (
          <IoTable
            className="text-[24px]"
            rows={[
              ["Example input", question.example.stdin.trimEnd() || "(none)"],
              ["Expected output", question.example.expected_stdout.trimEnd()],
            ]}
          />
        )}
      </div>
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
  // The task's example test: what Run uses when the attempt failed no test
  // (a correct one), so input() has something to read instead of hitting EOF.
  exampleTest: TestCase | null;
}

function ExampleCard({ example, label, language, questionId, exampleTest }: ExampleCardProps) {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const highlightsRef = useRef<monaco.editor.IEditorDecorationsCollection[]>([]);
  const fontSize = FONT_SIZE;
  const lineHeight = LINE_HEIGHT;
  const padding = 12;
  // The editor is always as tall as its (wrapped) content, so it never
  // scrolls on its own -- the page scrolls past it instead. Kept as a count
  // of on-screen (wrapped) lines, so the height is right before Monaco has
  // loaded and reported its size.
  const [visualLines, setVisualLines] = useState(() => example.source_code.split("\n").length);
  const height = visualLines * lineHeight + 2 * padding;
  const measure = (contentHeight: number) => {
    setVisualLines(Math.max(1, Math.round((contentHeight - 2 * padding) / lineHeight)));
  };
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
  // A correct attempt failed nothing, so it runs on the task's example input.
  const runTest = example.failing_test ?? exampleTest;
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
          stdin: runTest?.stdin ?? "",
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
        {example.correct && <span className="text-lg font-semibold text-emerald-600">✓ Passes every test</span>}
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
              if (editor.getLayoutInfo().contentWidth > 100) measure(editor.getContentHeight());
              editor.onDidContentSizeChange((e) => {
                // Monaco's first layout can be a few px wide, which word-wraps
                // every character onto its own line -- don't let that
                // momentary height make the page shrink to fit it.
                if (e.contentHeightChanged && editor.getLayoutInfo().contentWidth > 100) measure(e.contentHeight);
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
      {(run || runError) && (
        <RunResult
          run={run}
          error={runError}
          expected={runTest?.expected_stdout ?? null}
          // The failing test's input is already in the table above.
          input={failing ? null : (runTest?.stdin ?? "")}
        />
      )}
      {edited && <p className="mt-3 text-[15px] text-zinc-500">Edited here only. Students still see the original.</p>}
    </div>
  );
}

export interface RunResultProps {
  run: RunResponse | null;
  error: string | null;
  // The failing test's expected output, to say whether the run now matches.
  expected: string | null;
  // The input it ran on, when it isn't already shown above.
  input: string | null;
}

function RunResult({ run, error, expected, input }: RunResultProps) {
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
          ...(input != null ? ([["Input", input.trimEnd() || "(none)"]] as Array<[string, string]>) : []),
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
