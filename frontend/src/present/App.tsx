import { useEffect, useRef, useState } from "react";
import type { LectureStatus, SharedExample } from "../shared/types";
import { fetchActiveLecture, fetchLectureStatus } from "../shared/api";
import { Editor, monaco } from "../shared/monaco";

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

  return (
    <div className="projector">
      <div className="projector-bar">
        <span className="projector-brand">
          <span className="top-nav-mark" aria-hidden="true">IL</span>
          Interactive Lecture
        </span>
        <div className="projector-bar-right">
          {joinCode && question && (
            <span className="join-code-pill">
              Join code <strong>{joinCode}</strong>
            </span>
          )}
          <FullscreenButton />
        </div>
      </div>

      {error && !status && <div className="projector-empty">{error}</div>}

      {status && status.finished && !question && (
        <div className="projector-empty">
          <h1>That's the lecture. Thanks!</h1>
        </div>
      )}

      {status && !status.finished && !question && (
        <div className="projector-empty">
          {joinCode ? (
            <>
              <p className="join-instructions">
                Go to <strong>{window.location.host}/student.html</strong> and enter
              </p>
              <div className="join-code-big">{joinCode}</div>
              <p className="join-sub">Waiting for the first task to start.</p>
            </>
          ) : (
            <h1>Waiting for the lecture to start.</h1>
          )}
        </div>
      )}

      {question && (
        <main className="projector-main">
          <section className={timeUp && examples.length > 0 ? "task-panel compact" : "task-panel"}>
            <div className="task-text">
              <h1>{question.title}</h1>
              <p className="task-prompt">{question.prompt}</p>
              {question.example && !(timeUp && examples.length > 0) && (
                <dl className="io-table">
                  <dt>Example input</dt>
                  <dd>
                    <code>{question.example.stdin.trimEnd() || "(none)"}</code>
                  </dd>
                  <dt>Expected output</dt>
                  <dd>
                    <code>{question.example.expected_stdout.trimEnd()}</code>
                  </dd>
                </dl>
              )}
            </div>
            <div className={timeUp ? "timer time-up" : "timer"}>
              <div className="timer-label">{timeUp ? "Time's up" : "Time left"}</div>
              <div className="timer-value">{secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}</div>
            </div>
          </section>

          {timeUp && examples.length > 0 && (
            <section className="examples">
              <h2>Let's look at this together</h2>
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
            </section>
          )}
        </main>
      )}
    </div>
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
    <button
      className="secondary"
      onClick={() => {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen();
      }}
    >
      {full ? "Exit full screen" : "Full screen"}
    </button>
  );
}

const FONT_SIZE = 20;
const LINE_HEIGHT = 30;

// One shown attempt, in an editable editor: the lecturer can highlight a
// selection (or the cursor's line) and rewrite the code live while talking
// it through. Edits only live on this screen -- students' own waiting
// screens keep showing the original attempt.
function ExampleCard({
  example,
  label,
  language,
}: {
  example: SharedExample;
  label: string | null;
  language: string;
}) {
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
    <div className="example-card">
      <div className="example-head">
        {label && <span className="example-label">{label}</span>}
        <div className="example-tools">
          <button className="secondary" onClick={highlight} title="Highlight the selection, or the cursor's line (Ctrl+B)">
            Highlight
          </button>
          <button className="secondary" onClick={clearHighlights} disabled={highlightCount === 0}>
            Clear highlights
          </button>
          <button className="secondary" onClick={reset} disabled={!edited && highlightCount === 0}>
            Reset
          </button>
        </div>
      </div>
      <div className="example-body">
        <div className="example-editor">
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
          <dl className="io-table example-io">
            <dt>Input</dt>
            <dd>
              <code>{failing.stdin.trimEnd() || "(none)"}</code>
            </dd>
            <dt>Expected</dt>
            <dd>
              <code>{failing.expected_stdout.trimEnd()}</code>
            </dd>
            <dt>Got</dt>
            <dd>
              <code>{failing.stdout.trim() || "(nothing)"}</code>
            </dd>
            {failing.stderr && (
              <>
                <dt>Error</dt>
                <dd>
                  <code>{failing.stderr.trim().split("\n").pop()}</code>
                </dd>
              </>
            )}
          </dl>
        )}
      </div>
      {edited && <div className="example-note">Edited here only. Students still see the original.</div>}
    </div>
  );
}
