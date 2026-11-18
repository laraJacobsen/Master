import { DocPage, ProseSection, PublicLayout } from "../shared/PublicLayout";
import { BRAND } from "../shared/brand";

const TOC: [string, string][] = [
  ["short", "The short version"],
  ["students", "What we store about students"],
  ["browser", "What stays in your browser"],
  ["services", "Other services involved"],
  ["access", "Who can see what"],
  ["lecturers", "Lecturers"],
  ["keeping", "How long it's kept"],
];

// Every statement here describes what the code actually does (backend/store.py
// tables, the browser storage keys in student/App.tsx and student/drafts.ts,
// aggregation.py's language-model call). Change the page when those change.
export default function App() {
  return (
    <PublicLayout current="privacy">
      <DocPage
        eyebrow="Privacy"
        title="Your data"
        intro={`What ${BRAND.name} keeps when you take part in a lecture, who can see it, and why. No accounts, no ads, no tracking.`}
        toc={TOC}
      >
        <ProseSection id="short" title="The short version">
          <ul>
            <li>You join with a name and a code. There's no account, email or password for students.</li>
            <li>We keep the code you submit and its results, so your lecturer can see how the class is doing.</li>
            <li>Code shown to the whole class is shown without your name.</li>
            <li>No analytics, advertising or tracking cookies. Fonts and the code editor load from this server, not third parties.</li>
          </ul>
        </ProseSection>

        <ProseSection id="students" title="What we store about students">
          <ul>
            <li>
              <strong>The name you type</strong> when joining, and when you joined. It doesn't have to be your full
              name. Use what your lecturer asks for.
            </li>
            <li>
              <strong>Each submission</strong>: the code, when it was sent, which tests passed, the result, and the hint
              you were shown.
            </li>
            <li>
              <strong>Whether you're working on the task</strong>: when you opened it, and when you last typed. This lets
              the lecturer see who might be stuck. Only <em>that</em> you typed is recorded, not what. Your code is stored
              when you submit; code you only run is tested and then discarded.
            </li>
          </ul>
        </ProseSection>

        <ProseSection id="browser" title="What stays in your browser">
          <p>A few things are kept in your own browser's storage, not on the server:</p>
          <ul>
            <li>A join token, so you can close the tab and rejoin the same lecture under the same name.</li>
            <li>Unsubmitted drafts of your code, so a reload doesn't lose your work.</li>
            <li>Your name for the current tab, so you don't have to type it again.</li>
          </ul>
          <p>Clearing your browser's site data removes all of them.</p>
        </ProseSection>

        <ProseSection id="services" title="Other services involved">
          <ul>
            <li>
              <strong>Code execution.</strong> To test your code, it's run in an isolated sandbox (Judge0) operated
              together with this server.
            </li>
            <li>
              <strong>Language model.</strong> When several students make the same mistake, short snippets of their code
              are sent to a language model to write a one-line note for the lecturer. Snippets are sent{" "}
              <strong>without names and with comments removed</strong>. Depending on how this server is set up, the model
              runs on NTNU's own infrastructure (IDUN) or on this machine.
            </li>
          </ul>
        </ProseSection>

        <ProseSection id="access" title="Who can see what">
          <ul>
            <li>
              <strong>Your lecturer</strong> can see your name, your submissions and your results. Names are hidden on
              the dashboard by default, so they don't end up on the projector by accident.
            </li>
            <li>
              <strong>Your classmates</strong> only see code the lecturer chooses to show, on the projector or on
              their waiting screen, and always without a name.
            </li>
          </ul>
        </ProseSection>

        <ProseSection id="lecturers" title="Lecturers">
          <p>
            Signing in sets one cookie, which keeps you signed in for up to 12 hours and is used for nothing else. Your
            choice to show or hide student names is remembered in your browser.
          </p>
        </ProseSection>

        <ProseSection id="keeping" title="How long it's kept">
          <p>
            Data from past lectures is kept so the lecturer can look back at them under History. Nothing is deleted
            automatically. If you want your data removed, ask your lecturer, who runs this installation.
          </p>
        </ProseSection>
      </DocPage>
    </PublicLayout>
  );
}
