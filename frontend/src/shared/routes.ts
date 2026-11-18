// Every page's public URL. The pages are still separate Vite entry points
// (index.html, lecturer.html, ...), but they're served at these clean paths:
// by backend/main.py in production and by the cleanUrls plugin in
// vite.config.ts in dev. The old *.html URLs redirect here, so bookmarks and
// links from before keep working.
export const ROUTES = {
  home: "/",
  setup: "/setup",
  live: "/live",
  history: "/history",
  present: "/present",
  join: "/join",
  help: "/help",
  privacy: "/privacy",
} as const;

function withQuery(path: string, params: Record<string, string | number>): string {
  return `${path}?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()}`;
}

/** The live dashboard for one task. */
export function liveTaskUrl(questionId: string): string {
  return withQuery(ROUTES.live, { question_id: questionId });
}

/** A finished lecture's summary. */
export function lectureSummaryUrl(lectureId: number): string {
  return withQuery(ROUTES.live, { lecture_id: lectureId });
}

/** A lecture's lobby (join code + joined count). */
export function lobbyUrl(lectureId: number): string {
  return withQuery(ROUTES.live, { lobby: lectureId });
}

/** The live dashboard filled with sample data, no backend needed (see lecturer/mockData.ts). */
export const DEMO_DASHBOARD_URL = `${ROUTES.live}?question_id=mock&mock`;

/** The link students can open to join with the code already filled in. */
export function joinLink(joinCode: string): string {
  return `${window.location.origin}${withQuery(ROUTES.join, { code: joinCode })}`;
}
