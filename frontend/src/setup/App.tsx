import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import type { LectureRow, QuestionRow, QuestionStatus, ValidationTestResult } from "../shared/types";
import {
  createQuestion,
  deleteLecture as deleteLectureApi,
  deleteQuestion as deleteQuestionApi,
  fetchActiveLecture,
  fetchQuestionList,
  openLobby as openLobbyApi,
  startQuestion as startQuestionApi,
  updateQuestion,
  validateQuestion as validateQuestionApi,
} from "../shared/api";
import { NavBar } from "../shared/NavBar";
import { ConfirmDialog } from "../shared/ConfirmDialog";

// Lecture preparation. Top: the lecture itself and its one next action (open
// the lobby, or go back to it / the live dashboard). Left: the questions in
// the order they'll run. Right: the question editor, split into three steps
// so a new question isn't one 15-field form -- what students see, the tests
// and a known-correct solution (checked in one click), then timing. Rarely
// changed grading limits sit under "Advanced" in step 3.

interface TestCaseDraft {
  stdin: string;
  expected: string;
}

interface ValidationResultState {
  pass: boolean;
  total: number;
  failing: ValidationTestResult[];
}

const emptyTestCase = (): TestCaseDraft => ({ stdin: "", expected: "" });

const STEPS = ["Task", "Tests & solution", "Timing & class"] as const;

// Autosave waits this long after the last edit, so typing doesn't send a
// request per keystroke.
const AUTOSAVE_MS = 900;

// Plain-language status for the question list.
function statusLabel(q: QuestionRow): { text: string; kind: string } {
  if (q.status === "live") return { text: "Live", kind: "live" };
  if (q.status === "closed") return { text: "Done", kind: "done" };
  if (q.status === "skipped") return { text: "Skipped", kind: "done" };
  return q.validated ? { text: "Ready", kind: "ready" } : { text: "Needs a check", kind: "check" };
}

