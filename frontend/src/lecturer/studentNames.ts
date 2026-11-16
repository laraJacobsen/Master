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
