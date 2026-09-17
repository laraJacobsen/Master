import { useEffect, useState } from "react";
import type { QuestionRow, QuestionStatus, ValidationTestResult } from "../shared/types";
import {
  createQuestion,
  fetchQuestionList,
  startQuestion as startQuestionApi,
  updateQuestion,
  validateQuestion as validateQuestionApi,
} from "../shared/api";

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
  const [referenceSolution, setReferenceSolution] = useState("");

  const [formStatusText, setFormStatusText] = useState("");
  const [formStatusColor, setFormStatusColor] = useState("var(--muted)");
  const [validationResult, setValidationResult] = useState<ValidationResultState | null>(null);
  const [startDisabled, setStartDisabled] = useState(true);

  const locked = currentStatus === "live";

  function loadQuestionList() {
    fetchQuestionList()
      .then(setQuestions)
      .catch(() => {
        // Backend not reachable -- leave the last-known list in place.
      });
  }

  useEffect(() => {
    loadQuestionList();
  }, []);

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
    };
  }

  async function saveDraft() {
    const payload = formPayload();
    if (!payload.title || !payload.prompt || payload.test_cases.length === 0) {
      setFormStatusText("Title, prompt, and at least one test case are required.");
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
      </header>
      <main>
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
                      <span className={"status-pill " + (q.status === "live" ? "status-live" : "status-draft")}>
                        {q.status}
                      </span>{" "}
                      {q.id}
                    </div>
                  </div>
                  {q.status === "live" && (
                    <a href={`lecturer.html?question_id=${encodeURIComponent(q.id)}`}>Live dashboard &rarr;</a>
                  )}
                </li>
              ))}
            </ul>
            <button className="secondary" id="new-question-btn" style={{ marginTop: "0.9rem" }} onClick={resetForm}>
              + New question
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
