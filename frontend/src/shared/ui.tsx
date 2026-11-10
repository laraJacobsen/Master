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
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";

// ---------------------------------------------------------------- Buttons

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "danger-ghost";
export type ButtonSize = "sm" | "md" | "lg";

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap select-none " +
  "transition-colors duration-150 disabled:cursor-not-allowed " +
  focusRing;

const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "bg-zinc-900 text-white hover:bg-zinc-700 active:bg-zinc-800 " +
    "disabled:bg-zinc-200 disabled:text-zinc-400",
  secondary:
    "border border-zinc-200 bg-white text-zinc-900 hover:border-zinc-300 hover:bg-zinc-100 " +
    "disabled:bg-white disabled:text-zinc-400 disabled:hover:border-zinc-200",
  danger:
    "bg-red-600 text-white hover:bg-red-700 active:bg-red-800 " +
    "disabled:bg-red-200 disabled:text-white",
  ghost:
    "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 " +
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
        "font-medium text-zinc-900 underline decoration-zinc-300 underline-offset-4 " +
          "transition-colors hover:decoration-zinc-900 rounded-sm",
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
      className={cx("rounded-xl border border-zinc-200 bg-white", !flush && "p-5 sm:p-6", className)}
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
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
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
  width?: "narrow" | "default" | "wide";
  className?: string;
}

export function Page({ children, width = "default", className }: PageProps) {
  const max = width === "narrow" ? "max-w-3xl" : width === "wide" ? "max-w-7xl" : "max-w-6xl";
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
  "hover:border-zinc-300 focus:border-zinc-900 focus:ring-3 focus:ring-zinc-900/10 focus:outline-none " +
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

const badgeTones: Record<Tone, string> = {
  neutral: "border-zinc-200 bg-zinc-50 text-zinc-600",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  danger: "border-red-200 bg-red-50 text-red-700",
  info: "border-sky-200 bg-sky-50 text-sky-700",
  inverse: "border-zinc-900 bg-zinc-900 text-white",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  /** Show a leading status dot. */
  dot?: boolean;
  /** Animate the dot (for "live" states). */
  pulse?: boolean;
}

export function Badge({ tone = "neutral", dot = false, pulse = false, className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        badgeTones[tone],
        className,
      )}
      {...rest}
    >
      {dot && <span className={cx("size-1.5 rounded-[2px] bg-current", pulse && "animate-pulse-dot")} aria-hidden="true" />}
      {children}
    </span>
  );
}

const calloutTones: Record<Exclude<Tone, "inverse">, string> = {
  neutral: "border-zinc-200 bg-zinc-50 text-zinc-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-red-200 bg-red-50 text-red-900",
  info: "border-sky-200 bg-sky-50 text-sky-900",
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
  neutral: "bg-zinc-900",
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
        "rounded-md border border-zinc-200 bg-zinc-100 px-1.5 py-px font-mono text-[0.85em] whitespace-pre-wrap text-zinc-900",
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
        className="size-4 rounded border-zinc-300 accent-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
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
        className="grid size-7 place-items-center rounded-md bg-zinc-950 font-mono text-[11px] font-bold text-white"
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
