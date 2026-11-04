import { useState } from "react";
import type { ReactNode } from "react";
import type { SubmissionRow, ValidationTestResult } from "../shared/types";
import { nameSlots } from "./codeGroups";

// Names to mark in the code: slot -> tooltip ("also called ...").
type NameMarks = Map<number, string>;

// The code as text with the student's own names swapped for `names` (when
// given) and the slots in `marks` wrapped in a <mark>.
function markedCode(sub: SubmissionRow, names: string[] | undefined, marks: NameMarks | undefined): ReactNode {
  if (!names && !marks) return sub.source_code;
  const out: ReactNode[] = [];
  let at = 0;
  for (const [slot, start, end] of [...(sub.shape_spans ?? [])].sort((a, b) => a[1] - b[1])) {
    if (start < at) continue;
    const text = names?.[slot] ?? sub.source_code.slice(start, end);
    out.push(sub.source_code.slice(at, start));
    out.push(
      marks?.has(slot) ? (
        <mark key={start} className="name-var" title={marks.get(slot)}>
          {text}
        </mark>
      ) : (
        text
      ),
    );
    at = end;
  }
  out.push(sub.source_code.slice(at));
  return out;
}

// One submission's code plus the first test it failed, as an
// input / expected / got strip -- shared by an issue's "View code" and a
// student tile's detail panel.
export interface SubmissionDetailProps {
  sub: SubmissionRow;
  // Show the code with these names in place of the student's own (by slot).
  names?: string[];
  marks?: NameMarks;
}

export function SubmissionDetail({ sub, names, marks }: SubmissionDetailProps) {
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
      <code className="example-code">{markedCode(sub, names, marks)}</code>
    </>
  );
}

// "Ada, Bo, Cy +16" -- a group can be most of the class.
function someNames(subs: SubmissionRow[]): string {
  const all = subs.map((s) => s.student_name);
  return all.length > 3 ? `${all.slice(0, 3).join(", ")} +${all.length - 3}` : all.join(", ");
}

function alsoCalled(names: { name: string; count: number }[]): string {
  return names.map((n) => (n.count > 1 ? `${n.name} (${n.count})` : n.name)).join(", ");
}

// How many alternative names to list per variable before "+N more".
const MAX_ALTERNATIVES = 4;

export interface ExampleBlockProps {
  subs: SubmissionRow[];
}

// One "same code" group (see codeGroups.ts), shown once with the most common
// name for each variable. The names that vary are marked, with the others
// listed per variable underneath -- one line per variable however many
// students there are. "Show as written by" switches to one student's exact code.
export function ExampleBlock({ subs }: ExampleBlockProps) {
  const [viewAs, setViewAs] = useState("");
  const slots = nameSlots(subs);
  const varying = slots.filter((s) => s.names.length > 1);
  const student = subs.find((s) => s.student_name === viewAs) ?? null;
  const base = student ?? subs[0];
  const shown = student ? (student.shape_names ?? []) : slots.map((s) => s.names[0]?.name ?? "");

  const marks: NameMarks = new Map(
    varying.map((s) => [s.slot, `Also called: ${alsoCalled(s.names.filter((n) => n.name !== shown[s.slot]))}`]),
  );

  return (
    <div className="example">
      <div className="example-head">
        <div className="example-meta">
          {subs.length > 1 && <strong>{subs.length} students </strong>}
          {someNames(subs)} · {base.tests_passed}/{base.tests_total} tests
        </div>
        {varying.length > 0 && (
          <label className="view-as">
            Show as written by
            <select value={student ? viewAs : ""} onChange={(e) => setViewAs(e.target.value)}>
              <option value="">Most common names</option>
              {[...subs]
                .sort((a, b) => a.student_name.localeCompare(b.student_name))
                .map((s) => (
                  <option key={s.id} value={s.student_name}>
                    {s.student_name}
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>
      <SubmissionDetail sub={base} names={varying.length ? shown : undefined} marks={varying.length ? marks : undefined} />
      {varying.length > 0 && (
        <dl className="name-legend" aria-label="Other names students used">
          {varying.map((s) => {
            const others = s.names.filter((n) => n.name !== shown[s.slot]);
            const more = others.length - MAX_ALTERNATIVES;
            return (
              <div key={s.slot} className="name-legend-row">
                <dt>{shown[s.slot]}</dt>
                <dd>
                  <span className="name-legend-also">also</span> {alsoCalled(others.slice(0, MAX_ALTERNATIVES))}
                  {more > 0 && <span className="name-legend-more"> +{more} more</span>}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </div>
  );
}