export default function App() {
  const [questions, setQuestions] = useState<QuestionRow[]>([]);

  const [currentId, setCurrentId] = useState<string | null>(null);
  const [currentStatus, setCurrentStatus] = useState<QuestionStatus>("draft");
  const [currentValidated, setCurrentValidated] = useState(false);
  const [step, setStep] = useState(0);

  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [language, setLanguage] = useState("python");
  const [testCases, setTestCases] = useState<TestCaseDraft[]>([emptyTestCase()]);
  const [timeLimit, setTimeLimit] = useState("5");
  const [memoryLimit, setMemoryLimit] = useState("125");
  const [lineLimit, setLineLimit] = useState("200");
  const [packages, setPackages] = useState("");
  const [expectedStudents, setExpectedStudents] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("10");
  const [idleNudgeMinutes, setIdleNudgeMinutes] = useState("3");
  const [referenceSolution, setReferenceSolution] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  // Autosave bookkeeping. editVersion counts edits; savedVersion is the edit
  // count the last successful save contained -- so a save that was in flight
  // while the lecturer kept typing doesn't mark those newer edits as saved,
  // and the server's reply never overwrites what's in the form.
  const [editVersion, setEditVersion] = useState(0);
  const [savedVersion, setSavedVersion] = useState(0);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "error">("idle");
  const savingRef = useRef(false);
  // Bumped whenever the editor switches question, so a save that finishes
  // after the switch doesn't write its id into the newly opened question.
  const generationRef = useRef(0);
  const dirty = editVersion !== savedVersion;
  function markEdited() {
    setEditVersion((v) => v + 1);
  }

  const [formStatusText, setFormStatusText] = useState("");
  const [formStatusKind, setFormStatusKind] = useState<"muted" | "ok" | "bad">("muted");
  const [busy, setBusy] = useState<null | "saving" | "checking" | "starting">(null);
  const [validationResult, setValidationResult] = useState<ValidationResultState | null>(null);

  // The lecture this setup session belongs to (see the lobby-scoping-
  // decision) -- fetched once so the lecture bar knows whether the lobby's
  // already open (link back to it instead of the button).
  const [activeLecture, setActiveLecture] = useState<LectureRow | null>(null);
  // If a question is already live, "back to the lobby" must actually mean
  // "back to the live dashboard" -- see the lobby-view fix in
  // lecturer/App.tsx for why (landing on the pre-start lobby again would
  // let "Start lecture" fire a second time on top of the question already
  // running).
  const [liveQuestionId, setLiveQuestionId] = useState<string | null>(null);
  const [openingLobby, setOpeningLobby] = useState(false);
  const [lobbyError, setLobbyError] = useState<string | null>(null);
  const [deletingLecture, setDeletingLecture] = useState(false);
  const [deleteLectureError, setDeleteLectureError] = useState<string | null>(null);
  const [addingTestQuestions, setAddingTestQuestions] = useState(false);
  const [confirmDeleteLectureOpen, setConfirmDeleteLectureOpen] = useState(false);
  const [questionPendingDelete, setQuestionPendingDelete] = useState<QuestionRow | null>(null);

  const locked = currentStatus !== "draft";

  function setStatus(text: string, kind: "muted" | "ok" | "bad" = "muted") {
    setFormStatusText(text);
    setFormStatusKind(kind);
  }

  function loadQuestionList() {
    fetchQuestionList()
      .then(setQuestions)
      .catch(() => {
        // Backend not reachable -- leave the last-known list in place.
      });
  }

  function loadActiveLecture() {
    fetchActiveLecture()
      .then((a) => {
        setActiveLecture(a.lecture);
        setLiveQuestionId(a.live_question_id);
      })
      .catch(() => {
        // Not critical -- the lecture bar just won't show.
      });
  }

  useEffect(() => {
    loadQuestionList();
    loadActiveLecture();
  }, []);

  async function handleOpenLobby() {
    if (!activeLecture) return;
    setOpeningLobby(true);
    setLobbyError(null);
    try {
      await openLobbyApi(activeLecture.id);
      window.location.href = `lecturer.html?lobby=${activeLecture.id}`;
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : "Could not open the lobby.");
      setOpeningLobby(false);
    }
  }

  // Only offered while nothing's live yet (see the JSX below) -- once a
  // question starts, the backend itself refuses this (see
  // api_lecturer_delete_lecture in main.py), and archive is the right tool
  // instead.
  async function confirmDeleteLecture() {
    setConfirmDeleteLectureOpen(false);
    if (!activeLecture) return;
    setDeletingLecture(true);
    setDeleteLectureError(null);
    try {
      await deleteLectureApi(activeLecture.id);
      window.location.href = "index.html";
    } catch (e) {
      setDeleteLectureError(e instanceof Error ? e.message : "Could not delete this lecture.");
      setDeletingLecture(false);
    }
  }

  function handleDeleteQuestion(q: QuestionRow, e: MouseEvent) {
    e.stopPropagation(); // don't also open it in the editor
    setQuestionPendingDelete(q);
  }

  async function confirmDeleteQuestion() {
    const q = questionPendingDelete;
    setQuestionPendingDelete(null);
    if (!q) return;
    try {
      await deleteQuestionApi(q.id);
      if (currentId === q.id) resetForm();
      loadQuestionList();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not delete this question.", "bad");
    }
  }

  // Dev convenience only: three real, correct-by-construction questions
  // (validated immediately so they're startable right away) so testing the
  // whole lobby/start/submit flow doesn't require typing a question in by
  // hand every time. Not something a real class needs -- just faster manual
  // testing.
  async function addTestQuestions() {
    setAddingTestQuestions(true);
    setStatus("Adding...");
    const samples = [
      {
        title: "Double It",
        prompt: "Read one integer and print double it.",
        test_cases: [
          { stdin: "3\n", expected: "6" },
          { stdin: "10\n", expected: "20" },
        ],
        reference_solution: "print(int(input()) * 2)",
      },
      {
        title: "Sum Two",
        prompt: "Read two integers on one line and print their sum.",
        test_cases: [
          { stdin: "3 4\n", expected: "7" },
          { stdin: "10 -2\n", expected: "8" },
        ],
        reference_solution: "a, b = map(int, input().split()); print(a + b)",
      },
      {
        title: "Reverse It",
        prompt: "Read a line of text and print it reversed.",
        test_cases: [
          { stdin: "hello\n", expected: "olleh" },
          { stdin: "abc\n", expected: "cba" },
        ],
        reference_solution: "print(input()[::-1])",
      },
    ];
    try {
      for (const sample of samples) {
        const created = await createQuestion({
          title: sample.title,
          prompt: sample.prompt,
          language: "python",
          test_cases: sample.test_cases.map((tc) => ({ stdin: tc.stdin, expected_stdout: tc.expected })),
          reference_solution: sample.reference_solution,
          cpu_time_limit_s: 5,
          memory_limit_kb: 128000,
          extra_packages: [],
          line_limit: 200,
          expected_students: null,
          duration_seconds: 600,
          idle_nudge_seconds: 180,
        });
        await validateQuestionApi(created.id);
      }
      setStatus("Added 3 sample questions.", "ok");
      loadQuestionList();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not add test questions.", "bad");
    } finally {
      setAddingTestQuestions(false);
    }
  }

  function resetForm() {
    setCurrentId(null);
    setCurrentStatus("draft");
    setCurrentValidated(false);
    setStep(0);
    setTitle("");
    setPrompt("");
    setLanguage("python");
    setTimeLimit("5");
    setMemoryLimit("125");
    setLineLimit("200");
    setPackages("");
    setExpectedStudents("");
    setDurationMinutes("10");
    setIdleNudgeMinutes("3");
    setReferenceSolution("");
    setTestCases([emptyTestCase()]);
    setShowAdvanced(false);
    generationRef.current += 1;
    setEditVersion(0);
    setSavedVersion(0);
    setSaveState("idle");
    setStatus("");
    setValidationResult(null);
  }

  function loadQuestionIntoForm(q: QuestionRow, keepStep = false) {
    setCurrentId(q.id);
    setCurrentStatus(q.status);
    setCurrentValidated(q.validated);
    if (!keepStep) setStep(0);
    setTitle(q.title);
    setPrompt(q.prompt);
    setLanguage(q.language);
    setTimeLimit(String(q.cpu_time_limit_s));
    // 1024, not 1000 -- the backend's own default/cap (128000 KB "~125MB",
    // 256000 KB max) are 1024-based, so 1000 would drift the displayed MB
    // value away from what's actually stored (128000/1024 = 125 exactly).
    setMemoryLimit(String(Math.round(q.memory_limit_kb / 1024)));
    setLineLimit(String(q.line_limit));
    setPackages(q.extra_packages.join(", "));
    setExpectedStudents(q.expected_students != null ? String(q.expected_students) : "");
    setDurationMinutes(String(q.duration_seconds / 60));
    setIdleNudgeMinutes(String(q.idle_nudge_seconds / 60));
    setReferenceSolution(q.reference_solution || "");
    setTestCases(
      q.test_cases.length
        ? q.test_cases.map((tc) => ({ stdin: tc.stdin, expected: tc.expected_stdout }))
        : [emptyTestCase()]
    );
    if (!keepStep) {
      generationRef.current += 1;
      setEditVersion(0);
      setSavedVersion(0);
      setSaveState("idle");
      setStatus("");
      setValidationResult(null);
    }
  }

  function addTestCaseRow() {
    setTestCases((prev) => [...prev, emptyTestCase()]);
  }
  function removeTestCaseRow(index: number) {
    markEdited();
    setTestCases((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== index) : [emptyTestCase()]));
  }
  function updateTestCase(index: number, field: "stdin" | "expected", value: string) {
    setTestCases((prev) => prev.map((tc, i) => (i === index ? { ...tc, [field]: value } : tc)));
  }

  function formPayload() {
    const packageList = packages
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      title: title.trim(),
      prompt: prompt.trim(),
      language,
      // An untouched blank row isn't a test case.
      test_cases: testCases
        .filter((tc) => tc.stdin.trim() || tc.expected.trim())
        .map((tc) => ({ stdin: tc.stdin, expected_stdout: tc.expected })),
      reference_solution: referenceSolution || null,
      cpu_time_limit_s: parseFloat(timeLimit),
      memory_limit_kb: Math.round(parseFloat(memoryLimit) * 1024),
      extra_packages: packageList,
      line_limit: parseInt(lineLimit, 10),
      expected_students: expectedStudents ? parseInt(expectedStudents, 10) : null,
      duration_seconds: Math.round(parseFloat(durationMinutes) * 60),
      // Blank counts as off, same as 0.
      idle_nudge_seconds: Math.max(0, Math.round((parseFloat(idleNudgeMinutes) || 0) * 60)),
    };
  }

  // What each step still needs -- drives the step checkmarks.
  const payloadNow = formPayload();
  const stepDone = [
    Boolean(payloadNow.title && payloadNow.prompt),
    Boolean(payloadNow.test_cases.length && referenceSolution.trim() && currentValidated),
    // Defaults fill this step in already, so it only counts once the question is saved.
    Boolean(currentId && payloadNow.duration_seconds > 0),
  ];

  // A question can be saved as soon as it has a title -- everything else can
  // be filled in later (it only runs once "Check solution" passes).
  const canAutosave = currentStatus === "draft" && title.trim() !== "" && payloadNow.duration_seconds > 0;

  // Saves the form as it is now (create or update). Never touches the form's
  // fields, so edits made while it's in flight survive. Returns the saved row,
  // or null if it failed or another save was already running.
  async function persist(): Promise<QuestionRow | null> {
    if (savingRef.current) return null;
    savingRef.current = true;
    setSaveState("saving");
    const version = editVersion;
    const generation = generationRef.current;
    try {
      const payload = formPayload();
      const data = currentId ? await updateQuestion(currentId, payload) : await createQuestion(payload);
      if (generation === generationRef.current) {
        setCurrentId(data.id);
        setCurrentStatus(data.status);
        setCurrentValidated(data.validated);
        setSavedVersion(version);
      }
      setSaveState("idle");
      loadQuestionList();
      return data;
    } catch (e) {
      setSaveState("error");
      setStatus(e instanceof Error ? `Not saved: ${e.message}` : "Not saved.", "bad");
      return null;
    } finally {
      savingRef.current = false;
    }
  }

  async function waitForSave() {
    while (savingRef.current) await new Promise((resolve) => setTimeout(resolve, 80));
  }

  // Before leaving this question (another one, or a new one): save what's
  // there if it can be saved. A question without a title has nothing worth
  // keeping yet.
  async function flushThen(next: () => void) {
    await waitForSave();
    if (dirty && canAutosave) await persist();
    next();
  }

  // Autosave: shortly after the last edit.
  useEffect(() => {
    if (!dirty || !canAutosave || saveState === "saving") return;
    const t = window.setTimeout(() => {
      persist();
    }, AUTOSAVE_MS);
    return () => window.clearTimeout(t);
    // persist() reads the current render's form state; re-running on each
    // edit (editVersion) is what keeps that fresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editVersion, savedVersion, saveState, canAutosave]);

  // Closing the tab with an unsaved edit or a save still in flight.
  useEffect(() => {
    if (!dirty && saveState !== "saving") return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, saveState]);

  // Step 2's one button: save, then run the reference solution against the
  // tests (the backend refuses to validate an unsaved question anyway).
  async function checkSolution() {
    const payload = formPayload();
    if (!payload.title || !payload.prompt) {
      setStep(0);
      setStatus("Add a title and task description first.", "bad");
      return;
    }
    if (payload.test_cases.length < 2) {
      // The first test is the example students see and isn't graded (main._graded).
      setStatus("Add at least 2 test cases. The first is shown to students and isn't graded.", "bad");
      return;
    }
    if (!referenceSolution.trim()) {
      setStatus("Add a reference solution first.", "bad");
      return;
    }
    if (!canAutosave) {
      setStep(2);
      setStatus("Time limit must be at least 1 minute.", "bad");
      return;
    }
    await waitForSave();
    const saved = dirty || !currentId ? await persist() : questions.find((q) => q.id === currentId) ?? null;
    if (!saved) return;
    setBusy("checking");
    setStatus("Checking...");
    setValidationResult(null);
    try {
      const data = await validateQuestionApi(saved.id);
      setStatus("");
      setValidationResult({
        pass: data.validated,
        total: (data.results || []).length,
        failing: (data.results || []).filter((r) => !r.passed),
      });
      setCurrentValidated(data.validated);
      loadQuestionList();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Check failed.", "bad");
    } finally {
      setBusy(null);
    }
  }

  async function startQuestion() {
    if (!currentId) return;
    setBusy("starting");
    setStatus("Starting...");
    try {
      await startQuestionApi(currentId);
      setStatus("Live.", "ok");
      loadQuestionList();
      setTimeout(() => {
        window.location.href = `lecturer.html?question_id=${encodeURIComponent(currentId)}`;
      }, 700);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Could not start this question.", "bad");
      setBusy(null);
    }
  }

  const readyCount = questions.filter((q) => q.status === "draft" && q.validated).length;
  const draftCount = questions.filter((q) => q.status === "draft").length;
  const lobbyOpen = Boolean(activeLecture?.lobby_opened_at);
  const canStartNow = lobbyOpen && !liveQuestionId && currentStatus === "draft" && currentValidated;

  return (
    <>
      <NavBar />
      <header>
        <h1>Prepare lecture</h1>
      </header>
      <main>
        {activeLecture && (
          <section className="card lecture-bar" aria-label="Lecture">
            <div className="lecture-bar-info">
              <div className="lecture-bar-title">
                <span className="lecture-bar-name">{activeLecture.display_label}</span>
                <span className={`chip chip-${liveQuestionId ? "live" : lobbyOpen ? "open" : "prep"}`}>
                  {liveQuestionId ? "Live" : lobbyOpen ? "Lobby open" : "Preparing"}
                </span>
              </div>
              <div className="lecture-bar-sub">
                {questions.length === 0
                  ? "No questions yet"
                  : `${readyCount}/${draftCount} ready`}
                {lobbyOpen && activeLecture.join_code && (
                  <>
                    {" "}
                    · Code <strong className="join-code">{activeLecture.join_code}</strong>
                  </>
                )}
              </div>
            </div>
            <div className="lecture-bar-actions">
              {!liveQuestionId && (
                <button
                  type="button"
                  className="link-button danger-link"
                  onClick={() => setConfirmDeleteLectureOpen(true)}
                  disabled={deletingLecture}
                >
                  {deletingLecture ? "Deleting..." : "Delete lecture"}
                </button>
              )}
              {liveQuestionId ? (
                <a className="button-link" href={`lecturer.html?question_id=${encodeURIComponent(liveQuestionId)}`}>
                  Back to live dashboard &rarr;
                </a>
              ) : lobbyOpen ? (
                <a className="button-link" href={`lecturer.html?lobby=${activeLecture.id}`}>
                  Back to lobby &rarr;
                </a>
              ) : (
                <button
                  type="button"
                  onClick={handleOpenLobby}
                  disabled={openingLobby || readyCount === 0}
                  title={readyCount === 0 ? "No questions ready yet" : undefined}
                >
                  {openingLobby ? "Opening..." : "Open lobby"}
                </button>
              )}
            </div>
            {(lobbyError || deleteLectureError) && (
              <div className="form-status bad lecture-bar-error">{lobbyError || deleteLectureError}</div>
            )}
          </section>
        )}

        <div className="grid">
          <section className="card question-panel" aria-label="Questions">
            <div className="panel-head">
              <h2>Questions</h2>
              <span className="panel-count">{questions.length}</span>
            </div>
            {questions.length === 0 ? (
              <div className="empty">No questions yet</div>
            ) : (
              <ol className="question-list">
                {/* Run order: questions start oldest first (store.next_draft_question),
                    and the API lists newest first, so reversed is exactly that order. */}
                {[...questions].reverse().map((q, i) => {
                  const s = statusLabel(q);
                  return (
                    <li
                      key={q.id}
                      className={q.id === currentId ? "is-selected" : undefined}
                      onClick={(e) => {
                        if ((e.target as HTMLElement).closest("a")) return;
                        if (q.id === currentId) return;
                        flushThen(() => loadQuestionIntoForm(q));
                      }}
                    >
                      <span className="q-index">{i + 1}</span>
                      <span className="q-body">
                        <span className="q-title">{q.title}</span>
                        <span className={`q-status q-status-${s.kind}`}>{s.text}</span>
                      </span>
                      {q.status === "live" && (
                        <a className="text-link" href={`lecturer.html?question_id=${encodeURIComponent(q.id)}`}>
                          Dashboard
                        </a>
                      )}
                      {q.status === "draft" && (
                        <button
                          type="button"
                          className="icon-button"
                          aria-label={`Delete ${q.title}`}
                          title="Delete"
                          onClick={(e) => handleDeleteQuestion(q, e)}
                        >
                          &times;
                        </button>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
            <button type="button" className="new-question-btn" onClick={() => flushThen(resetForm)}>
              + New question
            </button>
            <button
              type="button"
              className="link-button dev-link"
              onClick={addTestQuestions}
              disabled={addingTestQuestions}
              title="Adds 3 checked sample questions, for testing"
            >
              {addingTestQuestions ? "Adding..." : "Add sample questions"}
            </button>
          </section>

          <section className="card editor" aria-label="Question editor">
            <div className="editor-head">
              <h2>{currentId ? title || "Untitled question" : "New question"}</h2>
              {currentId && (
                <span className={`q-status q-status-${currentValidated ? "ready" : locked ? "done" : "check"}`}>
                  {currentStatus === "live"
                    ? "Live"
                    : currentStatus !== "draft"
                    ? "Done"
                    : currentValidated
                    ? "Ready"
                    : "Needs a check"}
                </span>
              )}
            </div>
            {locked && (
              <div className="locked-banner">
                Already run, so it can't be edited.
              </div>
            )}

            <ol className="stepper">
              {STEPS.map((name, i) => (
                <li key={name}>
                  <button
                    type="button"
                    className={["step", i === step && "is-current", stepDone[i] && "is-done"].filter(Boolean).join(" ")}
                    aria-current={i === step ? "step" : undefined}
                    onClick={() => setStep(i)}
                  >
                    <span className="step-dot">{stepDone[i] && i !== step ? "✓" : i + 1}</span>
                    <span className="step-name">{name}</span>
                  </button>
                </li>
              ))}
            </ol>

            {/* onInput catches every typed edit in the steps (inputs, textareas, the select). */}
            <fieldset className="step-body" disabled={locked || busy !== null} onInput={markEdited}>
              {step === 0 && (
                <>
                  <label htmlFor="f-title">Title</label>
                  <input
                    type="text"
                    id="f-title"
                    placeholder="e.g. Sum of integers"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                  <label htmlFor="f-prompt">Task description</label>
                  <textarea
                    id="f-prompt"
                    className="prose"
                    placeholder="Read a line of space-separated integers and print their sum."
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                  />
                  <label htmlFor="f-language">Language</label>
                  <select id="f-language" value={language} onChange={(e) => setLanguage(e.target.value)}>
                    <option value="python">Python</option>
                    <option value="c">C</option>
                    <option value="java">Java</option>
                  </select>
                </>
              )}

              {step === 1 && (
                <>
                  <div className="field-head">
                    <span className="field-label">Test cases</span>
                  </div>
                  <div className="tc-table">
                    <div className="tc-header" aria-hidden="true">
                      <span>Input</span>
                      <span>Expected output</span>
                      <span />
                    </div>
                    {testCases.map((tc, i) => (
                      <div className="tc-row" key={i}>
                        <textarea
                          aria-label={`Test ${i + 1} input`}
                          placeholder="1 2 3"
                          value={tc.stdin}
                          onChange={(e) => updateTestCase(i, "stdin", e.target.value)}
                        />
                        <textarea
                          aria-label={`Test ${i + 1} expected output`}
                          placeholder="6"
                          value={tc.expected}
                          onChange={(e) => updateTestCase(i, "expected", e.target.value)}
                        />
                        <button
                          type="button"
                          className="icon-button"
                          aria-label={`Remove test ${i + 1}`}
                          title="Remove"
                          onClick={() => removeTestCaseRow(i)}
                        >
                          &times;
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" className="secondary small" onClick={addTestCaseRow}>
                    + Add test case
                  </button>

                  <label htmlFor="f-reference" className="spaced">
                    Reference solution <span className="hint">hidden from students</span>
                  </label>
                  <textarea
                    id="f-reference"
                    className="code"
                    placeholder="print(sum(int(x) for x in input().split()))"
                    value={referenceSolution}
                    onChange={(e) => setReferenceSolution(e.target.value)}
                  />
                  <div className="check-row">
                    <button type="button" className="secondary" onClick={checkSolution}>
                      {busy === "checking" ? "Checking..." : "Check solution"}
                    </button>
                  </div>
                  {validationResult && (
                    <div className={validationResult.pass ? "check-result pass" : "check-result fail"} role="status">
                      {validationResult.pass ? (
                        <>
                          <strong>All {validationResult.total} tests pass.</strong>
                        </>
                      ) : (
                        <>
                          <strong>
                            {validationResult.failing.length} of {validationResult.total} tests fail
                          </strong>
                          <ul>
                            {validationResult.failing.map((r, i) => (
                              <li key={i}>
                                input <code>{r.stdin.trim() || "(empty)"}</code>: expected{" "}
                                <code>{r.expected_stdout}</code>, got <code>{(r.stdout || "").trim() || "(nothing)"}</code>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              {step === 2 && (
                <>
                  <div className="row2">
                    <div>
                      <label htmlFor="f-duration">Time limit (min)</label>
                      <input
                        type="number"
                        id="f-duration"
                        min={1}
                        step={1}
                        value={durationMinutes}
                        onChange={(e) => setDurationMinutes(e.target.value)}
                      />
                    </div>
                    <div>
                      <label htmlFor="f-expected">
                        Class size <span className="hint">optional</span>
                      </label>
                      <input
                        type="number"
                        id="f-expected"
                        min={1}
                        step={1}
                        placeholder="e.g. 22"
                        value={expectedStudents}
                        onChange={(e) => setExpectedStudents(e.target.value)}
                      />
                    </div>
                  </div>
                  <label htmlFor="f-idle-nudge">
                    Idle nudge after (min) <span className="hint">0 = off</span>
                  </label>
                  <input
                    type="number"
                    id="f-idle-nudge"
                    className="narrow"
                    min={0}
                    step={0.5}
                    value={idleNudgeMinutes}
                    onChange={(e) => setIdleNudgeMinutes(e.target.value)}
                  />

                  <button
                    type="button"
                    className="disclosure"
                    aria-expanded={showAdvanced}
                    onClick={() => setShowAdvanced((v) => !v)}
                  >
                    <span className="chevron" aria-hidden="true" /> Advanced
                  </button>
                  {showAdvanced && (
                    <div className="advanced">
                      <div className="row2">
                        <div>
                          <label htmlFor="f-time">CPU time per test (s)</label>
                          <input
                            type="number"
                            id="f-time"
                            min={0.5}
                            step={0.5}
                            value={timeLimit}
                            onChange={(e) => setTimeLimit(e.target.value)}
                          />
                        </div>
                        <div>
                          <label htmlFor="f-memory">Memory (MB)</label>
                          <input
                            type="number"
                            id="f-memory"
                            min={16}
                            step={1}
                            value={memoryLimit}
                            onChange={(e) => setMemoryLimit(e.target.value)}
                          />
                        </div>
                      </div>
                      <div className="row2">
                        <div>
                          <label htmlFor="f-lines">Max lines</label>
                          <input
                            type="number"
                            id="f-lines"
                            min={10}
                            step={10}
                            value={lineLimit}
                            onChange={(e) => setLineLimit(e.target.value)}
                          />
                        </div>
                        <div>
                          <label htmlFor="f-packages">
                            Extra packages <span className="hint">comma-separated</span>
                          </label>
                          <input
                            type="text"
                            id="f-packages"
                            placeholder="e.g. numpy, requests"
                            value={packages}
                            onChange={(e) => setPackages(e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </fieldset>

            <div className={`form-status ${formStatusKind}`} role="status">
              {formStatusText}
            </div>

            <div className="editor-footer">
              <button type="button" className="secondary" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
                Back
              </button>
              {!locked && (
                <span className={`save-indicator save-${saveState}`} role="status">
                  {saveState === "saving"
                    ? "Saving…"
                    : saveState === "error"
                    ? "Not saved"
                    : dirty && !canAutosave
                    ? "Add a title to save"
                    : currentId && !dirty
                    ? "Saved"
                    : ""}
                </span>
              )}
              <div className="editor-footer-right">
                {step < STEPS.length - 1 ? (
                  <button type="button" onClick={() => setStep((s) => s + 1)}>
                    Next: {STEPS[step + 1]}
                  </button>
                ) : canStartNow ? (
                  <button type="button" onClick={startQuestion} disabled={busy !== null}>
                    {busy === "starting" ? "Starting..." : "Start now"}
                  </button>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      </main>
      <ConfirmDialog
        open={confirmDeleteLectureOpen}
        title="Delete lecture?"
        message={`Delete "${activeLecture?.display_label ?? ""}"? This can't be undone.`}
        onConfirm={confirmDeleteLecture}
        onCancel={() => setConfirmDeleteLectureOpen(false)}
      />
      <ConfirmDialog
        open={questionPendingDelete != null}
        title="Delete question?"
        message={`Delete "${questionPendingDelete?.title ?? ""}"? This can't be undone.`}
        onConfirm={confirmDeleteQuestion}
        onCancel={() => setQuestionPendingDelete(null)}
      />
    </>
  );
}
