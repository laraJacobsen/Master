import type { ActiveLectureResponse } from "./types";
import { liveTaskUrl, lobbyUrl, ROUTES } from "./routes";

// Where "the one obvious next step" points, given the current active-lecture
// state -- shared by the home page's own resume button and NavBar's
// always-visible shortcut, so the two can never disagree about it.
export function activeLectureAction(active: ActiveLectureResponse | null): {
  label: string;
  href: string;
} {
  if (!active || !active.lecture) {
    return { label: "New lecture", href: ROUTES.home };
  }
  if (active.live_question_id) {
    return {
      label: "Live dashboard",
      href: liveTaskUrl(active.live_question_id),
    };
  }
  if (active.lecture.lobby_opened_at) {
    return { label: "Resume lobby", href: lobbyUrl(active.lecture.id) };
  }
  return { label: "Continue setup", href: ROUTES.setup };
}
