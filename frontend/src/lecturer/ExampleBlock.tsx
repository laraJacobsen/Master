import type { SubmissionRow, ValidationTestResult } from "../shared/types";

// One submission's code plus the first test it failed, as an
// input / expected / got strip -- shared by an issue's "View code" and a
// student tile's detail panel.
export function SubmissionDetail({ sub }: { sub: SubmissionRow }) {
  const results: ValidationTestResult[] = JSON.parse(sub.raw_test_results || "[]");
  const failing = results.find((r) => !r.passed);
  // A program that didn't compile has no stderr -- the compiler's message is the error output.
  const errorOutput = failing && (failing.stderr || failing.compile_output);

  return (
    <>
      {failing && (
        <div className="io-strip">
          <div className="io-cell">
            <span className="io-label">Input</span>
            <code>{(failing.stdin ?? "").trimEnd() || "(none)"}</code>
          </div>
          <div className="io-cell">
            <span className="io-label">Expected</span>
            <code>{(failing.expected_stdout ?? "").trimEnd()}</code>
          </div>
          <div className="io-cell io-got">
            <span className="io-label">Got</span>
            <code>{(failing.stdout || "").trim() || "(nothing)"}</code>
          </div>
          {errorOutput && (
            <div className="io-cell io-error">
              <span className="io-label">Error</span>
              <code>{errorOutput.trim().split("\n").pop()}</code>
            </div>
          )}
        </div>
      )}
      <code className="example-code">{sub.source_code}</code>
    </>
  );
}

// Students in one cluster often submit character-for-character identical
// code -- shown once, with everyone who wrote it, instead of N copies.
export function ExampleBlock({ subs }: { subs: SubmissionRow[] }) {
  const sub = subs[0];
  const names = subs.map((s) => s.student_name).join(", ");
  return (
    <div className="example">
      <div className="example-meta">
        {subs.length > 1 && <strong>{subs.length}× </strong>}
        {names} · {sub.tests_passed}/{sub.tests_total} tests
      </div>
      <SubmissionDetail sub={sub} />
    </div>
  );
}
