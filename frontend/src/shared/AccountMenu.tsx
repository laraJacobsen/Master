import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchLecturerSession, lecturerLogout } from "./api";
import { ROUTES } from "./routes";
import { cx } from "./cx";
import { toast } from "./toast";

export interface AccountMenuProps {
  /** On the live dashboard's purple band: white-on-glass trigger. */
  onBand: boolean;
}

// The lecturer's menu at the right end of the nav bar. There's one shared
// lecturer password (backend/auth.py), not personal accounts, so it's
// "Lecturer" rather than a name. Sign out only shows when the server
// actually has a login -- with LECTURER_PASSWORD unset there's nothing to
// sign out of.
export function AccountMenu({ onBand }: AccountMenuProps) {
  const [open, setOpen] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    fetchLecturerSession()
      .then((s) => setAuthRequired(s.auth_required))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function signOut() {
    setSigningOut(true);
    try {
      await lecturerLogout();
      // A fresh load lands on the login screen (LecturerGate).
      window.location.href = ROUTES.home;
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't sign out.", "danger");
      setSigningOut(false);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cx(
          "flex items-center gap-2 rounded-lg py-1 pr-2 pl-1 text-[13px] font-medium transition-colors",
          "focus-visible:outline-2 focus-visible:outline-offset-2",
          onBand
            ? "text-white hover:bg-white/10 focus-visible:outline-white"
            : "text-zinc-700 hover:bg-zinc-100 focus-visible:outline-brand-500",
          open && (onBand ? "bg-white/10" : "bg-zinc-100"),
        )}
      >
        <span
          className={cx(
            "grid size-7 place-items-center rounded-md text-[11px] font-bold",
            onBand ? "bg-white/20 text-white" : "bg-brand-100 text-brand-700",
          )}
          aria-hidden="true"
        >
          L
        </span>
        <span className="hidden md:inline">Lecturer</span>
        <svg viewBox="0 0 16 16" className={cx("size-3.5 transition-transform", open && "rotate-180")} aria-hidden="true">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Lecturer menu"
          className="absolute top-full right-0 z-50 mt-2 w-56 animate-pop-in overflow-hidden rounded-xl border border-zinc-200 bg-white py-1.5 text-zinc-900 shadow-xl shadow-zinc-950/10"
        >
          <div className="border-b border-zinc-100 px-3.5 pt-1.5 pb-2.5">
            <div className="text-[13px] font-semibold">Lecturer</div>
            <div className="text-xs text-zinc-500">{authRequired ? "Signed in" : "Local mode, no login set up"}</div>
          </div>
          <div className="py-1">
            <MenuLink href={ROUTES.history}>Lecture history</MenuLink>
            <MenuLink href={ROUTES.privacy}>Privacy</MenuLink>
          </div>
          {authRequired && (
            <div className="border-t border-zinc-100 pt-1">
              <button
                type="button"
                role="menuitem"
                onClick={signOut}
                disabled={signingOut}
                className="block w-full px-3.5 py-2 text-left text-[13px] text-red-600 transition-colors hover:bg-red-50 focus-visible:bg-red-50 focus-visible:outline-none disabled:opacity-60"
              >
                {signingOut ? "Signing out…" : "Sign out"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface MenuLinkProps {
  href: string;
  children: ReactNode;
}

function MenuLink({ href, children }: MenuLinkProps) {
  return (
    <a
      role="menuitem"
      href={href}
      className="block px-3.5 py-2 text-[13px] text-zinc-700 transition-colors hover:bg-zinc-50 hover:text-zinc-950 focus-visible:bg-zinc-50 focus-visible:outline-none"
    >
      {children}
    </a>
  );
}
