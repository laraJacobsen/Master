import { useState } from "react";
import type { ReactNode } from "react";
import type { SubmissionRow, ValidationTestResult } from "../shared/types";
import { spellings, varyingSlots } from "./codeGroups";

// Names to mark in the code: slot -> tooltip ("also: m, biggest").
type NameMarks = Map<number, string>;

function markedCode(sub: SubmissionRow, marks: NameMarks | undefined): ReactNode {
  const spans = (sub.shape_spans ?? []).filter(([slot]) => marks?.has(slot));
  if (!marks || spans.length === 0) return sub.source_code;
  const out: ReactNode[] = [];
  let at = 0;
  for (const [slot, start, end] of [...spans].sort((a, b) => a[1] - b[1])) {
    if (start < at) continue;
    out.push(sub.source_code.slice(at, start));
    out.push(
      <mark key={start} className="name-var" title={marks.get(slot)}>
        {sub.source_code.slice(start, end)}
      </mark>,
    );
    at = end;
  }
  out.push(sub.source_code.slice(at));
  return out;
}

// One submission's code plus the first test it failed, as an
// input / expected / got strip -- shared by an issue's "View code" and a
// student tile's detail panel.
export function SubmissionDetail({ sub, marks }: { sub: SubmissionRow; marks?: NameMarks }) {
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
      <code className="example-code">{markedCode(sub, marks)}</code>
    </>
  );
}

function names(subs: SubmissionRow[]): string {
  return subs.map((s) => s.student_name).join(", ");
}

// One "same code" group (see codeGroups.ts): shown once, in its most common
// naming, with the names that differ between students marked and a chip per
// naming to switch to how someone else wrote it.
export function ExampleBlock({ subs }: { subs: SubmissionRow[] }) {
  const variants = spellings(subs);
  const varying = varyingSlots(variants);
  // Remembered by naming, not position, so a poll that reorders the chips
  // doesn't swap the code out from under the lecturer.
  const [pickedKey, setPickedKey] = useState<string | null>(null);
  const current = variants.find((v) => v.key === pickedKey) ?? variants[0];
  const sub = current.subs[0];

  const marks: NameMarks = new Map(
    [...varying].map((slot) => {
      const others = [...new Set(variants.map((v) => v.names[slot]))].filter((n) => n !== current.names[slot]);
      return [slot, `Same variable, also called: ${others.join(", ")}`];
    }),
  );

  return (
    <div className="example">
      <div className="example-meta">
        {subs.length > 1 && <strong>{subs.length} students</strong>}
        {variants.length > 1
          ? ` · same code, ${variants.length} ways of naming it`
          : `${subs.length > 1 ? ": " : ""}${names(subs)}`}
        {` · ${sub.tests_passed}/${sub.tests_total} tests`}
      </div>
      {variants.length > 1 && (
        <div className="spelling-chips" role="group" aria-label="Naming variants">
          {variants.map((v) => (
            <button
              key={v.key}
              className="spelling-chip"
              aria-pressed={v === current}
              title={names(v.subs)}
              onClick={() => setPickedKey(v.key)}
            >
              <span className="spelling-chip-names">
                {[...varying].map((slot) => v.names[slot]).join(" · ")}
              </span>
              {v.subs.length > 1 && <span className="spelling-chip-count">{v.subs.length}</span>}
            </button>
          ))}
          <span className="spelling-by">{names(current.subs)}</span>
        </div>
      )}
      <SubmissionDetail sub={sub} marks={varying.size ? marks : undefined} />
    </div>
  );
}
