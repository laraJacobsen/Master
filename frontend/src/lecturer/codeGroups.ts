import type { SubmissionRow } from "../shared/types";

// Grouping for an issue's "View code": submissions with the same
// backend/code_shape.py key are the same code apart from the names the
// students picked, so they're shown once -- with the most common name for each
// variable, and the other names listed per variable. Per variable rather than
// per student, so 19 students with 19 different namings is still a handful of
// lines (one per variable), not 19 versions.

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

// One of the program's own names (a "slot"), and what the group called it:
// most common first (ties alphabetical).
export interface NameSlot {
  slot: number;
  names: { name: string; count: number }[];
}

export function nameSlots(group: SubmissionRow[]): NameSlot[] {
  const n = group[0]?.shape_names?.length ?? 0;
  const slots: NameSlot[] = [];
  for (let slot = 0; slot < n; slot++) {
    const counts = new Map<string, number>();
    for (const sub of group) {
      const name = sub.shape_names?.[slot];
      if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    const names = [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    slots.push({ slot, names });
  }
  return slots;
}

// The group's code with each name swapped for `names[slot]` -- every member
// has the same shape, so any member's spans line up with any naming.
export function renamed(sub: SubmissionRow, names: string[]): string {
  const spans = [...(sub.shape_spans ?? [])].sort((a, b) => a[1] - b[1]);
  let out = "";
  let at = 0;
  for (const [slot, start, end] of spans) {
    out += sub.source_code.slice(at, start) + (names[slot] ?? sub.source_code.slice(start, end));
    at = end;
  }
  return out + sub.source_code.slice(at);
}
