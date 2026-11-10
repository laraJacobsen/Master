import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { ActiveLectureResponse } from "./types";
import { fetchActiveLecture } from "./api";
import { activeLectureAction } from "./lectureNav";
import { LinkButton } from "./ui";
import { cx } from "./cx";

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
// from), "History" opens the past-lectures page (history.html) from
// anywhere, and the right-hand shortcut is always the single obvious next
// step for wherever the lecture currently stands, using the exact same
// logic the home page's own resume button uses. That shortcut is a labeled
// action ("New lecture", "Continue setup", ...) rather than a plain "go
// home" link, so unlike the brand link, it must not render at all when it
// would just point at the page already open -- a button that claims to do
// something and then doesn't is worse than no button.
export interface NavBarProps {
  /** Match a full-width page (the live dashboard). */
  wide?: boolean;
}

export function NavBar({ wide = false }: NavBarProps) {
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);

  useEffect(() => {
    fetchActiveLecture()
      .then(setActive)
      .catch(() => {
        // Shortcut just won't render -- the brand link alone still works.
      });
  }, []);

  const action = activeLectureAction(active);
  const onHome = isCurrentPage("index.html");
  const onHistory = isCurrentPage("history.html");
  // "Resume lobby" is left off the nav bar's shortcut on purpose -- the home
  // page's own card already surfaces the join code for that state, and a
  // nav-bar link would just duplicate it without that context.
  const showCta = !isCurrentPage(action.href) && action.label !== "Resume lobby";

  return (
    <nav className="sticky top-0 z-50 border-b border-zinc-200 bg-zinc-50/85 backdrop-blur-md">
      <div className={cx("mx-auto flex h-14 items-center gap-6 px-5 sm:px-8", wide ? "max-w-[112rem]" : "max-w-7xl")}>
        <a
          href="index.html"
          className="group flex items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-zinc-900"
        >
          <span
            className="grid size-7 place-items-center rounded-md bg-zinc-950 font-mono text-[11px] font-bold text-white transition-colors group-hover:bg-zinc-700"
            aria-hidden="true"
          >
            IL
          </span>
          <span className="hidden text-sm font-bold tracking-tight text-zinc-950 sm:inline">Interactive Lecture</span>
        </a>
        {/* Always shown, marked when current -- a nav link that vanishes on its
            own page makes the bar jump around between pages. */}
        <div className="flex items-center gap-1">
          <NavLink href="index.html" current={onHome}>
            Home
          </NavLink>
          <NavLink href="history.html" current={onHistory}>
            History
          </NavLink>
        </div>
        {showCta && (
          <LinkButton href={action.href} size="sm" className="ml-auto">
            {action.label}
          </LinkButton>
        )}
      </div>
    </nav>
  );
}

export interface NavLinkProps {
  href: string;
  current: boolean;
  children: ReactNode;
}

function NavLink({ href, current, children }: NavLinkProps) {
  return (
    <a
      href={href}
      aria-current={current ? "page" : undefined}
      className={cx(
        "relative rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
        current ? "text-zinc-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900",
      )}
    >
      {children}
      {current && <span className="absolute inset-x-2.5 -bottom-[13px] h-px bg-zinc-950" aria-hidden="true" />}
    </a>
  );
}
