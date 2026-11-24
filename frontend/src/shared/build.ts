// Is this tab running an old build? The server writes the frontend build it served the
// page from into <meta name="app-build"> (backend/main.py frontend_build()), and reports
// the build it serves now in GET /api/lecture/status. A tab opened before an
// `npm run build` keeps the old code, which misreads newer API responses (it showed
// "undefined" for test results), so pages that poll the status compare the two.

const pageBuild: string | null =
  document.querySelector<HTMLMetaElement>('meta[name="app-build"]')?.content ?? null;

/** True when the server now serves a different build than this page was loaded from.
 * Never in development (the Vite dev server sends no build id). */
export function isStaleBuild(serverBuild: string | null | undefined): boolean {
  return Boolean(pageBuild && serverBuild && serverBuild !== pageBuild);
}

const RELOADED_KEY = "il.reloadedForBuild";

/** Reload once for a given server build. If the page still isn't that build afterwards
 * (a cache in between), don't reload again in a loop. Returns whether it reloaded. */
export function reloadForBuild(serverBuild: string): boolean {
  try {
    if (sessionStorage.getItem(RELOADED_KEY) === serverBuild) return false;
    sessionStorage.setItem(RELOADED_KEY, serverBuild);
  } catch {
    // No sessionStorage: reload anyway, the page sends no-cache so it comes back new.
  }
  window.location.reload();
  return true;
}
