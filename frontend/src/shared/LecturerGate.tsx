import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchLecturerSession, lecturerLogin, LECTURER_AUTH_EXPIRED_EVENT } from "./api";
import { Button, Callout, Card, Eyebrow, Input, Label, Spinner } from "./ui";
import { rememberRole } from "./role";

// Every lecturer page (home, setup, live dashboard, history, projector) sits
// behind this when the server has a LECTURER_PASSWORD (backend/auth.py).
// Not logged in on arrival: a login screen instead of the page. Session runs
// out mid-lecture (a lecturer call comes back 401): the same form as a dialog
// over the page, which stays mounted underneath, so a half-written question
// or the live dashboard's state survives the login.

type GateState = "checking" | "login" | "open";

export interface LecturerGateProps {
  children: ReactNode;
}

export function LecturerGate({ children }: LecturerGateProps) {
  const [state, setState] = useState<GateState>("checking");
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    fetchLecturerSession()
      .then((s) => setState(!s.auth_required || s.logged_in ? "open" : "login"))
      // Can't tell -- let the page load; its own calls will 401 into the dialog if needed.
      .catch(() => setState("open"));
  }, []);

  useEffect(() => {
    const onExpired = () => setExpired(true);
    window.addEventListener(LECTURER_AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(LECTURER_AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  useEffect(() => {
    if (state === "open") rememberRole("lecturer");
  }, [state]);

  if (state === "checking") return null;

  if (state === "login") {
    return (
      <main className="mx-auto grid min-h-screen max-w-5xl gap-10 px-6 pt-14 sm:pt-24 lg:grid-cols-12 lg:gap-16">
        <section className="animate-fade-in-up lg:col-span-5">
          <Eyebrow>Lecturer</Eyebrow>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-balance text-zinc-950 sm:text-5xl">Log in</h1>
          <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-zinc-500">
            Lecture setup, live results and students' code are for the lecturer only.
          </p>
        </section>
        <section className="lg:col-span-7 lg:pt-8">
          <Card className="animate-fade-in-up p-6 sm:p-8">
            <LoginForm
              onLoggedIn={() => {
                setExpired(false);
                setState("open");
              }}
            />
          </Card>
        </section>
      </main>
    );
  }

  return (
    <>
      {children}
      {expired && (
        <div className="fixed inset-0 z-[100] flex animate-fade-in items-center justify-center bg-zinc-950/40 p-4 backdrop-blur-[2px]">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="lecturer-login-title"
            className="w-full max-w-sm animate-fade-in-up rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl shadow-zinc-950/10"
          >
            <h2 id="lecturer-login-title" className="text-lg font-bold tracking-tight text-zinc-950">
              Log in again
            </h2>
            <p className="mt-1.5 mb-5 text-sm text-zinc-500">
              Your lecturer session has ended. The page stays as it is; retry what you were doing once you're back in.
            </p>
            <LoginForm onLoggedIn={() => setExpired(false)} />
          </div>
        </div>
      )}
    </>
  );
}

interface LoginFormProps {
  onLoggedIn: () => void;
}

function LoginForm({ onLoggedIn }: LoginFormProps) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!password) {
      setError("Enter the lecturer password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await lecturerLogin(password);
      setPassword("");
      onLoggedIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't log in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <Label htmlFor="lecturer-password">Lecturer password</Label>
      <Input
        type="password"
        id="lecturer-password"
        autoComplete="current-password"
        autoFocus
        className="h-11 text-[15px]"
        aria-invalid={error ? true : undefined}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" size="lg" className="mt-6 w-full" disabled={busy}>
        {busy && <Spinner />}
        {busy ? "Logging in..." : "Log in"}
      </Button>
      {error && (
        <Callout tone="danger" role="alert" className="mt-4">
          {error}
        </Callout>
      )}
    </form>
  );
}
