import { useEffect, useState } from "react";
import type { ActiveLectureResponse, LectureTotals } from "../shared/types";
import { createLecture, deleteLecture, fetchActiveLecture, fetchLectureTotals } from "../shared/api";
import { activeLectureAction } from "../shared/lectureNav";
import { NavBar } from "../shared/NavBar";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { Badge, Button, Card, ErrorText, Eyebrow, Input, Label, TextLink } from "../shared/ui";

export default function App() {
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);
  const [activeLoading, setActiveLoading] = useState(true);
  const [label, setLabel] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [totals, setTotals] = useState<LectureTotals | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  function loadActive() {
    setActiveLoading(true);
    fetchActiveLecture()
      .then(setActive)
      .catch(() => setActive({ lecture: null, live_question_id: null }))
      .finally(() => setActiveLoading(false));
  }

  useEffect(() => {
    loadActive();
    fetchLectureTotals()
      .then(setTotals)
      .catch(() => {
        // Optional stats line -- fine to just not show it.
      });
  }, []);

  async function handleNewLecture() {
    setStarting(true);
    setStartError(null);
    try {
      await createLecture(label.trim() || null);
      window.location.href = "setup.html";
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Could not start a new lecture.");
      loadActive(); // someone else may have just started one -- pick up "Resume" instead
      setStarting(false);
    }
  }

  // Same logic NavBar's own shortcut uses -- kept in one place
  // (shared/lectureNav.ts) so the two can't drift apart.
  function handleResume() {
    window.location.href = activeLectureAction(active).href;
  }

  // Only ever offered before anything's started (see the JSX below) --
  // once a question's gone live there's real history, and the backend
  // itself refuses the delete at that point anyway (see
  // api_lecturer_delete_lecture in main.py).
  async function confirmDeleteLecture() {
    setConfirmDeleteOpen(false);
    if (!active?.lecture) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteLecture(active.lecture.id);
      loadActive();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Could not delete this lecture.");
    } finally {
      setDeleting(false);
    }
  }

  const hasActive = !activeLoading && active?.lecture != null;

  return (
    <>
      <NavBar />
      <main className="mx-auto grid w-full max-w-6xl gap-10 px-5 pt-14 pb-20 sm:px-8 sm:pt-24 lg:grid-cols-12 lg:gap-16">
        <section className="lg:col-span-5">
          <Eyebrow>Lecturer</Eyebrow>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-balance text-zinc-950 sm:text-5xl">
            Interactive Lecture
          </h1>
          <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-zinc-500">
            Pose a coding question, watch the class work through it live, and bring the interesting
            attempts back to the room.
          </p>
          {/* Past lectures live on their own page now (nav bar "History"). */}
          <div className="mt-10 animate-fade-in-up border-t border-zinc-200 pt-6 [animation-delay:80ms]">
            {totals && (
              <dl className="mb-5 flex gap-10">
                <div>
                  <dt className="text-[13px] text-zinc-500">
                    Lecture{totals.lectures_run === 1 ? "" : "s"} run
                  </dt>
                  <dd className="mt-1 font-mono text-2xl font-semibold text-zinc-950 tabular-nums">
                    {totals.lectures_run}
                  </dd>
                </div>
                <div>
                  <dt className="text-[13px] text-zinc-500">
                    Submission{totals.total_submissions === 1 ? "" : "s"}
                  </dt>
                  <dd className="mt-1 font-mono text-2xl font-semibold text-zinc-950 tabular-nums">
                    {totals.total_submissions}
                  </dd>
                </div>
              </dl>
            )}
            <TextLink href="history.html" className="text-sm">
              Lecture history &rarr;
            </TextLink>
          </div>
        </section>

        <section className="lg:col-span-7 lg:pt-8">
          <Card className="animate-fade-in-up p-6 sm:p-8">
            {activeLoading ? (
              <p className="text-sm text-zinc-500">Loading...</p>
            ) : hasActive ? (
              <>
                <div className="flex items-center justify-between gap-4">
                  <h2 className="text-xl font-bold tracking-tight text-zinc-950">Lecture in progress</h2>
                  {active!.lecture!.lobby_opened_at ? (
                    <Badge tone="success" dot pulse>
                      Open
                    </Badge>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-zinc-500">{active!.lecture!.display_label}</p>
                {active!.lecture!.lobby_opened_at ? (
                  active!.lecture!.join_code && (
                    <div className="mt-6 rounded-lg border border-zinc-200 bg-zinc-50 px-5 py-4">
                      <Eyebrow>Join code</Eyebrow>
                      <div className="mt-1 font-mono text-4xl font-bold tracking-[0.18em] text-zinc-950">
                        {active!.lecture!.join_code}
                      </div>
                      <p className="mt-1 text-[13px] text-zinc-500">
                        Students enter this on the student page to join.
                      </p>
                    </div>
                  )
                ) : (
                  <p className="mt-6 text-sm text-zinc-500">Not open to students yet.</p>
                )}
                <div className="mt-6 flex flex-wrap items-center gap-2">
                  <Button size="lg" onClick={handleResume}>
                    {activeLectureAction(active).label}
                  </Button>
                  {!active!.live_question_id && (
                    <Button
                      size="lg"
                      variant="danger-ghost"
                      onClick={() => setConfirmDeleteOpen(true)}
                      disabled={deleting}
                    >
                      {deleting ? "Deleting..." : "Delete lecture"}
                    </Button>
                  )}
                </div>
                {deleteError && <ErrorText className="mt-3">{deleteError}</ErrorText>}
              </>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleNewLecture();
                }}
              >
                <h2 className="text-xl font-bold tracking-tight text-zinc-950">Start a new lecture</h2>
                <p className="mt-1 text-sm text-zinc-500">You can add questions before opening it to students.</p>
                <div className="mt-6">
                  <Label htmlFor="f-label" hint="optional">
                    Name
                  </Label>
                  <Input
                    type="text"
                    id="f-label"
                    placeholder="e.g. Week 3: Recursion"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                  />
                </div>
                <Button type="submit" size="lg" className="mt-5" disabled={starting}>
                  {starting ? "Starting..." : "New lecture"}
                </Button>
                {startError && <ErrorText className="mt-3">{startError}</ErrorText>}
              </form>
            )}
          </Card>
        </section>
      </main>
      <ConfirmDialog
        open={confirmDeleteOpen}
        title="Delete lecture?"
        message={`Delete "${active?.lecture?.display_label ?? ""}"? This can't be undone.`}
        onConfirm={confirmDeleteLecture}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </>
  );
}
