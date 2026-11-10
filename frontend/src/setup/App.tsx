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
import { Badge, Button, Card, Code, Input, Label, LinkButton, Page, PageHeader, Select, Textarea } from "../shared/ui";
import { cx } from "../shared/cx";
import type { Tone } from "../shared/ui";

// Lecture preparation. Top: the lecture itself and its one next action (open
// the lobby, or go back to it / the live dashboard). Left: the questions in
// the order they'll run. Right: the question editor, split into three steps
// so a new question isn't one 15-field form -- what students see, the tests
// and a known-correct solution (checked in one click), then timing. Rarely
// changed grading limits sit under "Advanced" in step 3.

interface TestFileDraft {
  name: string;
  content: string;
}

interface TestCaseDraft {
  stdin: string;
  expected: string;
  // Data files the student's program opens by name (backend/test_files.py).
  files: TestFileDraft[];
}

// Same limit as the backend (backend/test_files.py): Judge0 caps what a
// program may print at 1 MB, so bigger test data couldn't be checked anyway.
const MAX_TEST_FILE_BYTES = 1_000_000;

function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} KB`;
  return `${(n / 1_000_000).toFixed(2)} MB`;
}

interface ValidationResultState {
  pass: boolean;
  total: number;
  failing: ValidationTestResult[];
}

const emptyTestCase = (): TestCaseDraft => ({ stdin: "", expected: "", files: [] });

const STEPS = ["Task", "Tests & solution", "Timing & class"] as const;

// Autosave waits this long after the last edit, so typing doesn't send a
// request per keystroke.
const AUTOSAVE_MS = 900;

type StatusKind = "live" | "done" | "ready" | "check";

// Plain-language status for the question list.
function statusLabel(q: QuestionRow): { text: string; kind: StatusKind } {
  if (q.status === "live") return { text: "Live", kind: "live" };
  if (q.status === "closed") return { text: "Done", kind: "done" };
  if (q.status === "skipped") return { text: "Skipped", kind: "done" };
  return q.validated ? { text: "Ready", kind: "ready" } : { text: "Needs a check", kind: "check" };
}

const STATUS_DOT: Record<StatusKind, string> = {
  live: "bg-emerald-500 animate-pulse-dot",
  ready: "bg-emerald-500",
  check: "bg-amber-500",
  done: "bg-zinc-300",
};
const STATUS_TEXT: Record<StatusKind, string> = {
  live: "text-emerald-700",
  ready: "text-emerald-700",
  check: "text-amber-700",
  done: "text-zinc-500",
};

export interface StatusTextProps {
  kind: StatusKind;
  children: string;
}

function StatusText({ kind, children }: StatusTextProps) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-xs font-medium", STATUS_TEXT[kind])}>
      <span className={cx("size-1.5 rounded-[2px]", STATUS_DOT[kind])} aria-hidden="true" />
      {children}
    </span>
  );
}

export interface RemoveButtonProps {
  label: string;
  onClick: (e: MouseEvent<HTMLButtonElement>) => void;
  className?: string;
}

// Small "x" for deleting a row (question, test case).
function RemoveButton({ label, onClick, className }: RemoveButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title="Remove"
      onClick={onClick}
      className={cx(
        "grid size-7 flex-none place-items-center rounded-md text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-600",
        "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-zinc-900 disabled:pointer-events-none disabled:opacity-40",
        className,
      )}
    >
      <svg className="size-3.5" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M3.5 3.5l7 7m0-7l-7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  );
}

// Dashed "attach" control wrapping a hidden file input. Greys out when the
// step fieldset is disabled (a started question is read-only).
export interface FilePickLabelProps {
  children: string;
  inputLabel: string;
  multiple?: boolean;
  onFiles: (files: FileList | null) => void;
}

function FilePickLabel({ children, inputLabel, multiple = false, onFiles }: FilePickLabelProps) {
  return (
    <label
      className={cx(
        "relative inline-flex cursor-pointer items-center rounded-md border border-dashed border-zinc-300 px-2 py-0.5 text-xs text-zinc-500 transition-colors",
        "hover:border-zinc-500 hover:text-zinc-900 focus-within:outline-2 focus-within:outline-offset-1 focus-within:outline-zinc-900",
        "group-disabled:cursor-default group-disabled:opacity-50 group-disabled:hover:border-zinc-300 group-disabled:hover:text-zinc-500",
      )}
    >
      {children}
      <input
        type="file"
        multiple={multiple}
        className="pointer-events-none absolute size-px opacity-0"
        aria-label={inputLabel}
        onChange={(e) => {
          onFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </label>
  );
}

const LECTURE_TONE: Record<"live" | "open" | "prep", Tone> = { live: "success", open: "info", prep: "neutral" };

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
  // Graded on a file the program writes (outputFile) instead of what it prints.
  const [gradeFile, setGradeFile] = useState(false);
  const [outputFile, setOutputFile] = useState("result.txt");
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

  // Dev convenience only: real, correct-by-construction questions -- three
  // Python, plus one each in C and Java
  // (validated immediately so they're startable right away) so testing the
  // whole lobby/start/submit flow doesn't require typing a question in by
  // hand every time. Not something a real class needs -- just faster manual
  // testing.
  async function addTestQuestions() {
    setAddingTestQuestions(true);
    setStatus("Adding...");
    const samples: {
      title: string;
      language?: string;
      prompt: string;
      test_cases: { stdin: string; expected: string }[];
      reference_solution: string;
    }[] = [
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
      {
        title: "Sum Two (C)",
        language: "c",
        prompt: "Read two integers on one line and print their sum.",
        test_cases: [
          { stdin: "3 4\n", expected: "7" },
          { stdin: "10 -2\n", expected: "8" },
        ],
        reference_solution: [
          "#include <stdio.h>",
          "",
          "int main(void) {",
          "    int a, b;",
          '    scanf("%d %d", &a, &b);',
          '    printf("%d\\n", a + b);',
          "    return 0;",
          "}",
          "",
        ].join("\n"),
      },
      {
        title: "Sum Two (Java)",
        language: "java",
        prompt: "Read two integers on one line and print their sum. Your class must be named Main.",
        test_cases: [
          { stdin: "3 4\n", expected: "7" },
          { stdin: "10 -2\n", expected: "8" },
        ],
        reference_solution: [
          "import java.util.Scanner;",
          "",
          "public class Main {",
          "    public static void main(String[] args) {",
          "        Scanner sc = new Scanner(System.in);",
          "        int a = sc.nextInt(), b = sc.nextInt();",
          "        System.out.println(a + b);",
          "    }",
          "}",
          "",
        ].join("\n"),
      },
    ];
    try {
      for (const sample of samples) {
        const created = await createQuestion({
          title: sample.title,
          prompt: sample.prompt,
          language: sample.language ?? "python",
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
      setStatus(`Added ${samples.length} sample questions.`, "ok");
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
    setGradeFile(false);
    setOutputFile("result.txt");
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
    setGradeFile(Boolean(q.output_file));
    setOutputFile(q.output_file || "result.txt");
    setTestCases(
      q.test_cases.length
        ? q.test_cases.map((tc) => ({
            stdin: tc.stdin,
            expected: tc.expected_stdout,
            files: (tc.files ?? []).map((f) => ({ name: f.name, content: f.content ?? "" })),
          }))
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

  const [fileError, setFileError] = useState("");

  // Reads the chosen files as text and attaches them to one test; a file with
  // the same name as one already attached replaces it.
  async function attachFiles(index: number, list: FileList | null) {
    if (!list || list.length === 0) return;
    setFileError("");
    const added: TestFileDraft[] = [];
    for (const file of Array.from(list)) {
      if (file.size > MAX_TEST_FILE_BYTES) {
        setFileError(`"${file.name}" is ${formatBytes(file.size)}. Test files can be at most 1 MB.`);
        return;
      }
      const content = await file.text();
      if (content.includes("\u0000")) {
        setFileError(`"${file.name}" isn't a text file. Only text files can be attached.`);
        return;
      }
      added.push({ name: file.name, content });
    }
    setTestCases((prev) =>
      prev.map((tc, i) => {
        if (i !== index) return tc;
        const names = new Set(added.map((f) => f.name));
        return { ...tc, files: [...tc.files.filter((f) => !names.has(f.name)), ...added] };
      }),
    );
    markEdited();
  }

  // The expected output, read from a file instead of typed -- handy for big outputs.
  async function loadExpectedFromFile(index: number, list: FileList | null) {
    const file = list?.[0];
    if (!file) return;
    setFileError("");
    if (file.size > MAX_TEST_FILE_BYTES) {
      setFileError(`"${file.name}" is ${formatBytes(file.size)}. An expected output can be at most 1 MB.`);
      return;
    }
    const content = await file.text();
    if (content.includes("\u0000")) {
      setFileError(`"${file.name}" isn't a text file.`);
      return;
    }
    updateTestCase(index, "expected", content);
    markEdited();
  }

  function removeFile(index: number, name: string) {
    setTestCases((prev) => prev.map((tc, i) => (i === index ? { ...tc, files: tc.files.filter((f) => f.name !== name) } : tc)));
    markEdited();
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
        .filter((tc) => tc.stdin.trim() || tc.expected.trim() || tc.files.length)
        .map((tc) => ({ stdin: tc.stdin, expected_stdout: tc.expected, files: tc.files })),
      reference_solution: referenceSolution || null,
      output_file: gradeFile ? outputFile.trim() || "result.txt" : null,
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

  const lectureState: "live" | "open" | "prep" = liveQuestionId ? "live" : lobbyOpen ? "open" : "prep";
  const editorStatus: StatusKind =
    currentStatus === "live" ? "live" : currentStatus !== "draft" ? "done" : currentValidated ? "ready" : "check";

  return (
    <>
      <NavBar />
      <Page>
        <PageHeader
          eyebrow={activeLecture ? activeLecture.display_label : "Lecture"}
          title="Prepare lecture"
          description={
            activeLecture && (
              <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <Badge tone={LECTURE_TONE[lectureState]} dot pulse={lectureState === "live"}>
                  {liveQuestionId ? "Live" : lobbyOpen ? "Lobby open" : "Preparing"}
                </Badge>
                <span>
                  {questions.length === 0 ? (
                    "No questions yet"
                  ) : (
                    <>
                      <span className="font-mono text-zinc-900 tabular-nums">
                        {readyCount}/{draftCount}
                      </span>{" "}
                      ready
                    </>
                  )}
                </span>
                {lobbyOpen && activeLecture.join_code && (
                  <span>
                    Code{" "}
                    <strong className="font-mono font-bold tracking-[0.12em] text-zinc-950">
                      {activeLecture.join_code}
                    </strong>
                  </span>
                )}
              </span>
            )
          }
          actions={
            activeLecture && (
              <>
                {!liveQuestionId && (
                  <Button
                    variant="danger-ghost"
                    onClick={() => setConfirmDeleteLectureOpen(true)}
                    disabled={deletingLecture}
                  >
                    {deletingLecture ? "Deleting..." : "Delete lecture"}
                  </Button>
                )}
                {liveQuestionId ? (
                  <LinkButton href={`lecturer.html?question_id=${encodeURIComponent(liveQuestionId)}`}>
                    Back to live dashboard &rarr;
                  </LinkButton>
                ) : lobbyOpen ? (
                  <LinkButton href={`lecturer.html?lobby=${activeLecture.id}`}>Back to lobby &rarr;</LinkButton>
                ) : (
                  <Button
                    onClick={handleOpenLobby}
                    disabled={openingLobby || readyCount === 0}
                    title={readyCount === 0 ? "No questions ready yet" : undefined}
                  >
                    {openingLobby ? "Opening..." : "Open lobby"}
                  </Button>
                )}
              </>
            )
          }
        />
        {(lobbyError || deleteLectureError) && (
          <p role="alert" className="-mt-4 mb-6 text-[13px] font-medium text-red-600">
            {lobbyError || deleteLectureError}
          </p>
        )}

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <section aria-label="Questions" className="lg:sticky lg:top-20">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Questions</h2>
              <span className="font-mono text-xs text-zinc-500">{questions.length}</span>
            </div>
            {questions.length === 0 ? (
              <div className="rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500">
                No questions yet
              </div>
            ) : (
              <ol className="grid gap-1">
                {/* Run order: questions start oldest first (store.next_draft_question),
                    and the API lists newest first, so reversed is exactly that order. */}
                {[...questions].reverse().map((q, i) => {
                  const s = statusLabel(q);
                  const selected = q.id === currentId;
                  return (
                    <li
                      key={q.id}
                      className={cx(
                        "group/q flex items-center gap-1 rounded-lg border pr-1.5 transition-colors",
                        selected ? "border-zinc-900 bg-white" : "border-transparent hover:border-zinc-200 hover:bg-white",
                      )}
                    >
                      <button
                        type="button"
                        aria-current={selected ? "true" : undefined}
                        className="flex min-w-0 flex-1 items-center gap-3 rounded-lg py-2.5 pl-2.5 text-left focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-zinc-900"
                        onClick={() => {
                          if (selected) return;
                          flushThen(() => loadQuestionIntoForm(q));
                        }}
                      >
                        <span
                          className={cx(
                            "grid size-6 flex-none place-items-center rounded-md font-mono text-[11px] font-semibold",
                            selected ? "bg-zinc-950 text-white" : "border border-zinc-200 bg-white text-zinc-500",
                          )}
                        >
                          {i + 1}
                        </span>
                        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <span className="truncate text-sm font-semibold text-zinc-900">{q.title}</span>
                          <StatusText kind={s.kind}>{s.text}</StatusText>
                        </span>
                      </button>
                      {q.status === "live" && (
                        <LinkButton
                          variant="ghost"
                          size="sm"
                          href={`lecturer.html?question_id=${encodeURIComponent(q.id)}`}
                        >
                          Dashboard
                        </LinkButton>
                      )}
                      {q.status === "draft" && (
                        <RemoveButton
                          label={`Delete ${q.title}`}
                          className="opacity-0 group-hover/q:opacity-100 focus-visible:opacity-100 max-lg:opacity-100"
                          onClick={(e) => handleDeleteQuestion(q, e)}
                        />
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
            {/* Disabled while the editor already is a new, not-yet-saved question
                (it saves itself once it has a title) -- clicking it then did
                nothing visible, or reset a language picked before the title back
                to Python. */}
            <Button
              variant="secondary"
              className="mt-3 w-full"
              onClick={() => flushThen(resetForm)}
              disabled={!currentId}
              title={!currentId ? "The editor is already a new question" : undefined}
            >
              + New question
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="mx-auto mt-2 flex"
              onClick={addTestQuestions}
              disabled={addingTestQuestions}
              title="Adds checked sample questions (Python, C, Java), for testing"
            >
              {addingTestQuestions ? "Adding..." : "Add sample questions"}
            </Button>
          </section>

          <Card flush aria-label="Question editor" role="region">
            <div className="px-6 pt-6 sm:px-8 sm:pt-7">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-xl font-bold tracking-tight text-zinc-950">
                  {currentId ? title || "Untitled question" : "New question"}
                </h2>
                {currentId && (
                  <StatusText kind={editorStatus}>
                    {currentStatus === "live"
                      ? "Live"
                      : currentStatus !== "draft"
                        ? "Done"
                        : currentValidated
                          ? "Ready"
                          : "Needs a check"}
                  </StatusText>
                )}
              </div>
              {locked && (
                <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 px-3.5 py-2.5 text-[13px] text-zinc-600">
                  Already run, so it can't be edited.
                </div>
              )}

              <ol className="mt-6 flex border-b border-zinc-200">
                {STEPS.map((name, i) => {
                  const current = i === step;
                  const done = stepDone[i] && !current;
                  return (
                    <li key={name} className="flex-1">
                      <button
                        type="button"
                        className={cx(
                          "-mb-px flex w-full items-center gap-2.5 border-b-2 px-1 pt-1 pb-3 text-left text-[13px] font-semibold transition-colors",
                          "rounded-t-md focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-zinc-900",
                          current ? "border-zinc-950 text-zinc-950" : "border-transparent text-zinc-500 hover:text-zinc-900",
                        )}
                        aria-current={current ? "step" : undefined}
                        onClick={() => setStep(i)}
                      >
                        <span
                          className={cx(
                            "grid size-6 flex-none place-items-center rounded-md font-mono text-[11px] font-bold",
                            current
                              ? "bg-zinc-950 text-white"
                              : done
                                ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                                : "border border-zinc-200 bg-white",
                          )}
                        >
                          {done ? "✓" : i + 1}
                        </span>
                        <span className={cx(!current && "max-sm:hidden")}>{name}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </div>

            {/* onInput catches every typed edit in the steps (inputs, textareas, the select). */}
            <fieldset
              className="group min-w-0 px-6 py-6 disabled:opacity-75 sm:px-8"
              disabled={locked || busy !== null}
              onInput={markEdited}
            >
              {step === 0 && (
                <div className="grid gap-5">
                  <div>
                    <Label htmlFor="f-title">Title</Label>
                    <Input
                      type="text"
                      id="f-title"
                      placeholder="e.g. Sum of integers"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="f-prompt">Task description</Label>
                    <Textarea
                      id="f-prompt"
                      className="min-h-28"
                      placeholder="Read a line of space-separated integers and print their sum."
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                    />
                  </div>
                  <div className="max-w-56">
                    <Label htmlFor="f-language">Language</Label>
                    <Select id="f-language" value={language} onChange={(e) => setLanguage(e.target.value)}>
                      <option value="python">Python</option>
                      <option value="c">C</option>
                      <option value="java">Java</option>
                    </Select>
                  </div>
                </div>
              )}

              {step === 1 && (
                <>
                  <div className="mb-2 text-[13px] font-semibold text-zinc-900">What&apos;s graded</div>
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2" role="radiogroup" aria-label="What's graded">
                    <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 hover:text-zinc-950">
                      <input
                        type="radio"
                        name="grade-mode"
                        className="size-4 accent-zinc-900"
                        checked={!gradeFile}
                        onChange={() => setGradeFile(false)}
                      />
                      What the program prints
                    </label>
                    <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 hover:text-zinc-950">
                      <input
                        type="radio"
                        name="grade-mode"
                        className="size-4 accent-zinc-900"
                        checked={gradeFile}
                        onChange={() => setGradeFile(true)}
                      />
                      A file the program writes:
                    </label>
                    <Input
                      type="text"
                      mono
                      className="h-8 w-48 text-[13px] disabled:opacity-55"
                      aria-label="Output file name"
                      value={outputFile}
                      disabled={!gradeFile}
                      onChange={(e) => setOutputFile(e.target.value)}
                    />
                  </div>
                  {gradeFile && (
                    <p className="mt-2 text-[13px] text-zinc-500">
                      Students write their answer to <Code>{outputFile.trim() || "result.txt"}</Code>. That file is
                      compared with the expected output; what the program prints isn&apos;t graded.
                    </p>
                  )}

                  <div className="mt-7 mb-2 text-[13px] font-semibold text-zinc-900">Test cases</div>
                  <div className="grid gap-3">
                    <div
                      className="grid grid-cols-[1fr_1fr_1.75rem] gap-2 text-[11px] font-semibold tracking-[0.08em] text-zinc-500 uppercase"
                      aria-hidden="true"
                    >
                      <span>Input</span>
                      <span>{gradeFile ? `Expected ${outputFile.trim() || "result.txt"}` : "Expected output"}</span>
                      <span />
                    </div>
                    {testCases.map((tc, i) => (
                      <div className="grid gap-1.5" key={i}>
                        <div className="grid grid-cols-[1fr_1fr_1.75rem] items-start gap-2">
                          <Textarea
                            mono
                            className="min-h-11"
                            aria-label={`Test ${i + 1} input`}
                            placeholder="1 2 3"
                            value={tc.stdin}
                            onChange={(e) => updateTestCase(i, "stdin", e.target.value)}
                          />
                          <Textarea
                            mono
                            className="min-h-11"
                            aria-label={`Test ${i + 1} expected output`}
                            placeholder="6"
                            value={tc.expected}
                            onChange={(e) => updateTestCase(i, "expected", e.target.value)}
                          />
                          <RemoveButton
                            label={`Remove test ${i + 1}`}
                            className="mt-2"
                            onClick={() => removeTestCaseRow(i)}
                          />
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 pr-9">
                          {tc.files.map((f) => (
                            <span
                              className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-zinc-200 bg-zinc-50 py-0.5 pr-0.5 pl-2 text-xs"
                              key={f.name}
                              title={f.name}
                            >
                              <span className="truncate font-mono text-zinc-900">{f.name}</span>
                              <span className="font-mono text-zinc-500">{formatBytes(new Blob([f.content]).size)}</span>
                              <button
                                type="button"
                                className="rounded px-1 leading-none text-zinc-400 transition-colors group-disabled:hidden hover:bg-red-50 hover:text-red-600 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-zinc-900"
                                aria-label={`Remove ${f.name} from test ${i + 1}`}
                                onClick={() => removeFile(i, f.name)}
                              >
                                &times;
                              </button>
                            </span>
                          ))}
                          <FilePickLabel
                            inputLabel={`Load test ${i + 1}'s expected output from a file`}
                            onFiles={(files) => void loadExpectedFromFile(i, files)}
                          >
                            Expected from file
                          </FilePickLabel>
                          <FilePickLabel
                            multiple
                            inputLabel={`Attach files to test ${i + 1}`}
                            onFiles={(files) => void attachFiles(i, files)}
                          >
                            + File
                          </FilePickLabel>
                          {i === 0 && tc.files.length > 0 && (
                            <span className="text-xs text-zinc-500">Test 1 is the example: students can open its files.</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[13px] leading-relaxed text-zinc-500">
                    Files are put next to the student&apos;s program, which opens them by name, e.g.{" "}
                    <Code>open(&quot;numbers.txt&quot;)</Code>. Text files, up to 1 MB each. Students see the
                    example&apos;s files during the task and every test&apos;s files once time is up.
                  </p>
                  {fileError && (
                    <div
                      className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-900"
                      role="alert"
                    >
                      {fileError}
                    </div>
                  )}
                  <Button variant="secondary" size="sm" className="mt-3" onClick={addTestCaseRow}>
                    + Add test case
                  </Button>

                  <div className="mt-8">
                    <Label htmlFor="f-reference" hint="hidden from students">
                      Reference solution
                    </Label>
                    <Textarea
                      id="f-reference"
                      mono
                      className="min-h-32"
                      placeholder="print(sum(int(x) for x in input().split()))"
                      value={referenceSolution}
                      onChange={(e) => setReferenceSolution(e.target.value)}
                    />
                  </div>
                  <Button variant="secondary" className="mt-3" onClick={checkSolution}>
                    {busy === "checking" ? "Checking..." : "Check solution"}
                  </Button>
                  {validationResult && (
                    <div
                      className={cx(
                        "mt-4 animate-fade-in rounded-lg border px-4 py-3 text-[13px] leading-relaxed",
                        validationResult.pass
                          ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                          : "border-red-200 bg-red-50 text-red-900",
                      )}
                      role="status"
                    >
                      {validationResult.pass ? (
                        <strong className="font-semibold">All {validationResult.total} tests pass.</strong>
                      ) : (
                        <>
                          <strong className="font-semibold">
                            {validationResult.failing.length} of {validationResult.total} tests fail
                          </strong>
                          <ul className="mt-2 grid list-disc gap-1 pl-5">
                            {validationResult.failing.map((r, i) => (
                              <li key={i}>
                                input <Code>{r.stdin.trim() || "(empty)"}</Code>: expected{" "}
                                <Code>{r.expected_stdout}</Code>, got <Code>{(r.stdout || "").trim() || "(nothing)"}</Code>
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
                <div className="grid gap-5">
                  <div className="grid gap-5 sm:grid-cols-2">
                    <div>
                      <Label htmlFor="f-duration">Time limit (min)</Label>
                      <Input
                        type="number"
                        id="f-duration"
                        mono
                        min={1}
                        step={1}
                        value={durationMinutes}
                        onChange={(e) => setDurationMinutes(e.target.value)}
                      />
                    </div>
                    <div>
                      <Label htmlFor="f-expected" hint="optional">
                        Class size
                      </Label>
                      <Input
                        type="number"
                        id="f-expected"
                        mono
                        min={1}
                        step={1}
                        placeholder="e.g. 22"
                        value={expectedStudents}
                        onChange={(e) => setExpectedStudents(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="max-w-40">
                    <Label htmlFor="f-idle-nudge" hint="0 = off">
                      Idle nudge after (min)
                    </Label>
                    <Input
                      type="number"
                      id="f-idle-nudge"
                      mono
                      min={0}
                      step={0.5}
                      value={idleNudgeMinutes}
                      onChange={(e) => setIdleNudgeMinutes(e.target.value)}
                    />
                  </div>

                  <div>
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 rounded-md py-1 text-[13px] font-semibold text-zinc-900 transition-colors hover:text-zinc-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
                      aria-expanded={showAdvanced}
                      onClick={() => setShowAdvanced((v) => !v)}
                    >
                      <svg
                        className={cx("size-3 transition-transform", showAdvanced && "rotate-90")}
                        viewBox="0 0 12 12"
                        fill="none"
                        aria-hidden="true"
                      >
                        <path d="M4.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      Advanced
                    </button>
                    {showAdvanced && (
                      <div className="mt-3 grid animate-fade-in gap-5 rounded-lg border border-zinc-200 bg-zinc-50 p-5 sm:grid-cols-2">
                        <div>
                          <Label htmlFor="f-time">CPU time per test (s)</Label>
                          <Input
                            type="number"
                            id="f-time"
                            mono
                            min={0.5}
                            step={0.5}
                            value={timeLimit}
                            onChange={(e) => setTimeLimit(e.target.value)}
                          />
                        </div>
                        <div>
                          <Label htmlFor="f-memory">Memory (MB)</Label>
                          <Input
                            type="number"
                            id="f-memory"
                            mono
                            min={16}
                            step={1}
                            value={memoryLimit}
                            onChange={(e) => setMemoryLimit(e.target.value)}
                          />
                        </div>
                        <div>
                          <Label htmlFor="f-lines">Max lines</Label>
                          <Input
                            type="number"
                            id="f-lines"
                            mono
                            min={10}
                            step={10}
                            value={lineLimit}
                            onChange={(e) => setLineLimit(e.target.value)}
                          />
                        </div>
                        <div>
                          <Label htmlFor="f-packages" hint="comma-separated">
                            Extra packages
                          </Label>
                          <Input
                            type="text"
                            id="f-packages"
                            placeholder="e.g. numpy, requests"
                            value={packages}
                            onChange={(e) => setPackages(e.target.value)}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </fieldset>

            <div
              className={cx(
                "min-h-5 px-6 text-[13px] sm:px-8",
                formStatusKind === "ok" ? "text-emerald-700" : formStatusKind === "bad" ? "font-medium text-red-600" : "text-zinc-500",
              )}
              role="status"
            >
              {formStatusText}
            </div>

            <div className="mt-4 flex items-center justify-between gap-3 border-t border-zinc-200 px-6 py-4 sm:px-8">
              <Button variant="secondary" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
                Back
              </Button>
              {!locked && (
                <span
                  className={cx("flex-1 text-[13px]", saveState === "error" ? "font-medium text-red-600" : "text-zinc-500")}
                  role="status"
                >
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
              <div className="flex gap-2">
                {step < STEPS.length - 1 ? (
                  <Button onClick={() => setStep((s) => s + 1)}>Next: {STEPS[step + 1]}</Button>
                ) : canStartNow ? (
                  <Button onClick={startQuestion} disabled={busy !== null}>
                    {busy === "starting" ? "Starting..." : "Start now"}
                  </Button>
                ) : null}
              </div>
            </div>
          </Card>
        </div>
      </Page>
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
