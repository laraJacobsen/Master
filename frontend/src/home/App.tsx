import { useEffect, useState } from "react";
import type { ActiveLectureResponse, LectureReview, LectureTotals, ProgressResponse, QuestionRow } from "../shared/types";
import {
  createLecture,
  deleteLecture,
  fetchActiveLecture,
  fetchLectureReview,
  fetchLectureTotals,
  fetchProgress,
  fetchQuestionList,
} from "../shared/api";
import { activeLectureAction } from "../shared/lectureNav";
import { NavBar } from "../shared/NavBar";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { Button, Card, ErrorText, Eyebrow, Input, Label, Skeleton, TextLink } from "../shared/ui";
import { Footer } from "../shared/Footer";
import { BRAND } from "../shared/brand";
import { copyWithToast, toast } from "../shared/toast";
import { Onboarding } from "./Onboarding";
import { cx } from "../shared/cx";
import { ReviewRow } from "./ReviewRow";
import { ROUTES, joinLink } from "../shared/routes";

const POLL_MS = 5000;

export interface LiveStatProps {
  label: string;
  value: number;
  /** Shown as "/total" and drives the bar; omitted when unknown. */
  total: number | null;
}

/** One number on the purple card -- "12/20" with a thin bar under it. */
function LiveStat({ label, value, total }: LiveStatProps) {
  const share = total ? Math.min(1, value / total) : null;
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-semibold tracking-[0.08em] text-white/70 uppercase">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold tracking-tight text-white tabular-nums">
        {value}
        {total !== null && <span className="text-white/60">/{total}</span>}
      </div>
      {share !== null && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-sm bg-white/20">
          <div className="h-full rounded-sm bg-white transition-[width] duration-500" style={{ width: `${share * 100}%` }} />
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [active, setActive] = useState<ActiveLectureResponse | null>(null);
  const [activeLoading, setActiveLoading] = useState(true);
  const [label, setLabel] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [totals, setTotals] = useState<LectureTotals | null>(null);
  const [reviews, setReviews] = useState<LectureReview[] | null>(null);
  const [questions, setQuestions] = useState<QuestionRow[] | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
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
    fetchLectureReview()
      .then(setReviews)
      .catch(() => setReviews([])); // the review row just stays hidden
  }, []);

  // Live numbers on the purple card move while students work -- refresh them.
  const lectureId = active?.lecture?.id ?? null;
  const liveId = active?.live_question_id ?? null;
  useEffect(() => {
    if (lectureId === null) return;
    let cancelled = false;
    function refresh() {
      fetchQuestionList()
        .then((q) => !cancelled && setQuestions(q))
        .catch(() => {});
      if (liveId) {
        fetchProgress(liveId)
          .then((p) => !cancelled && setProgress(p))
          .catch(() => {});
      }
    }
    refresh();
    const t = window.setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [lectureId, liveId]);

  async function handleNewLecture() {
    setStarting(true);
    setStartError(null);
    try {
      await createLecture(label.trim() || null);
      window.location.href = ROUTES.setup;
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
      toast("Lecture deleted");
      loadActive();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Could not delete this lecture.");
    } finally {
      setDeleting(false);
    }
  }

  const hasActive = !activeLoading && active?.lecture != null;
  const tasksDone = questions?.filter((q) => q.status === "closed" || q.status === "skipped").length ?? 0;

  return (
    <>
      <NavBar />
      <main className="mx-auto grid w-full max-w-6xl gap-10 px-5 pt-14 pb-20 sm:px-8 sm:pt-24 lg:grid-cols-12 lg:gap-16">
        <section className="lg:col-span-5">
          <Eyebrow>Lecturer</Eyebrow>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-balance text-zinc-950 sm:text-5xl">
            {BRAND.name}
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
            <TextLink href={ROUTES.history} className="text-sm">
              Lecture history &rarr;
            </TextLink>
          </div>
        </section>

        <section className="lg:col-span-7 lg:pt-8">
          <Card
            className={cx(
              "animate-fade-in-up p-6 sm:p-8",
              // Brand-purple gradient panel, both for the lecture that's on right now and for
              // starting a new one, so the primary action always sits in the same place/look.
              !activeLoading &&
                "relative isolate overflow-hidden bg-linear-to-br from-brand-500 via-brand-500 to-violet-500 text-white shadow-xl shadow-brand-500/25",
            )}
          >
            {!activeLoading && (
              // Soft light from the top right -- depth without decoration.
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(32rem_16rem_at_100%_0%,rgb(255_255_255/0.22),transparent_70%)]"
              />
            )}
            {activeLoading ? (
              <div role="status" aria-label="Loading">
                <Skeleton className="h-6 w-48" />
                <Skeleton className="mt-3 h-4 w-64" />
                <Skeleton className="mt-6 h-24 w-full rounded-lg" />
                <Skeleton className="mt-6 h-11 w-36 rounded-lg" />
              </div>
            ) : hasActive ? (
              <>
                <div className="flex items-center justify-between gap-4">
                  <h2 className="text-xl font-bold tracking-tight text-white">Lecture in progress</h2>
                  {active!.lecture!.lobby_opened_at ? (
                    <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-white">
                      <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-white" aria-hidden="true" />
                      Open
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-white/80">{active!.lecture!.display_label}</p>
                {active!.lecture!.lobby_opened_at ? (
                  active!.lecture!.join_code && (
                    <div className="mt-6 rounded-lg border border-white/20 bg-white/10 px-5 py-4">
                      <Eyebrow className="text-white/70">Join code</Eyebrow>
                      <div className="mt-1 font-mono text-4xl font-bold tracking-[0.18em] text-white">
                        {active!.lecture!.join_code}
                      </div>
                      <p className="mt-1 text-[13px] text-white/75">
                        Students enter this at {window.location.host}
                        {ROUTES.join} to join.
                      </p>
                      <button
                        type="button"
                        onClick={() => void copyWithToast(joinLink(active!.lecture!.join_code!), "Join link")}
                        className="mt-3 rounded-md text-[13px] font-semibold text-white underline decoration-white/40 underline-offset-4 transition-colors hover:decoration-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                      >
                        Copy join link
                      </button>
                    </div>
                  )
                ) : (
                  <p className="mt-6 text-sm text-white/80">Not open to students yet.</p>
                )}
                {questions && questions.length > 0 && (
                  <div className="mt-6 grid grid-cols-2 gap-6">
                    <LiveStat label="Tasks completed" value={tasksDone} total={questions.length} />
                    {liveId && progress && (
                      <LiveStat label="Submitted, current task" value={progress.submitted} total={progress.expected} />
                    )}
                  </div>
                )}
                <div className="mt-6 flex flex-wrap items-center gap-2">
                  <Button
                    size="lg"
                    onClick={handleResume}
                    className="bg-white text-brand-700 shadow-brand-900/20 hover:bg-brand-50 active:bg-brand-100 focus-visible:outline-white"
                  >
                    {activeLectureAction(active).label}
                  </Button>
                  {!active!.live_question_id && (
                    <Button
                      size="lg"
                      variant="danger-ghost"
                      className="text-white/80 hover:bg-white/10 hover:text-white disabled:text-white/50 focus-visible:outline-white"
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
                <h2 className="text-xl font-bold tracking-tight text-white">Start a new lecture</h2>
                <p className="mt-1 text-sm text-white/80">You can add questions before opening it to students.</p>
                <div className="mt-6 rounded-lg border border-white/20 bg-white/10 px-5 py-4">
                  <Label htmlFor="f-label" hint="optional" className="text-white [&>span]:text-white/70">
                    Name
                  </Label>
                  <Input
                    type="text"
                    id="f-label"
                    placeholder="e.g. Week 3: Recursion"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    className="border-white/30 hover:border-white/50 focus:border-white focus:ring-white/30"
                  />
                </div>
                <div className="mt-6 flex flex-wrap items-center gap-2">
                  <Button
                    type="submit"
                    size="lg"
                    disabled={starting}
                    className="bg-white text-brand-700 shadow-brand-900/20 hover:bg-brand-50 active:bg-brand-100 focus-visible:outline-white"
                  >
                    {starting ? "Starting..." : "New lecture"}
                  </Button>
                </div>
                {startError && <ErrorText className="mt-3 text-white">{startError}</ErrorText>}
              </form>
            )}
          </Card>
        </section>

        {/* Until the first lecture has been finished, show how it works. (Not
            "no lectures run": a fresh database already has the seeded sample
            lecture in progress -- see store.init_db.) */}
        {reviews !== null && reviews.length === 0 && (
          <section className="lg:col-span-12" aria-label="Getting started">
            <Onboarding />
          </section>
        )}

        <section className="lg:col-span-12" aria-label="Recent lectures">
          <ReviewRow reviews={reviews} activeLectureId={lectureId} />
        </section>
      </main>
      <Footer />
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
