import type { ReactNode } from "react";
import { cx } from "./cx";

export interface HeaderNavLinkProps {
  href: string;
  children: ReactNode;
  className?: string;
}

// Small "back to ..." link that sits in a page header (e.g. lecturer
// dashboard -> question setup).
export function HeaderNavLink({ href, children, className }: HeaderNavLinkProps) {
  return (
    <a
      href={href}
      className={cx(
        "inline-flex items-center gap-1 rounded-md text-[13px] font-medium text-zinc-500 transition-colors " +
          "hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
        className,
      )}
    >
      {children}
    </a>
  );
}
