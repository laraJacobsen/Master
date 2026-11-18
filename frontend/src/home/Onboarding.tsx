import { Card, LinkButton, TextLink } from "../shared/ui";
import { DEMO_DASHBOARD_URL, ROUTES } from "../shared/routes";

const STEPS: { title: string; body: string }[] = [
  {
    title: "Write your tasks",
    body: "Start a lecture, then add coding questions with a few test cases and a reference solution. “Check solution” makes sure the tests pass before students see anything.",
  },
  {
    title: "Open the lobby",
    body: "Students go to the join page on their laptop and type the six-digit code, or open the join link you share. You see them arrive.",
  },
  {
    title: "Watch, then discuss",
    body: "Each task runs on a timer. Submissions are graded as they come in and grouped into discussion points, so you can put the most useful attempts on the projector.",
  },
];

// Shown on the home page until the first lecture has run: what the product
// does, in three steps, and a way to see the live dashboard without a class.
export function Onboarding() {
  return (
    <Card className="animate-fade-in-up p-6 sm:p-8 [animation-delay:120ms]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-zinc-950">Getting started</h2>
          <p className="mt-1 text-sm text-zinc-500">From an empty lecture to a discussion in the room, in three steps.</p>
        </div>
        <TextLink href={ROUTES.help} className="text-sm">
          Read the guide &rarr;
        </TextLink>
      </div>
      <ol className="mt-8 grid gap-8 md:grid-cols-3">
        {STEPS.map((step, i) => (
          <li key={step.title} className="border-t border-zinc-200 pt-5">
            <span className="font-mono text-xs font-semibold text-brand-600 tabular-nums">0{i + 1}</span>
            <h3 className="mt-2 text-[15px] font-semibold tracking-tight text-zinc-950">{step.title}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-zinc-500">{step.body}</p>
          </li>
        ))}
      </ol>
      <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-lg bg-brand-50 px-5 py-4">
        <p className="min-w-0 flex-1 text-[13px] text-brand-900">
          <span className="font-semibold">Want to see it first?</span> Open the live dashboard filled with a sample
          class. Nothing is saved and no students are involved.
        </p>
        <LinkButton href={DEMO_DASHBOARD_URL} variant="secondary" size="sm">
          Preview with sample data
        </LinkButton>
      </div>
    </Card>
  );
}
