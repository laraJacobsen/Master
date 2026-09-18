import type { CSSProperties, ReactNode } from "react";

// Replaces the hand-duplicated inline-styled <a> ("<- Home", "Question
// setup ->") that setup.html and lecturer.html each wrote separately --
// same color/size (.header-nav-link, in shared/base.css) both places had.
export function HeaderNavLink({
  href,
  style,
  children,
}: {
  href: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <a href={href} className="header-nav-link" style={style}>
      {children}
    </a>
  );
}
