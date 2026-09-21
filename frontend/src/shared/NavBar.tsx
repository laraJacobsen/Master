import { useEffect, useState } from "react";
import type { ActiveLectureResponse } from "./types";
import { fetchActiveLecture } from "./api";
import { activeLectureAction } from "./lectureNav";

// A bare "/" (the site root) and "/index.html" are the same page as far as
// FastAPI's StaticFiles(html=True) is concerned -- normalize so comparing
// against the current location can't miss that they match.
function normalizedPath(pathname: string): string {
  return pathname === "/" ? "/index.html" : pathname;
}

function isCurrentPage(href: string): boolean {
  const target = new URL(href, window.location.href);
  return (
    normalizedPath(target.pathname) === normalizedPath(window.location.pathname) &&
    target.search === window.location.search
  );
}

// Persistent top bar across the three lecturer-facing pages (home, setup,
// live dashboard) -- not on student.html, which is a different audience
// with nothing on this bar relevant to it. The brand link is the "go back"
// affordance (clicking it always returns to the one hub every flow starts
// from), and the right-hand shortcut is always the single obvious next
// step for wherever the lecture currently stands, using the exact same
// logic the home page's own resume button uses. That shortcut is a labeled
// action ("New lecture", "Continue setup", ...) rather than a plain "go
// home" link, so unlike the brand link, it must not render at all when it
// would just point at the page already open -- a button that claims to do
// something and then doesn't is worse than no button.
export function NavBar() {
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);

  useEffect(() => {
    fetchActiveLecture()
      .then(setActive)
      .catch(() => {
        // Shortcut just won't render -- the brand link alone still works.
      });
  }, []);

  const action = activeLectureAction(active);
  const showHome = !isCurrentPage("index.html");
  // "Resume lobby" is left off the nav bar's shortcut on purpose -- the home
  // page's own card already surfaces the join code for that state, and a
  // nav-bar link would just duplicate it without that context.
  const showCta = !isCurrentPage(action.href) && action.label !== "Resume lobby";

  return (
    <nav className="top-nav">
      <a href="index.html" className="top-nav-brand">
        Interactive Lecture
      </a>
      <div className="top-nav-actions">
        {showHome && (
          <a href="index.html" className="top-nav-home">
            Home
          </a>
        )}
        {showCta && (
          <a href={action.href} className="top-nav-cta">
            {action.label}
          </a>
        )}
      </div>
    </nav>
  );
}
