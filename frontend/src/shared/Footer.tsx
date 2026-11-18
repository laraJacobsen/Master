import { APP_COMMIT, APP_VERSION, BRAND } from "./brand";
import { ROUTES } from "./routes";
import { LogoMark } from "./Logo";
import { cx } from "./cx";

export interface FooterProps {
  className?: string;
}

// The quiet line at the bottom of the "document" pages (home, history, setup,
// the student join and end screens, help, privacy). Left off the full-screen
// working views -- live dashboard, projector, the student's editor -- where
// every pixel is the task.
export function Footer({ className }: FooterProps) {
  return (
    <footer className={cx("border-t border-zinc-200", className)}>
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-5 py-6 text-[13px] text-zinc-500 sm:px-8">
        <span className="flex items-center gap-2">
          <LogoMark className="size-5" />
          <span className="font-semibold text-zinc-700">{BRAND.name}</span>
        </span>
        <nav aria-label="Footer" className="flex items-center gap-5">
          <FooterLink href={ROUTES.help}>Help</FooterLink>
          <FooterLink href={ROUTES.privacy}>Privacy</FooterLink>
        </nav>
        <span className="ml-auto font-mono text-xs text-zinc-400 tabular-nums" title={`Build ${APP_COMMIT}`}>
          v{APP_VERSION}
          {APP_COMMIT && <span className="text-zinc-300"> · {APP_COMMIT}</span>}
        </span>
      </div>
    </footer>
  );
}

interface FooterLinkProps {
  href: string;
  children: string;
}

function FooterLink({ href, children }: FooterLinkProps) {
  return (
    <a
      href={href}
      className="rounded-sm transition-colors hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
    >
      {children}
    </a>
  );
}
