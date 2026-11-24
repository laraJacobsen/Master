// Autosave for the student workspace: the code and the Run input are kept in
// this browser's localStorage per task and student, so a reload, a crashed tab
// or an accidental close mid-task doesn't lose what they wrote. Nothing is
// sent anywhere -- the server only ever sees code on Run or Submit.

const PREFIX = "il.draft:";
// Old tasks' drafts are dropped after this long, so storage doesn't fill up.
const KEEP_MS = 14 * 24 * 60 * 60 * 1000;

export interface Draft {
  code: string;
  input: string;
  // Test-graded tasks: every editable file, {path: content}.
  files?: Record<string, string>;
  savedAt: number;
}

export function draftKey(questionId: string, studentName: string): string {
  return `${PREFIX}${questionId}:${studentName.trim().toLowerCase()}`;
}

export function loadDraft(key: string): Draft | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const d = JSON.parse(raw) as Partial<Draft>;
    if (typeof d.code !== "string") return null;
    const files =
      d.files && typeof d.files === "object" && Object.values(d.files).every((v) => typeof v === "string")
        ? d.files
        : undefined;
    return { code: d.code, input: typeof d.input === "string" ? d.input : "", files, savedAt: d.savedAt ?? 0 };
  } catch {
    return null;
  }
}

/** False if the browser refused (private mode, storage full). */
export function saveDraft(key: string, draft: Omit<Draft, "savedAt">): boolean {
  try {
    localStorage.setItem(key, JSON.stringify({ ...draft, savedAt: Date.now() }));
    return true;
  } catch {
    return false;
  }
}

export function pruneOldDrafts(): void {
  try {
    const cutoff = Date.now() - KEEP_MS;
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (!key?.startsWith(PREFIX)) continue;
      const d = loadDraft(key);
      if (!d || d.savedAt < cutoff) localStorage.removeItem(key);
    }
  } catch {
    // Best effort.
  }
}
