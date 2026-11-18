import { useId } from "react";
import { cx } from "./cx";

export interface LogoMarkProps {
  className?: string;
  /** White tile with a brand-coloured glyph, for use on the purple band. */
  inverted?: boolean;
}

/** The brand mark: same geometry as public/favicon.svg. Size it with className. */
export function LogoMark({ className, inverted = false }: LogoMarkProps) {
  const gradientId = useId();
  const glyph = inverted ? "var(--color-brand-600)" : "#fff";
  return (
    <svg viewBox="0 0 32 32" className={cx("size-7 flex-none", className)} aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5E65E8" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={inverted ? "#fff" : `url(#${gradientId})`} />
      <g fill="none" stroke={glyph} strokeLinecap="round" strokeLinejoin="round">
        <path d="M22.93 12A8 8 0 1 1 16 8" strokeWidth="3" />
        <path d="M14 12.8l3.4 3.2-3.4 3.2" strokeWidth="2.6" />
      </g>
      <circle cx="22.93" cy="12" r="2.6" fill={glyph} />
    </svg>
  );
}
