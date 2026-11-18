import { PublicLayout } from "../shared/PublicLayout";
import { LinkButton } from "../shared/ui";
import { ROUTES } from "../shared/routes";

// Served by the backend (and Vite) for any path that isn't a page or an API
// route, with a 404 status.
export default function App() {
  return (
    <PublicLayout>
      <main className="mx-auto grid max-w-6xl gap-10 px-5 pt-20 pb-24 sm:px-8 sm:pt-28 lg:grid-cols-12 lg:gap-16">
        <section className="animate-fade-in-up lg:col-span-6">
          <p className="font-mono text-sm font-semibold text-brand-600 tabular-nums">404</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight text-balance text-zinc-950 sm:text-5xl">
            This page doesn't exist.
          </h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-zinc-500">
            The link may be old or mistyped. If you're here for a lecture, go to the join page and enter the code
            shown in the room.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            <LinkButton href={ROUTES.join} size="lg">
              Join a lecture
            </LinkButton>
            <LinkButton href={ROUTES.home} variant="secondary" size="lg">
              Lecturer home
            </LinkButton>
          </div>
        </section>
        <section className="hidden lg:col-span-6 lg:block" aria-hidden="true">
          <pre className="animate-fade-in-up rounded-xl bg-zinc-900 p-6 font-mono text-[13px] leading-relaxed text-zinc-300 shadow-xl shadow-zinc-950/10 [animation-delay:80ms]">
            <span className="text-zinc-500">{">>> "}</span>
            <span className="text-white">open(</span>
            <span className="text-emerald-300">{`"${window.location.pathname}"`}</span>
            <span className="text-white">)</span>
            {"\n"}
            <span className="text-zinc-500">Traceback (most recent call last):</span>
            {"\n  ...\n"}
            <span className="text-red-300">FileNotFoundError</span>
            {": no such page\n"}
          </pre>
        </section>
      </main>
    </PublicLayout>
  );
}
