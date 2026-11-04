import type { SubmissionRow } from "../shared/types";

// Grouping for an issue's "View code": submissions with the same
// backend/code_shape.py key are the same code apart from the names the
// students picked, so they're shown once, with each naming as a variant.

// One group per shape; code with no shape (not Python, or doesn't parse)
// only groups with character-for-character identical code.
export function groupByShape(subs: SubmissionRow[]): SubmissionRow[][] {
  const groups = new Map<string, SubmissionRow[]>();
  for (const sub of subs) {
    const key = groupKey(sub);
    groups.set(key, [...(groups.get(key) ?? []), sub]);
  }
  return [...groups.values()];
}

export function groupKey(sub: SubmissionRow): string {
  return sub.shape_key ? `shape:${sub.shape_key}` : `exact:${sub.source_code.trim()}`;
}

// One naming of a shape group, and everyone who wrote it that way.
export interface Spelling {
  key: string;
  names: string[];
  subs: SubmissionRow[];
}

// Most common naming first (ties: whoever submitted it first), so the
// default view is the version most of the group wrote.
export function spellings(group: SubmissionRow[]): Spelling[] {
  const byNames = new Map<string, Spelling>();
  for (const sub of group) {
    const names = sub.shape_names ?? [];
    const key = names.join("\u0000");
    const sp = byNames.get(key) ?? { key, names, subs: [] };
    sp.subs.push(sub);
    byNames.set(key, sp);
  }
  const firstId = (sp: Spelling) => Math.min(...sp.subs.map((s) => s.id));
  return [...byNames.values()].sort((a, b) => b.subs.length - a.subs.length || firstId(a) - firstId(b));
}

// Name slots that aren't spelled the same in every variant -- the ones to mark.
export function varyingSlots(variants: Spelling[]): Set<number> {
  const slots = new Set<number>();
  if (variants.length < 2) return slots;
  const n = variants[0].names.length;
  for (let i = 0; i < n; i++) {
    if (new Set(variants.map((v) => v.names[i])).size > 1) slots.add(i);
  }
  return slots;
}
