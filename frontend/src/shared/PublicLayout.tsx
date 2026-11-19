import type { ReactNode } from "react";
import { BrandMark, LinkButton } from "./ui";
import { Footer } from "./Footer";
import { ROUTES } from "./routes";
import { cx } from "./cx";
import { lastRole } from "./role";
import { NavBar } from "./NavBar";

export interface PublicLayoutProps {
  children: ReactNode;
  /** Which public page this is, to mark it in the bar. */
  current?: "help" | "privacy";
}

// The frame for pages anyone can open -- help, privacy, 404. A lecturer gets
// the same NavBar as on every other lecturer page (it was a different bar
// here, which felt like leaving the app); students get a bar with the same
// size and edges, minus the lecturer's links and account menu.
export function PublicLayout({ children, current }: PublicLayoutProps) {
  const isLecturer = lastRole() === "lecturer";
  return (
    <div className="flex min-h-screen flex-col">
      {isLecturer ? <NavBar /> : <StudentPublicBar current={current} />}
      <div className="flex-1">{children}</div>
      <Footer />
    </div>
  );
}

interface StudentPublicBarProps {
  current?: "help" | "privacy";
}

// Same dimensions as NavBar (h-14, full width up to 112rem, same padding).
function StudentPublicBar({ current }: StudentPublicBarProps) {
  return (
    <header className="sticky top-0 z-50 border-b border-zinc-200 bg-zinc-50/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[112rem] items-center gap-6 px-5 sm:px-8">
        <a
          href={ROUTES.join}
          className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-500"
        >
          <BrandMark />
        </a>
        <nav aria-label="Main" className="flex items-center gap-1">
          <BarLink href={ROUTES.help} current={current === "help"}>
            Help
          </BarLink>
          <BarLink href={ROUTES.privacy} current={current === "privacy"}>
            Privacy
          </BarLink>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <LinkButton href={ROUTES.home} variant="ghost" size="sm" className="hidden sm:inline-flex">
            Lecturer
          </LinkButton>
          <LinkButton href={ROUTES.join} size="sm">
            Join a lecture
          </LinkButton>
        </div>
      </div>
    </header>
  );
}

interface BarLinkProps {
  href: string;
  current: boolean;
  children: string;
}

function BarLink({ href, current, children }: BarLinkProps) {
  return (
    <a
      href={href}
      aria-current={current ? "page" : undefined}
      className={cx(
        "relative rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
        current ? "text-zinc-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900",
      )}
    >
      {children}
      {current && <span className="absolute inset-x-2.5 -bottom-[13px] h-0.5 rounded-full bg-brand-500" aria-hidden="true" />}
    </a>
  );
}

export interface ProseSectionProps {
  id: string;
  title: string;
  children: ReactNode;
}

/** A titled block of reading text on the help and privacy pages. */
export function ProseSection({ id, title, children }: ProseSectionProps) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-zinc-200 pt-8">
      <h2 className="text-xl font-bold tracking-tight text-zinc-950">{title}</h2>
      <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-zinc-600 [&_strong]:font-semibold [&_strong]:text-zinc-900 [&_li]:pl-1 [&_ol]:list-decimal [&_ol]:space-y-2 [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}

export interface DocPageProps {
  eyebrow: string;
  title: string;
  intro: ReactNode;
  /** Table of contents: [section id, label]. */
  toc: [string, string][];
  children: ReactNode;
}

/** Help/privacy layout: title and contents on the left, text on the right. */
export function DocPage({ eyebrow, title, intro, toc, children }: DocPageProps) {
  return (
    <main className="mx-auto grid max-w-6xl gap-10 px-5 pt-14 pb-24 sm:px-8 sm:pt-20 lg:grid-cols-12 lg:gap-16">
      <aside className="lg:col-span-4">
        <div className="lg:sticky lg:top-24">
          <p className="text-[11px] font-semibold tracking-[0.08em] text-brand-600 uppercase">{eyebrow}</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight text-balance text-zinc-950">{title}</h1>
          <div className="mt-4 text-[15px] leading-relaxed text-zinc-500">{intro}</div>
          <nav aria-label="On this page" className="mt-8 hidden lg:block">
            <ul className="space-y-1 border-l border-zinc-200">
              {toc.map(([id, label]) => (
                <li key={id}>
                  <a
                    href={`#${id}`}
                    className="-ml-px block border-l border-transparent py-1 pl-4 text-[13px] text-zinc-500 transition-colors hover:border-zinc-400 hover:text-zinc-900"
                  >
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </aside>
      <div className="animate-fade-in-up space-y-12 lg:col-span-8">{children}</div>
    </main>
  );
}
