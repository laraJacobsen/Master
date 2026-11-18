// Which side of the app this browser was last used for, so the shared public
// pages (help, privacy, 404) send people back to the right place: a lecturer
// clicking the logo on /help goes home, not to the student join screen.
// Set by LecturerGate once a lecturer page opens, and by the student page on
// joining. Only a navigation hint -- access is still the server's call.
export type Role = "lecturer" | "student";

const ROLE_KEY = "classloop.role";

export function rememberRole(role: Role): void {
  try {
    localStorage.setItem(ROLE_KEY, role);
  } catch {
    // Storage blocked: the public pages just fall back to the student links.
  }
}

export function lastRole(): Role | null {
  try {
    const v = localStorage.getItem(ROLE_KEY);
    return v === "lecturer" || v === "student" ? v : null;
  } catch {
    return null;
  }
}
