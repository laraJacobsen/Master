import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  Ref,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { cx } from "./cx";

// Shared, typed building blocks for every page. All visual rules from
// .claude/skills/ui-design.md live here once: zinc palette, ultra-thin
// borders, rounded-lg/xl (never rounded-full on controls), tight bold
// headings, and explicit hover / focus-visible / disabled states.


const focusRing =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500";

// ---------------------------------------------------------------- Buttons

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "danger-ghost";
export type ButtonSize = "sm" | "md" | "lg";

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap select-none " +
  "transition-colors duration-150 disabled:cursor-not-allowed " +
  focusRing;

const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-500 text-white shadow-sm shadow-brand-500/25 hover:bg-brand-600 active:bg-brand-700 " +
    "disabled:bg-zinc-200 disabled:text-zinc-400 disabled:shadow-none",
  secondary:
    "border border-zinc-200 bg-white text-zinc-900 hover:border-zinc-300 hover:bg-zinc-100 " +
    "disabled:bg-white disabled:text-zinc-400 disabled:hover:border-zinc-200",
  danger:
    "bg-red-600 text-white hover:bg-red-700 active:bg-red-800 " +
    "disabled:bg-red-200 disabled:text-white",
  ghost:
    "text-zinc-600 hover:bg-brand-50 hover:text-brand-700 " +
    "disabled:text-zinc-300 disabled:hover:bg-transparent",
  "danger-ghost":
    "text-zinc-500 hover:bg-red-50 hover:text-red-700 " +
    "disabled:text-zinc-300 disabled:hover:bg-transparent",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-5 text-[15px]",
};

function buttonClass(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cx(buttonBase, buttonVariants[variant], buttonSizes[size], className);
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  ref?: Ref<HTMLButtonElement>;
}

export function Button({ variant = "primary", size = "md", className, type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}

export interface LinkButtonProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/** An <a> that looks like a Button -- for navigation, not actions. */
export function LinkButton({ variant = "primary", size = "md", className, ...rest }: LinkButtonProps) {
  return <a className={buttonClass(variant, size, className)} {...rest} />;
}

export type TextLinkProps = AnchorHTMLAttributes<HTMLAnchorElement>;

export function TextLink({ className, ...rest }: TextLinkProps) {
  return (
    <a
      className={cx(
        "font-medium text-zinc-900 underline decoration-brand-300 underline-offset-4 " +
          "transition-colors hover:text-brand-700 hover:decoration-brand-500 rounded-sm",
        focusRing,
        className,
      )}
      {...rest}
    />
  );
}

// ------------------------------------------------------------- Surfaces

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Remove the default inner padding (for cards with their own sections). */
  flush?: boolean;
}

export function Card({ flush = false, className, ...rest }: CardProps) {
  return (
    <div
      className={cx("rounded-xl bg-white shadow-card", !flush && "p-5 sm:p-6", className)}
      {...rest}
    />
  );
}

export interface SectionTitleProps {
  children: ReactNode;
  /** Small text to the right of the title. */
  meta?: ReactNode;
  /** Controls aligned to the far right. */
  actions?: ReactNode;
  className?: string;
  as?: "h2" | "h3";
}

export function SectionTitle({ children, meta, actions, className, as: Tag = "h2" }: SectionTitleProps) {
  return (
    <div className={cx("flex flex-wrap items-center gap-x-3 gap-y-2", className)}>
      <Tag className="text-[15px] font-bold tracking-tight text-zinc-900">{children}</Tag>
      {meta && <span className="text-[13px] text-zinc-500">{meta}</span>}
      {actions && <div className="ml-auto flex flex-wrap items-center justify-end gap-2">{actions}</div>}
    </div>
  );
}

export interface EyebrowProps {
  children: ReactNode;
  className?: string;
}

/** Small uppercase label that sits above a heading or value. */
export function Eyebrow({ children, className }: EyebrowProps) {
  return (
    <div className={cx("text-[11px] font-semibold tracking-[0.08em] text-zinc-500 uppercase", className)}>
      {children}
    </div>
  );
}

