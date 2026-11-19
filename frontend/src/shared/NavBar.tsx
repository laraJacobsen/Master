import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { ActiveLectureResponse } from "./types";
import { fetchActiveLecture } from "./api";
import { activeLectureAction } from "./lectureNav";
import { LinkButton } from "./ui";
import { cx } from "./cx";
import { LogoMark } from "./Logo";
import { BRAND } from "./brand";
import { ROUTES } from "./routes";
import { AccountMenu } from "./AccountMenu";

// Pages are served at clean paths (shared/routes.ts); "/index.html" and a
// trailing slash are the same page -- normalize so comparing against the
// current location can't miss that they match.
function normalizedPath(pathname: string): string {
  if (pathname === "/index.html") return "/";
  return pathname.length > 1 ? pathname.replace(/\/$/, "").replace(/\.html$/, "") : pathname;
}

function isCurrentPage(href: string): boolean {
  const target = new URL(href, window.location.href);
  return (
    normalizedPath(target.pathname) === normalizedPath(window.location.pathname) &&
    target.search === window.location.search
  );
}

// Persistent top bar across the three lecturer-facing pages (home, setup,
// live dashboard) -- not on the student page, which is a different audience
// with nothing on this bar relevant to it. The brand link is the "go back"
// affordance (clicking it always returns to the one hub every flow starts
// from), "History" opens the past-lectures page from
// anywhere, and the right-hand shortcut is always the single obvious next
// step for wherever the lecture currently stands, using the exact same
// logic the home page's own resume button uses. That shortcut is a labeled
// action ("New lecture", "Continue setup", ...) rather than a plain "go
// home" link, so unlike the brand link, it must not render at all when it
// would just point at the page already open -- a button that claims to do
// something and then doesn't is worse than no button.
// Full width on every page (same edges as the student page's bar and the
// live dashboard), so the bar doesn't change width between pages.
export interface NavBarProps {
  /**
   * The live dashboard's coloured band (lecturer/TaskHeader.tsx), by element
   * id: the band runs up under the bar, and the bar is clear glass over it so
   * the band's colour shows through. Once the band is scrolled out from under
   * the bar, the bar goes back to its usual light glass.
   */
  overlayBandId?: string;
}

export function NavBar({ overlayBandId }: NavBarProps) {
  const [overBand, setOverBand] = useState(false);
  const onBand = overlayBandId != null && overBand;
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);

  useEffect(() => {
    if (!overlayBandId) return;
    const check = () => {
      const band = document.getElementById(overlayBandId);
      // 56px = this bar's height (h-14).
      setOverBand(band != null && band.getBoundingClientRect().bottom > 56);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    // The band mounts after the first data arrives -- catch it appearing.
    const t = window.setInterval(check, 500);
    return () => {
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
      window.clearInterval(t);
    };
  }, [overlayBandId]);

  useEffect(() => {
    fetchActiveLecture()
      .then(setActive)
      .catch(() => {
        // Shortcut just won't render -- the brand link alone still works.
      });
  }, []);

  const action = activeLectureAction(active);
  const onHome = isCurrentPage(ROUTES.home);
  const onHistory = isCurrentPage(ROUTES.history);
  const onHelp = isCurrentPage(ROUTES.help);
  // "Resume lobby" is left off the nav bar's shortcut on purpose -- the home
  // page's own card already surfaces the join code for that state, and a
  // nav-bar link would just duplicate it without that context.
  const showCta = !isCurrentPage(action.href) && action.label !== "Resume lobby";

  return (
    <nav
      className={cx(
        "sticky top-0 z-50 border-b backdrop-blur-md transition-colors duration-300",
        // Pulls the band up under the bar.
        overlayBandId && "-mb-14",
        onBand ? "border-white/15 bg-white/10" : "border-zinc-200 bg-zinc-50/85",
      )}
    >
      <div className="mx-auto flex h-14 max-w-[112rem] items-center gap-6 px-5 sm:px-8">
        <a
          href={ROUTES.home}
          className={cx(
            "group flex items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4",
            onBand ? "focus-visible:outline-white" : "focus-visible:outline-brand-500",
          )}
        >
          <LogoMark inverted={onBand} className="transition-opacity group-hover:opacity-85" />
          <span
            className={cx("hidden text-sm font-bold tracking-tight sm:inline", onBand ? "text-white" : "text-zinc-950")}
          >
            {BRAND.name}
          </span>
        </a>
        {/* Always shown, marked when current -- a nav link that vanishes on its
            own page makes the bar jump around between pages. */}
        <div className="flex items-center gap-1">
          <NavLink href={ROUTES.home} current={onHome} onBand={onBand}>
            Home
          </NavLink>
          <NavLink href={ROUTES.history} current={onHistory} onBand={onBand}>
            History
          </NavLink>
          <NavLink href={ROUTES.help} current={onHelp} onBand={onBand}>
            Help
          </NavLink>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {showCta && (
            <LinkButton
              href={action.href}
              size="sm"
              className={cx(
                onBand && "bg-white text-brand-700 hover:bg-brand-50 active:bg-brand-100 focus-visible:outline-white",
              )}
            >
              {action.label}
            </LinkButton>
          )}
          <AccountMenu onBand={onBand} />
        </div>
      </div>
    </nav>
  );
}

export interface NavLinkProps {
  href: string;
  current: boolean;
  onBand: boolean;
  children: ReactNode;
}

function NavLink({ href, current, onBand, children }: NavLinkProps) {
  return (
    <a
      href={href}
      aria-current={current ? "page" : undefined}
      className={cx(
        "relative rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2",
        onBand
          ? cx("focus-visible:outline-white", current ? "text-white" : "text-white/70 hover:bg-white/10 hover:text-white")
          : cx("focus-visible:outline-brand-500", current ? "text-zinc-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"),
      )}
    >
      {children}
      {current && (
        <span
          className={cx("absolute inset-x-2.5 -bottom-[13px] h-0.5 rounded-full", onBand ? "bg-white" : "bg-brand-500")}
          aria-hidden="true"
        />
      )}
    </a>
  );
}
