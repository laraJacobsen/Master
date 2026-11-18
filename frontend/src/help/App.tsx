import { DocPage, ProseSection, PublicLayout } from "../shared/PublicLayout";
import { Kbd } from "../shared/shortcuts";
import { BRAND } from "../shared/brand";
import { DEMO_DASHBOARD_URL, ROUTES } from "../shared/routes";

const TOC: [string, string][] = [
  ["students", "For students"],
  ["lecturers", "For lecturers"],
  ["shortcuts", "Keyboard shortcuts"],
  ["faq", "Questions"],
  ["trouble", "Something's not working"],
];

interface ShortcutTableProps {
  caption: string;
  rows: [string[], string][];
}

function ShortcutTable({ caption, rows }: ShortcutTableProps) {
  return (
    <div>
      <h3 className="text-[13px] font-semibold text-zinc-900">{caption}</h3>
      <dl className="mt-2 divide-y divide-zinc-100 rounded-xl bg-white px-4 shadow-card">
        {rows.map(([keys, label]) => (
          <div key={label} className="flex items-center justify-between gap-6 py-2.5">
            <dt className="text-sm text-zinc-700">{label}</dt>
            <dd className="flex flex-none gap-1">
              {keys.map((k) => (
                <Kbd key={k}>{k}</Kbd>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Link({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} className="font-medium text-brand-600 underline-offset-4 hover:underline">
      {children}
    </a>
  );
}

export default function App() {
  return (
    <PublicLayout current="help">
      <DocPage
        eyebrow="Help"
        title={`How ${BRAND.name} works`}
        intro="Short coding tasks during a lecture: everyone writes code at the same time, gets feedback straight away, and the lecturer brings the most useful attempts back to the room."
        toc={TOC}
      >
        <ProseSection id="students" title="For students">
          <ol>
            <li>
              Open <Link href={ROUTES.join}>the join page</Link> (or the link your lecturer shared), enter your name and
              the six-digit code shown in the room.
            </li>
            <li>Wait for the first task. It opens on its own when the lecturer starts it, with a timer at the top.</li>
            <li>
              Write your solution in the editor. <strong>Run</strong> tries it on the example input and isn't graded,
              so use it as much as you like. <strong>Submit</strong> checks it against the task's tests.
            </li>
            <li>
              A wrong answer comes back with a hint. Submit again and the hints get more specific. When time runs out,
              the code in your editor is submitted for you.
            </li>
            <li>At the end of the lecture you get a recap of how each task went.</li>
          </ol>
          <p>
            Your lecturer may put some attempts on the projector to talk about them. Code shown to the class is shown{" "}
            <strong>without your name</strong>.
          </p>
        </ProseSection>

        <ProseSection id="lecturers" title="For lecturers">
          <ol>
            <li>
              <strong>Start a lecture</strong> from the home page and give it a name, for example “Week 3: Recursion”.
            </li>
            <li>
              <strong>Add tasks.</strong> Each needs a description, at least two test cases (the first is the example
              students see and isn't graded) and a reference solution. <strong>Check solution</strong> runs your
              solution against the tests, and a task can only start once it passes.
            </li>
            <li>
              <strong>Open the lobby.</strong> You get a join code to show on the projector, and you can watch students
              arrive.
            </li>
            <li>
              <strong>Start the lecture.</strong> The live dashboard shows who has submitted, how each student is doing,
              and discussion points: groups of students who made the same mistake, with a short note on what went
              wrong.
            </li>
            <li>
              <strong>Bring it back to the room.</strong> Add attempts or discussion points to the screen queue and open
              the projector view. When time is up, step through them with the class. Then go to the next task.
            </li>
            <li>
              <strong>End the lecture</strong> when you're done. The summary stays under History.
            </li>
          </ol>
          <p>
            Want to see the dashboard first? <Link href={DEMO_DASHBOARD_URL}>Preview it with sample data</Link>. Nothing
            is saved.
          </p>
        </ProseSection>

        <ProseSection id="shortcuts" title="Keyboard shortcuts">
          <div className="grid gap-6">
            <ShortcutTable
              caption="Live dashboard"
              rows={[
                [["N"], "Show or hide student names"],
                [["P"], "Open the projector view"],
                [["←", "→"], "Previous / next student while their code is open"],
                [["Alt", "←", "→"], "Move the focused screen-queue item"],
                [["?"], "List these shortcuts"],
              ]}
            />
            <ShortcutTable
              caption="Projector view"
              rows={[
                [["→"], "Next item (clicker: Page Down)"],
                [["←"], "Previous item (clicker: Page Up)"],
                [["Esc"], "Close the task popup"],
              ]}
            />
            <ShortcutTable caption="Student editor" rows={[[["Ctrl", "↵"], "Run your code (⌘ ↵ on a Mac)"]]} />
          </div>
        </ProseSection>

        <ProseSection id="faq" title="Questions">
          <p>
            <strong>Do I need an account?</strong>
            <br />
            No. You join with your name and the lecture's code, nothing else.
          </p>
          <p>
            <strong>Can other students see my code?</strong>
            <br />
            Only if the lecturer puts it on the projector, and then without your name.
          </p>
          <p>
            <strong>Which languages are supported?</strong>
            <br />
            Python, C and Java. Each task is set to one of them.
          </p>
          <p>
            <strong>What do you store about me?</strong>
            <br />
            See the <Link href={ROUTES.privacy}>privacy page</Link>.
          </p>
        </ProseSection>

        <ProseSection id="trouble" title="Something's not working">
          <ul>
            <li>
              <strong>“That code didn't match”</strong>: check the six digits on the projector. The code changes for
              every lecture.
            </li>
            <li>
              <strong>“Connection lost” at the top of the screen</strong>: your wifi dropped or the server is restarting.
              Leave the page open. It reconnects on its own, and your code stays in the editor.
            </li>
            <li>
              <strong>Closed the tab by accident?</strong> Open the join page again in the same browser and join with
              the same name and code. You'll pick up where you left off.
            </li>
          </ul>
          <p>Anything else: ask your lecturer in the room.</p>
        </ProseSection>
      </DocPage>
    </PublicLayout>
  );
}