export interface PageHeaderProps {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Left-aligned page title block -- big, tight type with actions on the right. */
export function PageHeader({ title, eyebrow, description, actions, className }: PageHeaderProps) {
  return (
    <header className={cx("flex flex-wrap items-end gap-x-8 gap-y-4 pt-10 pb-8 sm:pt-14", className)}>
      <div className="w-full min-w-0 sm:w-auto sm:flex-1">
        {eyebrow && <Eyebrow className="mb-3">{eyebrow}</Eyebrow>}
        <h1 className="text-3xl font-bold tracking-tight text-balance text-zinc-950 sm:text-4xl">{title}</h1>
        {description && <div className="mt-3 max-w-2xl text-[15px] text-zinc-500">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export interface PageProps {
  children: ReactNode;
  width?: "narrow" | "default" | "wide" | "full";
  className?: string;
}

export function Page({ children, width = "default", className }: PageProps) {
  const max =
    width === "narrow" ? "max-w-3xl" : width === "wide" ? "max-w-7xl" : width === "full" ? "max-w-[112rem]" : "max-w-6xl";
  return <div className={cx("mx-auto w-full px-5 pb-20 sm:px-8", max, className)}>{children}</div>;
}

// ------------------------------------------------------------------ Forms

export interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  hint?: ReactNode;
}

export function Label({ hint, className, children, ...rest }: LabelProps) {
  return (
    <label className={cx("mb-1.5 block text-[13px] font-semibold text-zinc-900", className)} {...rest}>
      {children}
      {hint && <span className="ml-1.5 font-normal text-zinc-500">{hint}</span>}
    </label>
  );
}

const fieldBase =
  "block w-full rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-900 " +
  "placeholder:text-zinc-400 transition-[border-color,box-shadow] duration-150 " +
  "hover:border-zinc-300 focus:border-brand-500 focus:ring-3 focus:ring-brand-500/15 focus:outline-none " +
  "disabled:cursor-not-allowed disabled:bg-zinc-50 disabled:text-zinc-400 " +
  "aria-invalid:border-red-500 aria-invalid:focus:ring-red-500/15";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean;
  ref?: Ref<HTMLInputElement>;
}

export function Input({ mono = false, className, ...rest }: InputProps) {
  return <input className={cx(fieldBase, "h-10", mono && "font-mono", className)} {...rest} />;
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  mono?: boolean;
  ref?: Ref<HTMLTextAreaElement>;
}

export function Textarea({ mono = false, className, ...rest }: TextareaProps) {
  return (
    <textarea
      className={cx(fieldBase, "min-h-24 resize-y py-2.5 leading-relaxed", mono && "font-mono text-[13px]", className)}
      {...rest}
    />
  );
}

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function Select({ className, ...rest }: SelectProps) {
  return <select className={cx(fieldBase, "h-10 pr-8", className)} {...rest} />;
}

export interface FieldHelpProps {
  children: ReactNode;
  className?: string;
}

export function FieldHelp({ children, className }: FieldHelpProps) {
  return <p className={cx("mt-1.5 text-[13px] text-zinc-500", className)}>{children}</p>;
}

// --------------------------------------------------------------- Feedback

export interface ErrorTextProps {
  children: ReactNode;
  className?: string;
}

export function ErrorText({ children, className }: ErrorTextProps) {
  return (
    <p role="alert" className={cx("text-[13px] font-medium text-red-600", className)}>
      {children}
    </p>
  );
}

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "inverse";

const badgeText: Record<Tone, string> = {
  neutral: "text-zinc-500",
  success: "text-emerald-700",
  warning: "text-amber-700",
  danger: "text-red-700",
  info: "text-brand-700",
  inverse: "text-zinc-950 font-semibold",
};

const badgeMark: Record<Tone, string> = {
  neutral: "bg-zinc-400",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  info: "bg-brand-500",
  inverse: "bg-zinc-950",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  /** Animate the marker (for "live" states). */
  pulse?: boolean;
}

/** A status label: small coloured square + coloured text. No box -- not a pill. */
export function Badge({ tone = "neutral", pulse = false, className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cx("inline-flex items-center gap-1.5 text-[13px] font-medium whitespace-nowrap", badgeText[tone], className)}
      {...rest}
    >
      <span className={cx("size-1.5 flex-none rounded-[2px]", badgeMark[tone], pulse && "animate-pulse-dot")} aria-hidden="true" />
      {children}
    </span>
  );
}

const calloutTones: Record<Exclude<Tone, "inverse">, string> = {
  neutral: "border-zinc-200 bg-zinc-50 text-zinc-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-red-200 bg-red-50 text-red-900",
  info: "border-brand-200 bg-brand-50 text-brand-900",
};

export interface CalloutProps extends HTMLAttributes<HTMLDivElement> {
  tone?: Exclude<Tone, "inverse">;
}

export function Callout({ tone = "neutral", className, ...rest }: CalloutProps) {
  return <div className={cx("rounded-lg border px-4 py-3 text-sm", calloutTones[tone], className)} {...rest} />;
}

export interface ProgressBarProps {
  /** 0..1 */
  value: number;
  tone?: "neutral" | "success" | "warning" | "danger";
  className?: string;
  label?: string;
}

const barTones: Record<NonNullable<ProgressBarProps["tone"]>, string> = {
  neutral: "bg-brand-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
};

export function ProgressBar({ value, tone = "neutral", className, label }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div
      className={cx("h-1.5 w-full overflow-hidden rounded-sm bg-zinc-200", className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-label={label}
    >
      <div className={cx("h-full rounded-sm transition-[width] duration-500", barTones[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}

export interface StatProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  className?: string;
}

/** A labelled number -- numbers render in tabular monospace. */
export function Stat({ label, value, sub, className }: StatProps) {
  return (
    <div className={className}>
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-1.5 font-mono text-2xl font-semibold tracking-tight text-zinc-950 tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-[13px] text-zinc-500">{sub}</div>}
    </div>
  );
}

export interface EmptyStateProps {
  title: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function EmptyState({ title, children, className }: EmptyStateProps) {
  return (
    <div className={cx("rounded-xl border border-dashed border-zinc-300 px-6 py-10 text-center", className)}>
      <p className="text-sm font-semibold text-zinc-900">{title}</p>
      {children && <div className="mt-1.5 text-[13px] text-zinc-500">{children}</div>}
    </div>
  );
}

export interface MutedProps {
  children: ReactNode;
  className?: string;
}

export function Muted({ children, className }: MutedProps) {
  return <p className={cx("text-sm text-zinc-500", className)}>{children}</p>;
}

export interface CodeProps {
  children: ReactNode;
  className?: string;
}

/** Inline code -- student output, inputs, identifiers. */
export function Code({ children, className }: CodeProps) {
  return (
    <code
      className={cx(
        "font-mono text-[0.9em] font-medium whitespace-pre-wrap text-zinc-950",
        className,
      )}
    >
      {children}
    </code>
  );
}

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
}

export function Checkbox({ label, className, ...rest }: CheckboxProps) {
  return (
    <label className={cx("inline-flex cursor-pointer items-center gap-2 text-[13px] text-zinc-600 select-none hover:text-zinc-900", className)}>
      <input
        type="checkbox"
        className="size-4 rounded border-zinc-300 accent-brand-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
        {...rest}
      />
      {label}
    </label>
  );
}

export interface SpinnerProps {
  className?: string;
}

/** Inherits its colour from the surrounding text (currentColor). */
export function Spinner({ className }: SpinnerProps) {
  return (
    <svg className={cx("size-3.5 animate-spin", className)} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14.5 8A6.5 6.5 0 0 0 8 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export interface BrandMarkProps {
  /** Hide the wordmark on small screens. */
  compact?: boolean;
  className?: string;
}

export function BrandMark({ compact = false, className }: BrandMarkProps) {
  return (
    <span className={cx("flex items-center gap-2.5", className)}>
      <span
        className="grid size-7 place-items-center rounded-md bg-linear-to-br from-brand-500 to-violet-500 font-mono text-[11px] font-bold text-white"
        aria-hidden="true"
      >
        IL
      </span>
      <span className={cx("text-sm font-bold tracking-tight text-zinc-950", compact && "hidden sm:inline")}>
        Interactive Lecture
      </span>
    </span>
  );
}

export interface StatusLineProps {
  /** "live" pulses green; "closed" and "idle" are muted. */
  state: "live" | "closed" | "idle";
  label: string;
  /** Further plain facts, shown separated by slashes (language, ...). */
  items?: Array<ReactNode | false | null | undefined>;
  className?: string;
}

/** The small line above a page title: "● Live / Python / Last task". */
export function StatusLine({ state, label, items = [], className }: StatusLineProps) {
  const rest = items.filter(Boolean);
  return (
    <div className={cx("flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] font-medium", className)}>
      {state === "live" ? (
        <span className="inline-flex items-center gap-1.5 text-emerald-700">
          <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-emerald-500" aria-hidden="true" />
          {label}
        </span>
      ) : (
        <span className="text-zinc-500">{label}</span>
      )}
      {rest.map((item, i) => (
        <span key={i} className="contents">
          <span className="text-zinc-300" aria-hidden="true">
            /
          </span>
          <span className="text-zinc-500">{item}</span>
        </span>
      ))}
    </div>
  );
}

export interface TimeLineProps {
  /** Share of the time left, 0..1. */
  fraction: number;
  className?: string;
}

/** The time left as a hairline draining across the page; red near the end. */
export function TimeLine({ fraction, className }: TimeLineProps) {
  const f = Math.min(1, Math.max(0, fraction));
  return (
    <div className={cx("h-0.5 w-full bg-zinc-200", className)} aria-hidden="true">
      <div
        className={cx("h-full transition-[width] duration-1000 ease-linear", f <= 0.15 ? "bg-red-500" : "bg-brand-500")}
        style={{ width: `${f * 100}%` }}
      />
    </div>
  );
}

export interface BigTimerProps {
  seconds: number | null;
  className?: string;
}

export function formatMMSS(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
}

/** "Time left 4:12" -- big monospace, red once it hits zero. */
export function BigTimer({ seconds, className }: BigTimerProps) {
  const up = seconds === 0;
  return (
    <div className={cx("sm:text-right", className)}>
      <Eyebrow className={up ? "text-red-600" : undefined}>{up ? "Time's up" : "Time left"}</Eyebrow>
      <div
        role="timer"
        className={cx(
          "mt-1 font-mono text-5xl leading-none font-semibold tracking-tight tabular-nums",
          up ? "text-red-600" : "text-zinc-950",
        )}
      >
        {seconds != null ? formatMMSS(seconds) : "--:--"}
      </div>
    </div>
  );
}

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
}

export interface SegmentedControlProps<T extends string> {
  options: ReadonlyArray<SegmentedOption<T>>;
  value: T;
  onChange: (value: T) => void;
  /** Accessible name for the group, e.g. "Time range". */
  label: string;
  className?: string;
}

/** A small set of mutually exclusive views (e.g. Month / Semester). */
export function SegmentedControl<T extends string>({ options, value, onChange, label, className }: SegmentedControlProps<T>) {
  return (
    <div role="group" aria-label={label} className={cx("inline-flex gap-0.5 rounded-lg bg-zinc-100 p-0.5", className)}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={cx(
              "h-7 rounded-md px-3 text-[13px] font-medium transition-colors",
              focusRing,
              on ? "bg-white text-brand-700 shadow-sm shadow-zinc-950/5" : "text-zinc-500 hover:text-zinc-900",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export interface SkeletonProps {
  className?: string;
}

/** A grey placeholder block with a soft shimmer, sized by className. */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cx(
        "animate-shimmer rounded-md bg-[length:200%_100%]",
        "bg-[linear-gradient(90deg,var(--color-zinc-100)_25%,var(--color-zinc-200)_50%,var(--color-zinc-100)_75%)]",
        className,
      )}
    />
  );
}
