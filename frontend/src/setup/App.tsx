import { useEffect, useState } from "react";
import type { MouseEvent } from "react";
import type { LectureRow, QuestionRow, QuestionStatus, ValidationTestResult } from "../shared/types";
import {
  createQuestion,
  deleteQuestion as deleteQuestionApi,
  fetchActiveLecture,
  fetchQuestionList,
  openLobby as openLobbyApi,
  startQuestion as startQuestionApi,
  updateQuestion,
  validateQuestion as validateQuestionApi,
} from "../shared/api";
import { HeaderNavLink } from "../shared/HeaderNavLink";

interface TestCaseDraft {
  stdin: string;
  expected: string;
}

interface ValidationResultState {
  pass: boolean;
  failing: ValidationTestResult[];
}

const emptyTestCase = (): TestCaseDraft => ({ stdin: "", expected: "" });

export default function App() {
  const [questions, setQuestions] = useState<QuestionRow[]>([]);

  const [currentId, setCurrentId] = useState<string | null>(null);
  const [currentStatus, setCurrentStatus] = useState<QuestionStatus>("draft");
  const [formHeading, setFormHeading] = useState("New question");

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
  const [referenceSolution, setReferenceSolution] = useState("");

  const [formStatusText, setFormStatusText] = useState("");
  const [formStatusColor, setFormStatusColor] = useState("var(--muted)");
  const [validationResult, setValidationResult] = useState<ValidationResultState | null>(null);
  const [startDisabled, setStartDisabled] = useState(true);

  // The lecture this setup session belongs to (see the lobby-scoping-
  // decision) -- fetched once so the "Open lobby" banner knows whether the
  // lobby's already open (show a link back to it instead of the button).
  const [activeLecture, setActiveLecture] = useState<LectureRow | null>(null);
  // If a question is already live, "back to the lobby" must actually mean
  // "back to the live dashboard" -- see the lobby-view fix in
  // lecturer/App.tsx for why (landing on the pre-start lobby again would
  // let "Start lecture" fire a second time on top of the question already
  // running).
  const [liveQuestionId, setLiveQuestionId] = useState<string | null>(null);
  const [openingLobby, setOpeningLobby] = useState(false);
  const [lobbyError, setLobbyError] = useState<string | null>(null);
  const [addingTestQuestions, setAddingTestQuestions] = useState(false);

  const locked = currentStatus === "live";

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
        // Not critical -- the lobby banner just won't show.
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

  async function handleDeleteQuestion(q: QuestionRow, e: MouseEvent) {
    e.stopPropagation(); // don't also trigger the row's own onClick (load into form)
    if (!window.confirm(`Delete "${q.title}"? This can't be undone.`)) return;
    try {
      await deleteQuestionApi(q.id);
      if (currentId === q.id) resetForm();
      loadQuestionList();
    } catch (err) {
      setFormStatusText(err instanceof Error ? err.message : "Could not delete this question.");
      setFormStatusColor("var(--bad)");
    }
  }

  // Dev convenience only: three real, correct-by-construction questions
  // (validated immediately so they're startable right away) so testing the
  // whole lobby/start/submit flow doesn't require typing a question in by
  // hand every time. Not something a real class needs -- just faster manual
  // testing.
  async function addTestQuestions() {
    setAddingTestQuestions(true);
    setFormStatusText("Adding test questions...");
    setFormStatusColor("var(--muted)");
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
        test_cases: [{ stdin: "3 4\n", expected: "7" }],
        reference_solution: "a, b = map(int, input().split()); print(a + b)",
      },
      {
        title: "Reverse It",
        prompt: "Read a line of text and print it reversed.",
        test_cases: [{ stdin: "hello\n", expected: "olleh" }],
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
        });
        await validateQuestionApi(created.id);
      }
      setFormStatusText("Added 3 validated test questions.");
      setFormStatusColor("var(--ok)");
      loadQuestionList();
    } catch (err) {
      setFormStatusText(err instanceof Error ? err.message : "Could not add test questions.");
      setFormStatusColor("var(--bad)");
    } finally {
      setAddingTestQuestions(false);
    }
  }

  function resetForm() {
    setCurrentId(null);
    setCurrentStatus("draft");
    setFormHeading("New question");
    setTitle("");
    setPrompt("");
    setLanguage("python");
    setTimeLimit("5");
    setMemoryLimit("125");
    setLineLimit("200");
    setPackages("");
    setExpectedStudents("");
    setDurationMinutes("10");
    setReferenceSolution("");
    setTestCases([emptyTestCase()]);
    setFormStatusText("");
    setValidationResult(null);
    setStartDisabled(true);
  }

  function loadQuestionIntoForm(q: QuestionRow) {
    setCurrentId(q.id);
    setCurrentStatus(q.status);
    setFormHeading(q.title);
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
    setReferenceSolution(q.reference_solution || "");
    setTestCases(
      q.test_cases.length
        ? q.test_cases.map((tc) => ({ stdin: tc.stdin, expected: tc.expected_stdout }))
        : [emptyTestCase()]
    );
    setFormStatusText("");
    setValidationResult(null);
    setStartDisabled(!q.validated);
  }

  function addTestCaseRow() {
    setTestCases((prev) => [...prev, emptyTestCase()]);
  }
  function removeTestCaseRow(index: number) {
    setTestCases((prev) => prev.filter((_, i) => i !== index));
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
      test_cases: testCases.map((tc) => ({ stdin: tc.stdin, expected_stdout: tc.expected })),
      reference_solution: referenceSolution || null,
      cpu_time_limit_s: parseFloat(timeLimit),
      memory_limit_kb: Math.round(parseFloat(memoryLimit) * 1024),
      extra_packages: packageList,
      line_limit: parseInt(lineLimit, 10),
      expected_students: expectedStudents ? parseInt(expectedStudents, 10) : null,
      duration_seconds: Math.round(parseFloat(durationMinutes) * 60),
    };
  }

  async function saveDraft() {
    const payload = formPayload();
    if (!payload.title || !payload.prompt || payload.test_cases.length === 0) {
      setFormStatusText("Title, prompt, and at least one test case are required.");
      setFormStatusColor("var(--bad)");
      return;
    }
    if (!payload.duration_seconds || payload.duration_seconds <= 0) {
      setFormStatusText("Time limit must be a positive number of minutes.");
      setFormStatusColor("var(--bad)");
      return;
    }
    setFormStatusText("Saving...");
    setFormStatusColor("var(--muted)");
    try {
      const data = currentId ? await updateQuestion(currentId, payload) : await createQuestion(payload);
      loadQuestionIntoForm(data);
      setFormStatusText("Saved.");
      setFormStatusColor("var(--ok)");
      loadQuestionList();
    } catch (e) {
      setFormStatusText(e instanceof Error ? e.message : "Save failed.");
      setFormStatusColor("var(--bad)");
    }
  }

  async function runValidation() {
    if (!currentId) {
      setFormStatusText("Save the question as a draft first.");
      setFormStatusColor("var(--bad)");
      return;
    }
    setFormStatusText("Running the reference solution against the rubric on Judge0...");
    setFormStatusColor("var(--muted)");
    setValidationResult(null);
    try {
      const data = await validateQuestionApi(currentId);
      setFormStatusText("");
      setValidationResult({
        pass: data.validated,
        failing: (data.results || []).filter((r) => !r.passed),
      });
      setStartDisabled(!data.validated);
    } catch (e) {
      setFormStatusText(e instanceof Error ? e.message : "Validation failed.");
      setFormStatusColor("var(--bad)");
    }
  }

  async function startQuestion() {
    if (!currentId) return;
    setFormStatusText("Starting...");
    setFormStatusColor("var(--muted)");
    try {
      await startQuestionApi(currentId);
      setFormStatusText("Live. Redirecting to the dashboard...");
      setFormStatusColor("var(--ok)");
      loadQuestionList();
      setTimeout(() => {
        window.location.href = `lecturer.html?question_id=${encodeURIComponent(currentId)}`;
      }, 700);
    } catch (e) {
      setFormStatusText(e instanceof Error ? e.message : "Could not start this question.");
      setFormStatusColor("var(--bad)");
    }
  }

  return (
    <>
      <header>
        <h1>Lecturer -- Question Setup</h1>
        <p>Author a question, set its grading config, validate it against a known-correct solution, then start it.</p>
        <p>
          <HeaderNavLink href="index.html">&larr; Home</HeaderNavLink>
        </p>
      </header>
      <main>
        {activeLecture && (
          <div className="card" id="lobby-banner">
            {liveQuestionId ? (
              <>
                <h2>Lecture is live</h2>
                <p className="hint" style={{ marginBottom: "0.6rem" }}>
                  A question is already running. You can still add, edit, or delete draft questions here for
                  later in the lecture.
                </p>
                <a href={`lecturer.html?question_id=${encodeURIComponent(liveQuestionId)}`}>
                  <button type="button">Back to live dashboard &rarr;</button>
                </a>
              </>
            ) : activeLecture.lobby_opened_at ? (
              <>
                <h2>Lobby is open</h2>
                <p className="hint" style={{ marginBottom: "0.6rem" }}>
                  Students can already join with code <strong>{activeLecture.join_code}</strong>. Add, edit, or
                  delete draft questions here any time before you start the lecture.
                </p>
                <a href={`lecturer.html?lobby=${activeLecture.id}`}>
                  <button type="button">Back to lobby &rarr;</button>
                </a>
              </>
            ) : (
              <>
                <h2>Ready for class?</h2>
                <p className="hint" style={{ marginBottom: "0.6rem" }}>
                  Prepare as many questions as you like first -- nothing is joinable and no timer starts until you
                  open the lobby.
                </p>
                <button type="button" onClick={handleOpenLobby} disabled={openingLobby}>
                  {openingLobby ? "Opening..." : "Open lobby"}
                </button>
                {lobbyError && <div style={{ color: "var(--bad)", marginTop: "0.5rem" }}>{lobbyError}</div>}
              </>
            )}
          </div>
        )}
        <div className="grid">
          <div className="card">
            <h2>Questions</h2>
            <div id="empty-list" style={{ display: questions.length === 0 ? "block" : "none" }}>
              No questions yet -- create one on the right.
            </div>
            <ul id="question-list" style={{ display: questions.length === 0 ? "none" : "block" }}>
              {questions.map((q) => (
                <li
                  key={q.id}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).tagName === "A") return;
                    loadQuestionIntoForm(q);
                  }}
                >
                  <div>
                    <div className="q-title">{q.title}</div>
                    <div className="q-meta">
                      <span
                        className={
                          "status-pill " +
                          (q.status === "live"
                            ? "status-live"
                            : q.status === "closed"
                            ? "status-closed"
                            : "status-draft")
                        }
                      >
                        {q.status}
                      </span>{" "}
                      {q.id}
                    </div>
                  </div>
                  {q.status === "live" && (
                    <a href={`lecturer.html?question_id=${encodeURIComponent(q.id)}`}>Live dashboard &rarr;</a>
                  )}
                  {q.status === "draft" && (
                    <button
                      type="button"
                      className="danger delete-question-btn"
                      onClick={(e) => handleDeleteQuestion(q, e)}
                    >
                      Delete
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <button className="secondary" id="new-question-btn" style={{ marginTop: "0.9rem" }} onClick={resetForm}>
              + New question
            </button>
            <button
              className="secondary"
              id="add-test-questions-btn"
              style={{ marginTop: "0.9rem" }}
              onClick={addTestQuestions}
              disabled={addingTestQuestions}
              title="Dev convenience -- adds 3 real, pre-validated questions so you don't have to type one in by hand to test the flow."
            >
              {addingTestQuestions ? "Adding..." : "+ Add 3 test questions"}
            </button>
          </div>

          <div className="card">
            <h2 id="form-heading">{formHeading}</h2>
            <div id="locked-banner" style={{ display: locked ? "block" : "none" }}>
              This question is live -- its config is locked. Create a new question to change anything.
            </div>

            <label htmlFor="f-title">Title</label>
            <input
              type="text"
              id="f-title"
              placeholder="e.g. Sum of Integers"
              value={title}
              disabled={locked}
              onChange={(e) => setTitle(e.target.value)}
            />

            <label htmlFor="f-prompt">
              Prompt <span className="hint">-- shown to students</span>
            </label>
            <textarea
              id="f-prompt"
              placeholder="Read a single line of space-separated integers..."
              value={prompt}
              disabled={locked}
              onChange={(e) => setPrompt(e.target.value)}
            />

            <label htmlFor="f-language">Language</label>
            <select id="f-language" value={language} disabled={locked} onChange={(e) => setLanguage(e.target.value)}>
              <option value="python">Python</option>
              <option value="c">C</option>
              <option value="java">Java</option>
            </select>

            <h3>
              Test cases <span className="hint">-- first one is shown to students as a worked example</span>
            </h3>
            <div id="test-cases">
              {testCases.map((tc, i) => (
                <div className="test-case-row" key={i}>
                  <textarea
                    className="tc-stdin"
                    placeholder="stdin"
                    value={tc.stdin}
                    disabled={locked}
                    onChange={(e) => updateTestCase(i, "stdin", e.target.value)}
                  />
                  <textarea
                    className="tc-expected"
                    placeholder="expected stdout"
                    value={tc.expected}
                    disabled={locked}
                    onChange={(e) => updateTestCase(i, "expected", e.target.value)}
                  />
                  <button
                    type="button"
                    className="danger remove-tc"
                    disabled={locked}
                    onClick={() => removeTestCaseRow(i)}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="secondary" id="add-testcase-btn" disabled={locked} onClick={addTestCaseRow}>
              + Add test case
            </button>

            <h3>Grading config</h3>
            <div className="row2">
              <div>
                <label htmlFor="f-time">
                  Time limit (seconds) <span className="hint">default 5, capped by the server</span>
                </label>
                <input
                  type="number"
                  id="f-time"
                  min={0.5}
                  step={0.5}
                  value={timeLimit}
                  disabled={locked}
                  onChange={(e) => setTimeLimit(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="f-memory">
                  Memory limit (MB) <span className="hint">default 125, capped by the server</span>
                </label>
                <input
                  type="number"
                  id="f-memory"
                  min={16}
                  step={1}
                  value={memoryLimit}
                  disabled={locked}
                  onChange={(e) => setMemoryLimit(e.target.value)}
                />
              </div>
            </div>
            <div className="row2">
              <div>
                <label htmlFor="f-lines">Submission line limit</label>
                <input
                  type="number"
                  id="f-lines"
                  min={10}
                  step={10}
                  value={lineLimit}
                  disabled={locked}
                  onChange={(e) => setLineLimit(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="f-packages">
                  Extra allowed packages <span className="hint">comma-separated, beyond stdlib</span>
                </label>
                <input
                  type="text"
                  id="f-packages"
                  placeholder="e.g. numpy, requests"
                  value={packages}
                  disabled={locked}
                  onChange={(e) => setPackages(e.target.value)}
                />
              </div>
            </div>

            <h3>Class</h3>
            <label htmlFor="f-expected">
              Expected number of students{" "}
              <span className="hint">optional -- powers the live "X/N submitted" counter on the dashboard</span>
            </label>
            <input
              type="number"
              id="f-expected"
              min={1}
              step={1}
              placeholder="e.g. 22"
              value={expectedStudents}
              disabled={locked}
              onChange={(e) => setExpectedStudents(e.target.value)}
            />

            <label htmlFor="f-duration">
              Time limit for students (minutes){" "}
              <span className="hint">
                countdown shown on the student page -- their code auto-submits when it hits zero
              </span>
            </label>
            <input
              type="number"
              id="f-duration"
              min={1}
              step={1}
              value={durationMinutes}
              disabled={locked}
              onChange={(e) => setDurationMinutes(e.target.value)}
            />

            <h3>
              Reference solution <span className="hint">-- a known-correct solution, used only for the validation preview below</span>
            </h3>
            <textarea
              id="f-reference"
              placeholder="print(sum(int(x) for x in input().split()))"
              value={referenceSolution}
              disabled={locked}
              onChange={(e) => setReferenceSolution(e.target.value)}
            />

            <div id="form-status" style={{ color: formStatusColor }}>
              {formStatusText}
            </div>

            <div style={{ marginTop: "1rem" }}>
              <button id="save-btn" style={{ display: locked ? "none" : "inline-block" }} onClick={saveDraft}>
                Save draft
              </button>
              <button className="secondary" id="validate-btn" onClick={runValidation}>
                Run validation preview
              </button>
              <button className="secondary" id="start-btn" disabled={startDisabled} onClick={startQuestion}>
                Start (go live)
              </button>
            </div>

            {validationResult && (
              <div id="validation-result" className={validationResult.pass ? "pass" : "fail"} style={{ display: "block" }}>
                {validationResult.pass ? (
                  "All test cases passed against the reference solution. Ready to start."
                ) : (
                  <>
                    The reference solution did not pass every test case -- fix the rubric or the solution before
                    starting:
                    <ul>
                      {validationResult.failing.map((r, i) => (
                        <li key={i}>
                          stdin <code>{r.stdin}</code> -- expected <code>{r.expected_stdout}</code>, got{" "}
                          <code>{(r.stdout || "").trim()}</code>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  );
}
