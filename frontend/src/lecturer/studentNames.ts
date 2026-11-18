import type { StudentTrack } from "./studentTracks";

// Names are hidden by default (numbered instead) -- this dashboard can end
// up on a shared screen. Remembered per browser so it doesn't reset every task.
const NAMES_KEY = "lecturer.studentGrid.names";

export function saveShowNames(show: boolean) {
  try {
    window.localStorage.setItem(NAMES_KEY, show ? "1" : "0");
  } catch {
    // Storage blocked -- the toggle still works for this page view.
  }
}

export function readShowNames(): boolean {
  try {
    return window.localStorage.getItem(NAMES_KEY) === "1";
  } catch {
    return false;
  }
}

// A tile/drawer label: the name, or the student's alphabetical class number
// ("#04") when names are hidden. Takes the whole class's tracks so the number
// is the same wherever the student appears.
export function studentLabeler(tracks: StudentTrack[], showNames: boolean): (t: StudentTrack) => string {
  const number = new Map(tracks.map((t, i) => [t.name, String(i + 1).padStart(2, "0")]));
  return (t) => (showNames ? t.name : `#${number.get(t.name)}`);
}
