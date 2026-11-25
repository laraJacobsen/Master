"""
Cheap aggregation over stored submissions: group by (exec_verdict, error_type) -- the
deterministic Judge0-derived taxonomy from backend/hints.py -- and rank clusters by how
many distinct students hit each one. This is the groupby fallback from the
aggregation-pipeline sketch: cheap enough to run live during a lecture, not a semantic
clustering/embedding pipeline.

Discussion points are attached here, one per cluster, generated on first use and cached
in-memory for the rest of the process -- not one per submission. A single student
resubmitting the same broken code repeatedly must not inflate a cluster's count or spawn
a fresh discussion point on every attempt: count is distinct students, and a cluster only
gets a discussion point once at least MIN_STUDENTS_FOR_DISCUSSION distinct students are
actually stuck on it -- one student's idiosyncratic mistake isn't a whole-class talking
point. For most categories (syntax_error, a specific exception name, timeout, ...) that
grouping is already homogeneous enough that a single curated line covers it -- see
feedback-research/feedback.py's discussion_point_for().

wrong_answer is the exception: "ran fine, wrong output" covers arbitrarily different bugs
on the same exercise, so treating it as one bucket produces a discussion point too generic
to act on. That bucket gets sub-clustered by actual code similarity instead:

  1. _canonicalize() renames every non-keyword identifier to VAR1/VAR2/... in order of
     first appearance (via the stdlib `tokenize` module), so two students' differently
     named variables/functions don't make structurally-identical code look different.
  2. _cluster_by_similarity() TF-IDFs the canonicalized text (plain TfidfVectorizer, no
     embedding model -- this is an MVP) and runs AgglomerativeClustering with no fixed k
     (distance_threshold instead of n_clusters), so genuinely different bugs fall out as
     their own group -- including singletons -- rather than being forced into a fixed
     number of buckets.
  3. Sub-clusters that clear MIN_STUDENTS_FOR_DISCUSSION get a live LLM call (IDUN's
     OpenAI-compatible gateway -- see https://www.hpc.ntnu.no/idun/documentation/
     ai-coding-assistant-and-large-language-models-llms-on-idun/ -- rather than local
     Ollama, so this doesn't sit on the laptop-latency/memory ceiling measured in
     pedagogical-feedback-design-decision.md), but a narrowly scoped one: given 2-3
     representative snippets (comments stripped, never student names -- canonicalized
     VARn form until 2026-10-13, see the entry at the end) from that one sub-cluster, 
     and explicitly told to describe only the pattern
     visible in ALL of them, never invent a cause true of less than all. This is a
     different risk shape than the lecturer discussion-point call this project removed
     twice before (see pedagogical-feedback-design-decision.md) -- that one asked a model
     to explain a cause from a bare label with no evidence, which is exactly what it
     couldn't do reliably. Here the model is shown real (anonymized) evidence and asked
     to describe only what's shared across it, with a hard fallback to the generic
     wrong_answer line if it fails or won't hold the audience distinction either.

This is genuinely unvalidated: the distance threshold below is a first guess, not tuned
against labeled data, and no human has reviewed real generated output yet. Per
pedagogical-feedback-design-decision.md's own methodology, real sub-cluster output from
this pipeline is the trigger for the human/expert spot-check pass already committed to
there -- this should not go near a live lecture before that happens.

2026-09-16 finding, first real-corpus run (feedback-research/corpora/corpus.py's and
corpus_count_vowels.py's actual wrong_answer cases): WRONG_ANSWER_SUBCLUSTER_DISTANCE=0.4
is too permissive for realistic short exercise solutions and merged every distinct bug
into one group on both exercises tested. Measured pairwise cosine distances between the
real (genuinely different) bugs: 0.000-0.326 for is_palindrome, 0.090-0.158 for
count_vowels -- both entirely under the 0.4 threshold. Cause: canonicalized short-exercise
code is dominated by shared boilerplate (the function signature, the input()/print() shell
around it), so the one buggy line is a small fraction of the vector even when it's a
structurally different kind of bug (e.g. a missing .lower() vs. a rewritten off-by-one
loop). Separately, the TF-IDF step's default tokenizer drops single-character tokens
entirely, so bugs differing only by an operator (+1 vs -1) or a short string-literal
argument are already indistinguishable to it before threshold tuning even enters into it.
Also observed in that same run: even when shown real (anonymized) evidence and explicitly
told to describe only a pattern true of every snippet, the model still asserted a specific
claim ("all snippets have the same off-by-one indexing pattern") that was only actually
true of one of the four merged snippets -- the same failure category the human/expert
review step exists to catch, recurring despite the tighter grounding here. Whoever tunes
the threshold next should start well below 0.326, probably per-exercise rather than one
global constant, and should not assume evidence-grounding alone fixed the over-generalization
risk.

2026-09-16, follow-up after the finding above: two problems fixed, one new one found and
mitigated, still unvalidated overall.

- Root cause of the over-permissive merging: TfidfVectorizer's default token_pattern
  (\\b\\w\\w+\\b) drops every operator, bracket, and single-digit literal -- exactly the
  tokens a short exercise's bug usually lives in. Checked against 4 deliberately-distinct
  sum-ints bugs (wrong operator, an off-by-one slice, wrong index, a stray +1): under the
  default pattern their vectors were close enough to fully merge regardless of threshold.
  Switching to token_pattern=r"\\S+" (keep every canonicalized token -- _canonicalize()
  already space-joins them) separated the same 4 bugs to pairwise cosine distances of
  0.098-0.240, while two submissions of genuinely identical code stayed at 0.000 -- an
  actual gap to threshold on. The token pattern was the real blind spot; the threshold
  alone was never going to fix this.
- WRONG_ANSWER_SUBCLUSTER_DISTANCE retuned from 0.4 to 0.05, and linkage from "average" to
  "complete". 0.15 with "average" linkage (the first retune) still chained 3 of the 4
  distinct bugs into one cluster: average linkage merges based on the mean distance across
  a growing cluster, so two points that are each individually close to a third (here, two
  distinct bugs both moderately close to the identical-code pair) get pulled together even
  though their own direct distance is the largest in the group. "complete" linkage merges
  on the *maximum* pairwise distance instead, which doesn't chain that way, and separated
  all 3 distinct bugs into their own clusters at threshold 0.05-0.09 while still correctly
  merging the one genuinely-identical-code pair (distance 0.000). Chose the safer end of
  that range (0.05): a false split just shows one bug as two rows, each still individually
  correct; a false merge produces an actively wrong claim to a lecturer, so under
  uncertainty this errs toward splitting. Still one (question, sample) data point, not
  tuned against labeled data -- treat as a better first guess, not a validated constant,
  and prefer per-exercise tuning eventually.
- New failure mode, worse than over-generalization: given a degenerate real submission
  (two students' actual "int" typed into the textarea, unrelated to any real exercise
  attempt -- canonicalizes to the single token VAR1), the model fabricated a detailed,
  entirely fictitious pattern ("all snippets show an identical addition of 1 to the result
  of VAR2*VAR2") with no VAR2, no multiplication, and no addition anywhere in the actual
  input -- a direct violation of its own "say so if there's no pattern" instruction.
  Mitigated with _MIN_TOKENS_FOR_PATTERN_CALL: below that many canonicalized tokens, skip
  the model call entirely and use the generic fallback line, rather than trust the model to
  self-police on degenerate input. This guards the specific case observed; it is not a
  general fix for the model asserting ungrounded claims on richer input, which the
  over-generalization finding above shows can still happen even with real evidence shown.

None of this replaces the human/expert checkpoint -- it removes two concrete, reproduced
failure modes, not the general risk the checkpoint exists to catch.

2026-09-21, signal swap based on labeled ground truth (see feedback-research/
clustering-eval/subcluster_ground_truth_sample.csv -- 29 real wrong_answer submissions across 3
exercises, hand-labeled into bug groups -- and feedback-research/clustering-eval/run_tfidf_baseline.py/
run_diff_baseline.py, which score any clustering against it with adjusted Rand index +
pairwise precision/recall). Per the module docstring above, WRONG_ANSWER_SUBCLUSTER_DISTANCE
was always a first guess, not tuned against labeled data -- this is the first real score:
at the threshold above (0.05), raw-canonicalized-code TF-IDF scored mean ARI 0.579, and
is_palindrome specifically scored 0.000 (two genuinely different bugs -- missing .lower(),
missing space-stripping -- still merged into one cluster, in production, today).

Root cause isn't the threshold: TF-IDF over raw canonicalized code is measuring code
*shape*, but the ground truth is grouped by code *behavior* (what's actually wrong), and a
short exercise's shared boilerplate (the function signature, the input()/print() shell)
dominates the vector regardless of threshold -- this is the same boilerplate-dominance
problem the 2026-09-16 finding above already diagnosed, just not fully solved by retuning
alone. Swapped the input representation instead: each submission is now represented by its
diff against the exercise's own reference_solution (both sides canonicalized first, same
_canonicalize() as before, so identifier naming still doesn't matter), rather than by its
own raw canonicalized code. Boilerplate shared with the reference solution -- which is most
of a short exercise -- now contributes exactly zero signal, by construction, instead of
merely being down-weighted by TF-IDF's document-frequency term.

Rescored against the same ground truth at the same threshold (0.05): mean ARI 0.579 -> 0.899,
is_palindrome 0.000 -> 1.000, with no regression on the other two exercises. This was a
one-variable change -- WRONG_ANSWER_SUBCLUSTER_DISTANCE, linkage, and token_pattern are all
unchanged from the 2026-09-16 retune, only _cluster_by_similarity()'s input representation
differs. See feedback-research/clustering-eval/run_diff_baseline.py for the full threshold-sweep results this
was chosen from (diff-against-reference stays well above the TF-IDF baseline across
0.02-0.30, not just at 0.05).

This does NOT close every gap: feedback-research/decisions/double-it-shape-vs-behavior-limitation-2026-09-21.md
documents a case (three structurally different one-line edits that all diverge from the
reference *differently* but happen to print identical output) that no code-similarity or
code-diff signal can group correctly -- doing so would require an output/behavior-based
signal (actually running submissions against sample inputs) instead. Treated as a documented
methodological limitation, not an open bug to chase with this signal.

Discussion-point generation (_subcluster_discussion_point() / the IDUN call below) is
UNCHANGED by this: it still shows the LLM raw canonicalized code snippets, not diff tokens --
that step's own known issues (see the fabrication/over-generalization findings above) are
tracked separately and weren't touched here.

2026-10-13, Label call shown real code instead of canonicalized code. Round 3 of the real
discussion-point spot-check (feedback-research/label-spot-checks/real_discussion_point_sample_2026-09-21_round3.csv)
rated all 16 rows lecturer-facing, but 9 only partially grounded -- every one of them because
_canonicalize() renames builtins and methods along with the students' own names, so the model
could only describe a missing .replace(" ", "") as "the subsequent method call that takes the
two string literals". The Label call now gets each snippet and the reference solution as written
by the student, minus comments (_strip_comments()). Clustering is untouched: it still diffs
canonicalized code, which is where name-independence actually matters. The VARn/STMT_BREAK leak
backstop added in round 3 was removed along with the placeholders it guarded against.

2026-10-15, output-signature level added in front of the diff signal. Closes the case in
feedback-research/decisions/double-it-shape-vs-behavior-limitation-2026-09-21.md: DI-01/02/05/07 print the
same wrong output (33, 1010) through three different code edits, so the diff signal kept them in
3 groups. Every graded submission already stores its per-test stdout (raw_test_results), so a
behavioral signal costs no extra execution.

- _output_signature(): one entry per test case, in order -- "PASS", or the stdout with whitespace
  stripped and collapsed. None (missing/unparseable/empty raw_test_results) falls through to the
  diff signal unchanged.
- _group_wrong_answers(): level 1 groups by signature; level 2 runs the unchanged
  _cluster_by_similarity() inside a signature group only when the signature is weak (fewer than
  MIN_TESTS_FOR_FINAL_SIGNATURE = 2 test cases). WRONG_ANSWER_SUBCLUSTER_DISTANCE, linkage and the
  token pattern are unchanged.
- Tried and reverted the same day: also showing the Label call one failing test the whole group
  failed the same way (_shared_failing_case()), with a prompt paragraph asking for the shared
  wrong behavior when snippets differ in shape. See "Label call: round 5" below.

Measured with feedback-research/clustering-eval/run_signature_baseline.py against the same 29-submission ground
truth and subcluster_eval.py, at the production threshold (0.05), each submission run against its
own question's real stored test cases:

    variant                   sum-ints        double-it       is_palindrome   mean ARI
    (a) diff only (old)       0.897 (5/6)     0.798 (5/3)     1.000 (3/3)     0.899
    (b) signature only        1.000 (6/6)     1.000 (3/3)     0.000 (1/3)     0.667
    (c) signature then diff   1.000 (6/6)     1.000 (3/3)     1.000 (3/3)     1.000

Mean pairwise precision/recall: (a) 0.947/0.921, (b) 0.667/1.000, (c) 1.000/1.000. (b) shows why
the weak-signature fallback exists: is_palindrome has a single test input in the repo, all three
of its bugs print False on it, and signature-only merges them. Under (c) that exercise is decided
entirely by the diff signal -- the signature adds nothing there.

Not solved, and worth saying plainly:
- The perfect score is on 29 submissions whose labels were made with the help of
  subcluster_ground_truth_io_table.md, an output table. An output-based signal agreeing with
  output-assisted labels is partly circular; this shows the signal does what it should on the
  cases it targets, not that it's validated.
- Two unrelated bugs that happen to print the same thing on every test case now merge, and the
  diff signal never gets a say on a final signature. Fewer test cases means more of this; 2 is
  the minimum before a signature is trusted alone.
- Questions with one test case get no benefit (weak signature -> diff, as before).
- Output that isn't deterministic (random numbers, set/dict ordering, timestamps) splits
  identical bugs into separate signatures.

Label call: round 5 (feedback-research/label-spot-checks/real_discussion_point_sample_2026-09-21_round5.csv), same
data as round 4 plus the shared failing test. Pass rule fixed before rating: no row less grounded
or actionable than its round-4 counterpart, the double-it prints-twice row describes the shared
behavior, no fabrications. Result: sum-ints and double-it all y/y/y, including the two new groups
(drop-last on its own; the prints-twice row, grounded and using the test correctly). No
fabrications. But 4 of 14 rows matched to round 4 got worse, all in the single-test corpus
exercises: is_palindrome off-by-one and second_largest x3 lost the bug's meaning ("differs from
the correct indexing" instead of round 4's "an off-by-one index"; "instead of sorting a set" with
no mention that duplicates make it pick the second position, not the second distinct value --
which the shown test, 9 9 -> printed 9, actually demonstrated). None of the four labels used the
test. Rule failed, so the Label part was reverted; the clustering change stays (evaluated
separately above). Not established: whether the test caused the drift or it's run-to-run model
variation -- each round is one sample per row. A control (same groups, test off, plus a repeat
of each) would tell, and the round's groups were mostly identical code, so the case the test was
for (different code, same output) was exercised by one row only.

Signature grouping time is logged per question ("wrong_answer signature: ..."), next to the
existing diff+cluster line, which now reports how many submissions still needed the diff step.

2026-10-23: provider switch. LLM_PROVIDER=idun (default) or ollama picks where the Label call
goes -- see _resolve_llm_config(). Both speak the same OpenAI-compatible chat-completions API,
so the prompt and validation are identical; only endpoint/model/auth/timeout differ. Ollama is
for running off NTNU's network/VPN, or keeping student code on the machine. Not re-evaluated:
every spot-check round so far used IDUN's gpt-oss-120b, and a small local model is expected
to do worse (more fallbacks from invalid JSON or second-person phrasing, vaguer labels).

2026-11-16, Label wording: one sentence about the code itself -- no "snippets", "reference
solution", or "both"/"all" for the group. Labels were already grounded, but read as code diffs
("Both snippets use a single %d ..., whereas the reference solution uses two"). A "headline:
sentence" format was tried the same day and dropped: the dashboard's separate headline call
(HEADLINE_PROMPT) already writes the title from this note, so the note repeated it. Grounding
rules unchanged. Not yet through a spot-check round.
"""

import difflib
import io
import json
import keyword
import logging
import os
import re
import threading
import time
import tokenize
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

import requests
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.rate_limit import take_llm_call
from backend import hints, store, task_import

# Nothing else in this project configures logging -- without this, the per-stage
# latency numbers below (the actual research question: is this fast enough to run
# live in a lecture) would silently go nowhere.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_STUDENTS_FOR_DISCUSSION = 2

# Issues the lecturer chose to show to the students on the live dashboard -- see
# raise_issue(). A raised issue gets a discussion point even below
# MIN_STUDENTS_FOR_DISCUSSION, sorts to the top, and its example is sent to the
# students' waiting screen (shown_examples()). Each is stored as (question_id,
# exec_verdict, error_type, student names in the issue when it was raised), so
# an issue stays raised as more students land in it, plus the submission id
# shown to students, in the order raised. Kept in SQLite (store.raised_issue_rows())
# rather than in memory: a backend restart -- every `uvicorn --reload` -- used to
# take the examples off the students' screens mid-lecture.

# Keeps operators/brackets/literals as features instead of dropping them -- see
# the 2026-09-16 follow-up in the module docstring.
_TOKEN_PATTERN = r"\S+"

# Retuned 2026-09-16 -- see module docstring for the measured distance gap this
# sits in. Still an unvalidated first guess, not a tuned constant.
WRONG_ANSWER_SUBCLUSTER_DISTANCE = 0.05

# An output signature (see _output_signature()) built from fewer test cases than
# this is "weak": with a single test, two unrelated bugs that both just print the
# wrong thing for that one input -- e.g. False for a non-palindrome check -- would
# share a signature by coincidence. A weak signature group is therefore split
# further by the diff signal; a signature from at least this many tests is final.
# The signature has one entry per stored test case, so this is the same as "the
# question has fewer than 2 test cases". Not tuned: 2 is the smallest count where
# two different bugs have to agree on more than one input to merge.
MIN_TESTS_FOR_FINAL_SIGNATURE = 2

# Below this many canonicalized tokens there's nothing real to describe a pattern
# from -- see the 2026-09-16 fabrication finding in the module docstring.
_MIN_TOKENS_FOR_PATTERN_CALL = 4

# Per-sub-cluster Label (IDUN) calls are independent of each other -- see
# _generate_subcluster_labels() -- so they're run concurrently rather than one at a
# time. Capped rather than unbounded so a lecture with many simultaneous sub-clusters
# doesn't fire an unbounded burst of requests at the gateway at once.
_MAX_PARALLEL_LABEL_CALLS = 8

# IDUN's OpenAI-compatible LLM gateway (NTNU network/VPN required) -- see
# https://www.hpc.ntnu.no/idun/documentation/ai-coding-assistant-and-large-language-models-llms-on-idun/.
# Replaces the local-Ollama call this project started with: same evidence-grounded,
# narrowly-scoped prompt (see the module docstring), just off the laptop-latency/
# memory ceiling that motivated moving it off local Ollama in the first place.
IDUN_BASE_URL = os.environ.get("IDUN_BASE_URL", "https://llm.hpc.ntnu.no/v1")
IDUN_API_KEY = os.environ.get("IDUN_API_KEY")
IDUN_MODEL = os.environ.get("IDUN_MODEL", "openai/gpt-oss-120b")

# Local Ollama, as the alternative to IDUN (LLM_PROVIDER=ollama): off NTNU's network/VPN,
# or when student code shouldn't leave the machine. Ollama serves the same
# OpenAI-compatible chat-completions API, so the call itself is shared; only the endpoint,
# model, auth and timeout differ. No key needed. The longer timeout is because a small
# model on a CPU-only laptop took ~9-38s per call when this project last ran it locally
# (pedagogical-feedback-design-decision.md).
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")


def _resolve_llm_config(provider: str) -> dict:
    """The endpoint/model/key/timeout for LLM_PROVIDER. An unknown provider raises, so a
    typo fails loudly at startup instead of silently falling back to the generic line."""
    provider = (provider or "idun").strip().lower()
    if provider == "idun":
        return {"provider": "idun", "base_url": IDUN_BASE_URL, "model": IDUN_MODEL,
                "api_key": IDUN_API_KEY, "timeout": 60}
    if provider == "ollama":
        return {"provider": "ollama", "base_url": OLLAMA_BASE_URL, "model": OLLAMA_MODEL,
                "api_key": None, "timeout": 120}
    raise ValueError(f"LLM_PROVIDER must be 'idun' or 'ollama', got {provider!r}")


LLM = _resolve_llm_config(os.environ.get("LLM_PROVIDER", "idun"))

WRONG_ANSWER_SUBCLUSTER_PROMPT = (
    "You are writing a short, factual note for a lecturer's own dashboard about a group "
    "of students whose code produced the wrong output on the same exercise. You are given "
    "1-3 of those students' code snippets (comments removed). Different students may use "
    "different variable names for the same thing. You may also be given the exercise's own "
    "reference (correct) solution -- it is for context only, never one of the snippets to "
    "describe.\n"
    "Describe only the pattern that is visibly shared "
    "across ALL of the given snippets AND, when a reference solution is shown, is "
    "actually DIFFERENT from it -- e.g. a specific operator, an off-by-one style "
    "adjustment, a missing or extra call, a particular loop or condition shape. Code the "
    "snippets share with the reference solution is normal, correct code, not the bug -- "
    "never describe it as if it were the shared pattern, even if it looks distinctive. "
    "Name the specific function, method, argument, literal, or operator involved (e.g. "
    "'call .lower()', 'pass reverse=True to sorted()', 'use range(len(t) - 1)') rather than "
    "describing it abstractly. Do not guess a root cause or what the students intended "
    "unless it is literally visible in every snippet shown. If the snippets don't share an "
    "obvious concrete pattern that differs from the reference, say plainly that they don't "
    "rather than inventing one. Given a single snippet, describe how it differs from the "
    "reference solution.\n"
    "Only refer to a variable by name if every snippet uses that same name; otherwise "
    "describe what it holds (e.g. 'the lowercased string').\n"
    "Write in third person, for the lecturer, about the students -- never 'you' or "
    "'your'.\n"
    "Format: ONE short factual sentence about the code itself, with no headline or label "
    "in front of it (the dashboard shows its own title above it). Never mention "
    "'snippets', the reference or correct solution, or the group of students ('both', "
    "'all', 'the students', 'each student') -- the lecturer sees this next to the code and "
    "doesn't need to be told where it came from. Say what the right code would be directly "
    "instead (\"uses 'aeio' instead of 'aeiou'\"). Examples of the format:\n"
    "  The loop uses range(1, n), which stops before n, so the last number is left out.\n"
    "  sorted() is called without reverse=True, so the list comes out smallest first.\n"
    "If there is no shared pattern, say so plainly and briefly how the code differs.\n"
    "Respond with ONLY a JSON object with exactly this key:\n"
    "  \"discussion_point\": the one-sentence factual note\n"
    "No other keys, no markdown fences, no explanation outside the JSON object."
)

_SECOND_PERSON_RE = re.compile(r"\byou\b|\byour\b|\byou're\b|\byours\b", re.IGNORECASE)

_discussion_cache = {}  # (question_id, exec_verdict, error_type) -> str or None
_subcluster_discussion_cache = {}  # (reference, snippets shown) -> str
_subcluster_label_failed_at = {}  # same key -> time.monotonic() of the last failed Label call
_LABEL_RETRY_SECONDS = 60

# Model calls currently running, per cache key -- see _single_flight().
_inflight_lock = threading.Lock()
_label_inflight = {}  # Label cache key -> Future
_headline_inflight = {}  # Headline cache key -> Future


def _single_flight(inflight: dict, key, compute):
    """Runs compute() for `key` unless a call for the same key is already running,
    in which case it waits for that one and returns its result.

    Fixed 2026-11-18: overlapping requests for the same uncached label each made
    their own model call -- the dashboard's 3 s cluster poll firing again before a
    slow poll had answered, a second lecturer tab, a raise, the summary. The
    caches only help once a call has finished; this covers the calls still
    running. A waiter is no slower than before (it would otherwise have made the
    same call itself), and it gets the same text the first request cached.

    compute() should re-check its cache first: a call that finished between the
    caller's own cache check and this one has already left `inflight`."""
    with _inflight_lock:
        future = inflight.get(key)
        owner = future is None
        if owner:
            future = Future()
            inflight[key] = future
    if not owner:
        return future.result()
    try:
        result = compute()
        future.set_result(result)
        return result
    except BaseException as e:
        future.set_exception(e)
        raise
    finally:
        with _inflight_lock:
            inflight.pop(key, None)

# Placeholder for a stripped tokenize.NEWLINE (end of a logical statement) -- see
# _canonicalize()'s docstring for why this can't just be dropped like NL/INDENT/
# DEDENT/etc. are. Unambiguous against real Python tokens (not a valid identifier
# or operator), so it can't collide with anything _canonicalize() also emits.
_STMT_BREAK = "STMT_BREAK"

def _canonicalize(source_code: str) -> str:
    """Renames every non-keyword identifier to VAR1/VAR2/... in order of first
    appearance, so two students' differently-named variables/functions don't make
    structurally-identical code look different for similarity comparison. Falls back
    to the raw source if it can't be tokenized -- defensive only, since wrong_answer
    by definition means the code ran without crashing, so a tokenize failure here
    would be unexpected.

    Every tokenize.NEWLINE (end of a logical statement) becomes a literal
    _STMT_BREAK token rather than being dropped silently. Found 2026-09-21 via a
    real Label-step spot-check: dropping NEWLINE with no placeholder means two
    adjacent statements on separate lines collapse into one space-joined token run
    indistinguishable from a single expression -- e.g. "nums = input().split()" +
    "print(int(nums[0]))" canonicalizes (without this marker) to a token stream
    where the only thing between the two statements is a bare space, the exact same
    shape a real missing-`.`-between-two-chained-calls bug would produce. The LLM
    Label call, given only that token stream, fabricated exactly that: a "space
    instead of a dot" / "two calls on the same line" bug that was never in the
    source, on two separate real generated-sample rows (independently, same root
    cause). NL (a non-logical newline -- blank lines, comments, or line
    continuations inside brackets) is deliberately NOT marked: unlike NEWLINE, NL
    can occur in the *middle* of one still-open logical statement (see
    tokenize's own behavior on e.g. "x = (\\n    1 +\\n    2\\n)"), so marking it
    would fabricate a false statement boundary inside a single expression --
    trading one join-collision bug for the opposite one.
    """
    mapping = {}
    next_id = 1
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source_code).readline):
            if tok.type == tokenize.NAME and not keyword.iskeyword(tok.string):
                if tok.string not in mapping:
                    mapping[tok.string] = f"VAR{next_id}"
                    next_id += 1
                out.append(mapping[tok.string])
            elif tok.type == tokenize.NEWLINE:
                out.append(_STMT_BREAK)
            elif tok.type in (
                tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
                tokenize.ENCODING, tokenize.ENDMARKER, tokenize.COMMENT,
            ):
                continue
            else:
                out.append(tok.string)
        return " ".join(out)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source_code


def _strip_comments(source_code: str) -> str:
    """The student's own code, minus comments -- what the Label call is shown
    (see _call_llm_subcluster_pattern's docstring for why that's no longer the
    _canonicalize() form). Comments are dropped because they can state the bug
    outright (the research corpora's "# forgot to lowercase" annotations would hand
    the model the answer) and are the one free-text field in a submission that
    could carry anything personal. Lines left empty by removing a whole-line comment
    are dropped too; everything else -- names, layout, indentation -- is unchanged.
    Falls back to the raw source if it can't be tokenized, same as _canonicalize()."""
    try:
        comments = [
            tok for tok in tokenize.generate_tokens(io.StringIO(source_code).readline)
            if tok.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source_code
    lines = source_code.splitlines()
    comment_only = set()
    for tok in comments:
        row, col = tok.start[0] - 1, tok.start[1]
        lines[row] = lines[row][:col].rstrip()
        if not lines[row].strip():
            comment_only.add(row)
    return "\n".join(line for i, line in enumerate(lines) if i not in comment_only)


def _diff_tokens(reference_solution: str, source_code: str) -> str:
    """Tagged, space-joined sequence of the tokens that differ between
    `source_code` and `reference_solution`, both canonicalized first via
    _canonicalize() -- so identifier naming doesn't matter on either side, same as
    the raw-code TF-IDF this replaced. Tokens common to both (shared boilerplate --
    the function signature, the input()/print() shell) are dropped entirely rather
    than merely down-weighted; the rest are tagged DEL: (present in the reference,
    missing from the submission) or INS: (present in the submission, not in the
    reference) so a deletion and an insertion of the same token don't collide. See
    the 2026-09-21 finding in the module docstring for why this replaced diffing
    against nothing (i.e. plain TF-IDF over the submission's own code)."""
    ref_tokens = _canonicalize(reference_solution).split()
    sub_tokens = _canonicalize(source_code).split()
    matcher = difflib.SequenceMatcher(None, ref_tokens, sub_tokens, autojunk=False)

    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            parts.extend(f"DEL:{t}" for t in ref_tokens[i1:i2])
        if tag in ("insert", "replace"):
            parts.extend(f"INS:{t}" for t in sub_tokens[j1:j2])
    return " ".join(parts)


def _cluster_by_similarity(rows: list, reference_solution: str) -> list:
    """Groups submissions by how they diverge from the exercise's reference
    solution (see the 2026-09-21 finding in the module docstring for why this
    replaced clustering on each submission's own raw code): represent each row by
    its diff-against-reference tokens (_diff_tokens()), TF-IDF that, agglomerative-
    cluster on cosine distance with no fixed k. Returns a list of groups (each a
    list of rows); a group of size 1 is a natural outlier, not an error."""
    if len(rows) < 2:
        return [[r] for r in rows]

    diffs = [_diff_tokens(reference_solution, r["source_code"]) for r in rows]
    try:
        matrix = TfidfVectorizer(token_pattern=_TOKEN_PATTERN).fit_transform(diffs)
    except ValueError:
        return [[r] for r in rows]  # empty vocabulary -- nothing to compare on
    if matrix.shape[1] == 0:
        return [[r] for r in rows]

    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=WRONG_ANSWER_SUBCLUSTER_DISTANCE,
        metric="cosine",
        linkage="complete",
    ).fit_predict(matrix.toarray())

    groups = defaultdict(list)
    for row, label in zip(rows, labels):
        groups[int(label)].append(row)
    return list(groups.values())


def _parsed_results(row: dict):
    """raw_test_results as a non-empty list of dicts, or None."""
    raw = row.get("raw_test_results")
    if not raw:
        return None
    try:
        results = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(results, list) or not results or not all(isinstance(r, dict) for r in results):
        return None
    return results


def _is_test_graded(results) -> bool:
    """Results from a test-graded task (backend/task_runner.py) carry each test's id."""
    return bool(results) and "test_id" in results[0]


def _failing_test_signature(row: dict):
    """A test-graded submission's first-level signature: the set of tests it failed
    (visible and hidden), as a sorted tuple of test ids -- the counterpart of
    _output_signature() for tasks whose tests report pass/fail, not printed output.
    None for stdout-graded rows or rows without results."""
    results = _parsed_results(row)
    if not _is_test_graded(results):
        return None
    return tuple(sorted(r["test_id"] for r in results if not r.get("passed")))


def _output_signature(row: dict):
    """What this submission actually printed, as a tuple with one entry per test
    case in order: "PASS" for a passed case, otherwise its stdout with surrounding
    whitespace stripped and internal whitespace runs collapsed to one space. Two
    submissions with equal signatures behaved identically on every test the
    question has, however differently their code is written -- see the 2026-10-15
    entry in the module docstring.

    Read from raw_test_results, which already holds Judge0's per-test result for
    every graded submission (a JSON list of run_test_cases() dicts: stdout, passed,
    case_index, ...), so this costs no extra execution. Returns None when that's
    missing, unparseable, or empty (a rejected submission stores "[]") -- such rows
    fall through to diff-based clustering instead of all sharing one empty
    signature."""
    results = _parsed_results(row)
    if results is None or _is_test_graded(results):
        return None
    results = sorted(results, key=lambda r: r.get("case_index", 0))
    return tuple(
        "PASS" if r.get("passed") else " ".join((r.get("stdout") or "").split())
        for r in results
    )


def _group_wrong_answers(rows: list, reference_solution: str, question_id: str = None) -> list:
    """Two-level grouping of one question's wrong_answer rows (see the 2026-10-15
    entry in the module docstring). Level 1: rows with equal _output_signature()
    are one group. Level 2: _cluster_by_similarity() (diff against the reference)
    splits a level-1 group further only when its signature is weak -- see
    MIN_TESTS_FOR_FINAL_SIGNATURE. Rows with no signature skip level 1 and are
    diff-clustered exactly as before. Returns a list of groups (lists of rows).
    Each level's latency is logged, same as diff+cluster always was.

    Test-graded rows: level 1 is the set of failing tests (_failing_test_signature()),
    and level 2 always runs inside each group. Unlike a printed-output signature, two
    students failing the same tests may have produced different wrong values (an
    assertion only says "not equal"), so the failing set alone is never final."""
    t0 = time.monotonic()
    by_signature = defaultdict(list)
    by_failing_tests = defaultdict(list)
    unsigned = []
    for row in rows:
        failing_tests = _failing_test_signature(row)
        if failing_tests is not None:
            by_failing_tests[failing_tests].append(row)
            continue
        signature = _output_signature(row)
        if signature is None:
            unsigned.append(row)
        else:
            by_signature[signature].append(row)
    logger.info(
        "wrong_answer signature: question=%s, %d submissions -> %d signature groups, %d failing-test groups "
        "(%d without a signature), %.3fs",
        question_id, len(rows), len(by_signature), len(by_failing_tests), len(unsigned), time.monotonic() - t0,
    )

    t0 = time.monotonic()
    groups = []
    diffed = 0
    for signature, members in by_signature.items():
        if len(signature) < MIN_TESTS_FOR_FINAL_SIGNATURE:
            groups.extend(_cluster_by_similarity(members, reference_solution))
            diffed += len(members)
        else:
            groups.append(members)
    for members in by_failing_tests.values():
        groups.extend(_cluster_by_similarity(members, reference_solution))
        diffed += len(members)
    if unsigned:
        groups.extend(_cluster_by_similarity(unsigned, reference_solution))
        diffed += len(unsigned)
    logger.info(
        "wrong_answer diff+cluster: question=%s, %d of %d submissions diff-clustered -> %d groups total, %.3fs",
        question_id, diffed, len(rows), len(groups), time.monotonic() - t0,
    )
    return groups


def _shared_failing_cases(group: list) -> list:
    """Every test case all rows in `group` failed with the same (normalized)
    output, in test order, as {"stdin", "expected_stdout", "stdout"} dicts --
    see _shared_failing_case() for the first one alone."""
    parsed = []
    for row in group:
        try:
            results = json.loads(row.get("raw_test_results") or "[]")
        except (TypeError, ValueError):
            return []
        if not isinstance(results, list) or not results:
            return []
        parsed.append({r.get("case_index", i): r for i, r in enumerate(results) if isinstance(r, dict)})
    if _is_test_graded(list(parsed[0].values())):
        return _shared_failing_tests(parsed)
    shared = []
    for index in sorted(parsed[0]):
        cases = [p.get(index) for p in parsed]
        if any(c is None or c.get("passed") for c in cases):
            continue
        outputs = {" ".join((c.get("stdout") or "").split()) for c in cases}
        if len(outputs) == 1:
            first = cases[0]
            shared.append(
                {
                    "stdin": first.get("stdin", ""),
                    "expected_stdout": first.get("expected_stdout", ""),
                    "stdout": outputs.pop(),
                }
            )
    return shared


def _failing_tests_of_group(group: list):
    """For a test-graded wrong-answer group: the tests its submissions fail, as
    [{"name", "visibility"}] in test order -- the same for every row, since the group's
    first level is the failing-test set. None for stdout-graded groups. Lecturer-side
    (the dashboard), so hidden tests are named too."""
    results = _parsed_results(group[0]) if group else None
    if not _is_test_graded(results):
        return None
    return [{"name": r.get("test_name"), "visibility": r.get("visibility")}
            for r in sorted(results, key=lambda r: r.get("case_index", 0)) if not r.get("passed")]


def _shared_failing_tests(parsed: list) -> list:
    """_shared_failing_cases() for test-graded rows: every test all rows failed, in test
    order, with the same keys (stdin/expected_stdout empty; stdout holds the failure
    message when every row's message is identical, else the first row's) plus the
    test's name, id and visibility. Lecturer-side evidence: hidden tests included."""
    shared = []
    for index in sorted(parsed[0]):
        cases = [p.get(index) for p in parsed]
        if any(c is None or c.get("passed") or c.get("test_id") != cases[0].get("test_id") for c in cases):
            continue
        first = cases[0]
        shared.append({
            "stdin": "",
            "expected_stdout": "",
            "stdout": first.get("message") or "",
            "test_id": first.get("test_id"),
            "test_name": first.get("test_name"),
            "visibility": first.get("visibility"),
            "message": first.get("message") or "",
            "same_message": len({c.get("message") for c in cases}) == 1,
        })
    return shared


def _shared_failing_case(group: list):
    """The first test case every row in `group` failed with the same (normalized)
    output, as {"stdin", "expected_stdout", "stdout"} -- or None if there isn't one.
    Not used by the Label call since the 2026-10-15 revert (see the module
    docstring); kept for feedback-research/label-spot-checks/generate_real_discussion_point_sample.py's
    round-5 sample and a planned control run. Always found for a final signature group (its rows printed
    the same thing on every test); not guaranteed for a diff-clustered group, whose
    rows are alike in code, not necessarily in output."""
    cases = _shared_failing_cases(group)
    return cases[0] if cases else None


def _representative_snippets(group: list, max_n: int = 3) -> list:
    """Up to max_n comment-stripped snippets (_strip_comments()) from distinct
    students in this group, for the Label call -- never the full group (keeps the
    call cheap and the model from over-indexing on one student's resubmissions).

    The FIRST students to land in the group, each by their first submission in it
    (oldest id first), not the newest. Changed 2026-11-18 with the Label cache key
    (see _subcluster_discussion_point()): picking the newest meant every new
    submission changed what the model was shown, so the label was regenerated on
    nearly every poll. Picked oldest-first, a group's input stops changing once it
    has max_n students. Every row in a group shares the same output signature (or
    the same diff shape), so the earliest students show the bug as well as the
    latest do."""
    seen_students = set()
    picked = []
    for row in sorted(group, key=lambda r: r["id"]):
        if row["student_name"] in seen_students:
            continue
        seen_students.add(row["student_name"])
        picked.append(_strip_comments(row["source_code"]))
        if len(picked) >= max_n:
            break
    return picked


def _llm_available() -> bool:
    """IDUN: just checks a key is configured -- the gateway has no cheap unauthenticated
    health check, so a bad key or unreachable network (off NTNU network/VPN) still
    surfaces as a request failure, caught by _call_llm_subcluster_pattern's caller same
    as any other failure mode. Ollama needs no key, so it's always worth trying; Ollama
    not running is a connection error, caught the same way."""
    if LLM["provider"] == "idun":
        return bool(LLM["api_key"])
    return True


def _call_llm_subcluster_pattern(snippets: list, reference_solution: str = None) -> str:
    """One JSON-mode call given 2-3 comment-stripped snippets from one similarity
    sub-cluster, via the configured provider's (LLM_PROVIDER: IDUN or Ollama)
    OpenAI-compatible chat-completions endpoint. Raises on
    network failure, invalid JSON, a response that doesn't satisfy the schema, or
    second-person phrasing -- caller retries/falls back to the generic wrong_answer
    line.

    `reference_solution` -- the exercise's own reference solution, comment-stripped
    the same way as `snippets` -- is optional context, not a snippet to describe
    (see WRONG_ANSWER_SUBCLUSTER_PROMPT). Added 2026-09-21 after a real spot-check
    found the model repeatedly restating structure the submissions share with the
    CORRECT solution as if it were the shared bug (e.g. "both compare a variable to
    its reversed slice" on an is_palindrome case where that comparison is also in
    the reference solution -- the actual bug was a missing .lower() call). Without
    ever seeing the reference, the model had no way to tell normal/correct code from
    the actual divergence. Deliberately NOT the diff-tokens representation
    _cluster_by_similarity() already computes for clustering: that representation
    numbers variables independently per snippet, so a single real difference before
    a shared call cascades into a run of spurious DEL/INS pairs from pure
    renumbering -- fine for a TF-IDF vectorizer (order/coherence don't matter to
    it), unreadable as a prompt.

    Changed 2026-10-13: snippets and reference are the students' real code (comments
    stripped), no longer _canonicalize()'s VARn token stream. Round 3's spot-check
    rated 9 of 16 rows only partially grounded, all for one reason: canonicalization
    renames builtins and methods too (lower, replace, sorted, reverse, int), so the
    model could see THAT something differed but not WHAT -- "omits the subsequent
    method call that takes the two string literals" for a missing .replace(" ", ""),
    "without the keyword argument set to True" for a missing reverse=True. Anonymizing
    names is what clustering needs (two students' different variable names mustn't
    split identical code); it was never a requirement of the Label call, just
    inherited from reusing the clustering input. Student names are still never sent.

    Not shown the group's shared failing test: tried 2026-10-15 and reverted the same
    day after spot-check round 5 -- see the module docstring's 2026-10-15 entry."""
    parts = []
    if reference_solution:
        parts.append(
            "Reference (correct) solution -- for context only, not one of the "
            "snippets to describe:\n\n" + reference_solution
        )
    parts.append("Snippets:\n\n" + "\n\n---\n\n".join(snippets))
    prompt = "\n\n".join(parts) + "\n\nRespond with the JSON object described in the system prompt."
    take_llm_call()  # the server-wide LLM budget (backend/rate_limit.py); raises over it
    headers = {"Authorization": f"Bearer {LLM['api_key']}"} if LLM["api_key"] else {}
    resp = requests.post(
        f"{LLM['base_url']}/chat/completions",
        headers=headers,
        json={
            "model": LLM["model"],
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": WRONG_ANSWER_SUBCLUSTER_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=LLM["timeout"],
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    point = parsed.get("discussion_point")
    if not isinstance(point, str) or not point.strip():
        raise ValueError(f"missing discussion_point in LLM response: {parsed!r}")
    point = point.strip()
    if _SECOND_PERSON_RE.search(point):
        raise ValueError(f"discussion_point addressed the student, not the lecturer: {point!r}")
    return point


def _subcluster_discussion_point(group: list, reference_solution: str, student_count: int, raised: bool = False):
    """`reference_solution` -- the exercise's raw (not yet canonicalized) reference
    solution, or None/empty if unavailable -- is comment-stripped here and passed as
    context to the IDUN call (see _call_llm_subcluster_pattern's docstring for
    why). None is a legitimate value, not an error: it just means the call falls
    back to the pre-2026-09-21 behavior of describing the snippets with no
    reference-relative context.

    `raised` -- the lecturer flagged this issue (see raise_issue()) -- lifts the
    MIN_STUDENTS_FOR_DISCUSSION gate, so a one-student sub-cluster is labeled
    from its single snippet. Single-snippet labels haven't been through a
    spot-check round yet; every rated round so far had 2-3 snippets per row.

    Cached on exactly what the model is shown -- the snippets and the reference --
    since that's all the label depends on. Until 2026-11-18 the key was the set of
    every submission id in the group, so each new submission joining a group (or a
    student resubmitting the same bug) meant a fresh Label call, and a fresh
    Headline call for the new text: about one model call per wrong-answer
    submission. With _representative_snippets() picking the group's first students,
    a group is labeled at most once per student count up to 3, plus again only if
    reclustering changes who its first students are.

    A failed call isn't cached as the answer: the fallback is shown, and the call is
    retried on a later poll, at most once per _LABEL_RETRY_SECONDS so a gateway
    outage doesn't make every 3-second dashboard poll wait out a timeout."""
    if student_count < MIN_STUDENTS_FOR_DISCUSSION and not raised:
        return None

    fallback = hints.discussion_point_for_cluster("wrong_answer", None, student_count)
    snippets = _representative_snippets(group)
    reference = _strip_comments(reference_solution) if reference_solution else None
    cache_key = (reference, tuple(snippets))
    if cache_key in _subcluster_discussion_cache:
        return _subcluster_discussion_cache[cache_key]
    failed_at = _subcluster_label_failed_at.get(cache_key)
    if failed_at is not None and time.monotonic() - failed_at < _LABEL_RETRY_SECONDS:
        return fallback

    # Token count measured on the canonicalized form, same as before the 2026-10-13
    # switch to showing real code -- this is a "too little code to describe" gate,
    # independent of what the model is shown.
    trivial = any(len(_canonicalize(s).split()) < _MIN_TOKENS_FOR_PATTERN_CALL for s in snippets)
    if not snippets or trivial or not _llm_available():
        _subcluster_discussion_cache[cache_key] = fallback
        return fallback

    return _single_flight(
        _label_inflight, cache_key, lambda: _label_now(cache_key, snippets, reference, fallback)
    )


def _label_now(cache_key, snippets: list, reference, fallback: str) -> str:
    """The Label call itself, for _subcluster_discussion_point() -- only ever run
    by one request at a time per cache key (see _single_flight())."""
    if cache_key in _subcluster_discussion_cache:
        return _subcluster_discussion_cache[cache_key]
    failed_at = _subcluster_label_failed_at.get(cache_key)
    if failed_at is not None and time.monotonic() - failed_at < _LABEL_RETRY_SECONDS:
        return fallback

    result = None
    t0 = time.monotonic()
    for _attempt in (1, 2):
        try:
            result = _call_llm_subcluster_pattern(snippets, reference)
            break
        except Exception:
            continue
    logger.info(
        "wrong_answer sub-cluster LLM call (%s): %d snippets, %.3fs, used_model=%s",
        LLM["provider"], len(snippets), time.monotonic() - t0, result is not None,
    )
    if result is None:
        _subcluster_label_failed_at[cache_key] = time.monotonic()
        return fallback
    _subcluster_label_failed_at.pop(cache_key, None)
    _subcluster_discussion_cache[cache_key] = result
    return result


HEADLINE_PROMPT = (
    "You are helping a lecturer run a live programming class. You are given one issue a "
    "group of students ran into: its error category and a short factual note about it. "
    "Rewrite it for the lecturer's dashboard as:\n"
    "  \"title\": a 3-8 word headline naming the mistake, in sentence case (no ending "
    "period, don't just repeat the category name)\n"
    "  \"action\": ONE short sentence telling the lecturer what to do with the class about "
    "it right now, e.g. what to show, trace or ask on the board\n"
    "Use only what the note says -- never add a cause, code detail or example it doesn't "
    "contain. Address the lecturer in the imperative (\"Show...\", \"Trace...\"); never "
    "speak to the students.\n"
    "Respond with ONLY a JSON object with exactly the keys \"title\" and \"action\". No "
    "markdown fences, no explanation outside the JSON object."
)

_headline_cache = {}  # (category, discussion_point) -> {"title", "action"}
_headline_failed_at = {}  # same key -> time.monotonic() of the last failed Headline call


def _category_label(exec_verdict: str, error_type) -> str:
    label = (exec_verdict or "unknown").replace("_", " ").capitalize()
    return f"{label} ({error_type})" if error_type and error_type != "none" else label


def _call_llm_headline(category: str, discussion_point: str) -> dict:
    """One JSON-mode call: the cluster's category + its existing discussion_point
    (the AI Label note for wrong_answer, the curated line otherwise) -> a short
    title and one lecturer action. Deliberately a separate call that only ever sees
    that text, never code: the note itself stays exactly the rated Label output
    (see the module docstring), and with nothing but the note to go on the model has
    nothing to invent a cause from. Raises on any failure; caller falls back to None."""
    take_llm_call()  # the server-wide LLM budget (backend/rate_limit.py); raises over it
    headers = {"Authorization": f"Bearer {LLM['api_key']}"} if LLM["api_key"] else {}
    resp = requests.post(
        f"{LLM['base_url']}/chat/completions",
        headers=headers,
        json={
            "model": LLM["model"],
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": HEADLINE_PROMPT},
                {"role": "user", "content": f"Category: {category}\nNote: {discussion_point}"},
            ],
        },
        timeout=LLM["timeout"],
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    title, action = parsed.get("title"), parsed.get("action")
    if not (isinstance(title, str) and title.strip() and isinstance(action, str) and action.strip()):
        raise ValueError(f"missing title/action in LLM response: {parsed!r}")
    return {"title": title.strip().rstrip("."), "action": action.strip()}


def _headline(category: str, discussion_point: str):
    """Same caching as the Label call: one call per (category, note) even when
    requests overlap (_single_flight()), and a failed call isn't cached as "no
    headline" for good -- with labels now stable, a note's text no longer changes,
    so that cached None would never be replaced. The dashboard shows the note as
    the headline meanwhile, and the call is retried at most once per
    _LABEL_RETRY_SECONDS."""
    key = (category, discussion_point)
    if key in _headline_cache:
        return _headline_cache[key]
    if not _llm_available():
        return None
    failed_at = _headline_failed_at.get(key)
    if failed_at is not None and time.monotonic() - failed_at < _LABEL_RETRY_SECONDS:
        return None
    return _single_flight(_headline_inflight, key, lambda: _headline_now(key, category, discussion_point))


def _headline_now(key, category: str, discussion_point: str):
    if key in _headline_cache:
        return _headline_cache[key]
    failed_at = _headline_failed_at.get(key)
    if failed_at is not None and time.monotonic() - failed_at < _LABEL_RETRY_SECONDS:
        return None
    result = None
    t0 = time.monotonic()
    for _attempt in (1, 2):
        try:
            result = _call_llm_headline(category, discussion_point)
            break
        except Exception:
            continue
    logger.info("headline LLM call (%s): %.3fs, ok=%s", LLM["provider"], time.monotonic() - t0, result is not None)
    if result is None:
        _headline_failed_at[key] = time.monotonic()
        return None
    _headline_failed_at.pop(key, None)
    _headline_cache[key] = result
    return result


def _attach_headlines(clusters: list) -> None:
    """Adds "title" and "action" (None when there's no discussion point or the call
    failed -- the dashboard then shows the note itself as the headline) to every
    cluster in place. Calls run in parallel, same reasoning as
    _generate_subcluster_labels()."""
    for c in clusters:
        c["title"] = None
        c["action"] = None
    pending = [c for c in clusters if c.get("discussion_point") and c["exec_verdict"] != "pass"]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=min(len(pending), _MAX_PARALLEL_LABEL_CALLS)) as pool:
        futures = {
            pool.submit(_headline, _category_label(c["exec_verdict"], c["error_type"]), c["discussion_point"]): c
            for c in pending
        }
        for future in as_completed(futures):
            h = future.result()
            if h:
                futures[future].update(h)


def _distinct_student_submission_ids(rows: list) -> list:
    """One submission id per distinct student -- their most recent attempt in this
    group, since rows is already newest-first (from store.all_submissions()). Lets
    the lecturer view every distinct student's example for a cluster, not just one,
    without also dumping every resubmission of the same bug."""
    seen_students = set()
    ids = []
    for row in rows:
        if row["student_name"] in seen_students:
            continue
        seen_students.add(row["student_name"])
        ids.append(row["id"])
    return ids


def _generate_subcluster_labels(groups_with_counts: list, raised_flags: list = None) -> list:
    """Returns one discussion_point (or None, below MIN_STUDENTS_FOR_DISCUSSION and
    not raised) per (group, reference_solution, student_count) in
    `groups_with_counts`, same order in. `raised_flags`, if given, is a parallel
    list of bools -- see raise_issue().

    Sub-clusters are independent of each other -- often from different questions
    entirely, and even within one question a bug shape in one sub-cluster has
    nothing to do with another's -- so their Label (IDUN) calls have no reason to
    wait on each other. Earlier this was a plain sequential loop, one IDUN call
    at a time; on a question with several sub-clusters clearing the discussion
    threshold at once, that serialized N single-call latencies (each a real,
    multi-second network round trip -- see the module docstring's latency
    measurements) into one N-times-longer wait before a lecturer's dashboard could
    show any of them. Below-threshold groups cost nothing extra here --
    _subcluster_discussion_point() returns None immediately without a thread or a
    network call.
    """
    results = [None] * len(groups_with_counts)
    raised_flags = raised_flags or [False] * len(groups_with_counts)
    pending = {
        i: (group, reference_solution, student_count, raised)
        for i, ((group, reference_solution, student_count), raised) in enumerate(zip(groups_with_counts, raised_flags))
        if student_count >= MIN_STUDENTS_FOR_DISCUSSION or raised
    }
    if not pending:
        return results

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(len(pending), _MAX_PARALLEL_LABEL_CALLS)) as pool:
        futures = {
            pool.submit(_subcluster_discussion_point, group, reference_solution, student_count, raised): i
            for i, (group, reference_solution, student_count, raised) in pending.items()
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    logger.info(
        "wrong_answer sub-cluster Label calls: %d sub-cluster(s), %.3fs wall-clock "
        "(parallel, max_workers=%d)",
        len(pending), time.monotonic() - t0, min(len(pending), _MAX_PARALLEL_LABEL_CALLS),
    )
    return results


def _wrong_answer_subclusters(members: list) -> list:
    """Sub-clusters one exec_verdict=="wrong_answer" bucket by what the submissions
    printed, then (only where that's too coarse) by divergence from the exercise's
    own reference solution (see _group_wrong_answers()). Scoped per question_id
    first: outputs and code are only comparable within one exercise, and each
    question_id has its own test cases and reference_solution. Returns cluster dicts in the same
    shape cluster_submissions() uses for every other category.

    Clustering itself stays per-question (a diff-against-reference signal is
    meaningless across different exercises), but the resulting sub-clusters' Label
    calls are gathered across ALL questions in `members` and dispatched together via
    _generate_subcluster_labels() -- see that function's docstring for why."""
    by_question = defaultdict(list)
    for row in members:
        by_question[row["question_id"]].append(row)

    all_groups = []
    for question_id, rows in by_question.items():
        question = store.get_question_row(question_id)
        reference_solution = question.get("reference_solution") if question else None
        if not reference_solution:
            # Shouldn't happen in practice -- a question can't reach 'live' (and
            # therefore can't have wrong_answer submissions at all) without a
            # reference_solution; validate() in main.py refuses without one. Falls
            # back to singletons rather than diffing every submission against
            # nothing if this invariant is ever violated by a data anomaly.
            logger.warning(
                "wrong_answer sub-clustering: question=%s has no reference_solution, "
                "skipping diff-based clustering", question_id,
            )
            groups = [[r] for r in rows]
        else:
            groups = _group_wrong_answers(rows, reference_solution, question_id)
        all_groups.extend((group, reference_solution) for group in groups)

    groups_with_counts = [
        (group, reference_solution, len({m["student_name"] for m in group}))
        for group, reference_solution in all_groups
    ]
    raised_flags = [
        _is_raised(group[0]["question_id"], "wrong_answer", None, {m["student_name"] for m in group})
        for group, _reference_solution, _student_count in groups_with_counts
    ]
    labels = _generate_subcluster_labels(groups_with_counts, raised_flags)

    result = []
    for (group, _reference_solution, student_count), discussion_point, raised in zip(
        groups_with_counts, labels, raised_flags
    ):
        example = group[0]
        result.append(
            {
                "exec_verdict": "wrong_answer",
                "error_type": None,
                "count": student_count,
                "example_submission_id": example["id"],
                "submission_ids": _distinct_student_submission_ids(group),
                "discussion_point": discussion_point,
                "raised": raised,
                "failing_tests": _failing_tests_of_group(group),
            }
        )
    return result


def _generate_discussion_point(exec_verdict: str, error_type: str, student_count: int):
    if exec_verdict == "missing_output_file":
        # Set in main.api_submit when the task's output file was never written.
        return "Ran without errors but never wrote the output file. Worth showing how to open a file for writing."
    if exec_verdict == "ignores_input":
        # Set in main.api_submit, not by the classifier, so it has no curated
        # line in feedback-research/feedback.py.
        return "Prints a fixed answer without reading the input. Worth showing why that only passes by luck."
    try:
        return hints.discussion_point_for_cluster(exec_verdict, error_type, student_count)
    except Exception:
        return None  # no recognized family -- nothing safe to say


def _cached_discussion_point(question_id, exec_verdict, error_type, student_count, raised=False):
    if student_count < MIN_STUDENTS_FOR_DISCUSSION and not raised:
        return None
    cache_key = (question_id, exec_verdict, error_type)
    if cache_key not in _discussion_cache:
        _discussion_cache[cache_key] = _generate_discussion_point(
            exec_verdict, error_type, student_count
        )
    return _discussion_cache[cache_key]


def _is_raised(question_id, exec_verdict, error_type, students: set) -> bool:
    return any(
        (r["exec_verdict"], r["error_type"]) == (exec_verdict, error_type) and r["students"] & students
        for r in store.raised_issue_rows(question_id)
    )


def raise_issue(
    question_id: str, exec_verdict: str, error_type, submission_ids: list, raised: bool, example_submission_id=None
):
    """Shows (or stops showing) one issue to the class, chosen by the lecturer: its
    example goes to every student's waiting screen once time is up (see
    shown_examples()), and the issue gets a discussion point and sorts first on
    the lecturer's own dashboard.

    MIN_STUDENTS_FOR_DISCUSSION keeps one student's idiosyncratic mistake off the
    dashboard's talking points by default -- but some single mistakes are exactly
    what's worth taking up with the whole class (a str * 2 doubling the text, an
    off-by-one), and only the lecturer can tell which. Requested in supervision,
    2026-10-13. Deliberately the lecturer's call rather than a curated per-category
    weight (too coarse for wrong_answer, where one category covers every logic bug)
    or a model-judged "teachability" score (the same unverifiable-judgment risk
    pedagogical-feedback-design-decision.md removed twice).

    Flagging alone only reordered the lecturer's list, which did nothing for the
    class -- so (same day) raising also became the way to put the example in front
    of the students, on the screen they're already looking at while the lecturer
    goes over results. Students see the code and its failing test only, no
    discussion point: those are written about students, for the lecturer.

    The issue is identified by the students in it, via `submission_ids` (what the
    dashboard already has per cluster; its first id is the example shown).
    Unraising removes every entry on the same (question, verdict, error_type) that
    shares a student with it. Raises ValueError if none of the ids exist.

    Raising adds to the end of the question's screen queue (see
    store.add_raised_issue()) and returns the new entry's id; unraising
    returns None.

    `example_submission_id` picks which snippet goes on screen -- one issue
    holds several code variants, and the lecturer wants "this one"
    (requested 2026-11-18). Each picked snippet is its own queue entry, so
    one issue can queue several; picking one that's already queued returns
    its existing entry. Unraising with it takes out only that snippet's
    entry. It must be one of `submission_ids` (ValueError otherwise);
    without it the first id is the example, as before."""
    students = set()
    for sub_id in submission_ids:
        row = store.get_submission(sub_id)
        if row:
            students.add(row["student_name"])
    if not students:
        raise ValueError(f"no submissions found for ids {submission_ids!r}")
    if example_submission_id is not None and example_submission_id not in submission_ids:
        raise ValueError(f"submission {example_submission_id} is not in this issue")
    same_issue = [
        r
        for r in store.raised_issue_rows(question_id)
        if (r["exec_verdict"], r["error_type"]) == (exec_verdict, error_type) and r["students"] & students
    ]
    if raised:
        example = example_submission_id if example_submission_id is not None else submission_ids[0]
        existing = next((r["id"] for r in same_issue if r["submission_id"] == example), None)
        if existing is not None:
            return existing
        return store.add_raised_issue(question_id, exec_verdict, error_type, students, example)
    else:
        store.delete_raised_issues(
            [
                r["id"]
                for r in same_issue
                if example_submission_id is None or r["submission_id"] == example_submission_id
            ]
        )


def _shared_example(submission_id: int):
    """One queued submission as the students see it: code with comments
    stripped (the one free-text field in a submission, see _strip_comments()),
    whether it passed every test, and the first test it failed. No student
    name, no discussion point -- see raise_issue()."""
    row = store.get_submission(submission_id)
    if not row:
        return None
    results = json.loads(row.get("raw_test_results") or "[]")
    if _is_test_graded(results):
        # Students see this (their waiting screen) and so does the class (projector):
        # the first failing visible test in full, hidden tests only as a count.
        # The code: comments stripped per file, then joined with the file headers
        # (task_import.join_files) -- stripping the joined text would drop those header
        # lines (they're comments), and the projector's Run splits the files on them.
        files = json.loads(row["files"]) if row.get("files") else None
        source = (task_import.join_files({p: _strip_comments(c) for p, c in files.items()}, list(files),
                                         row.get("language") or "python")
                  if files else _strip_comments(row["source_code"]))
        failing_visible = next((r for r in results if not r.get("passed") and r.get("visibility") != "hidden"), None)
        hidden = [r for r in results if r.get("visibility") == "hidden"]
        return {
            "source_code": source,
            "correct": row.get("verdict") == "correct",
            "failing_test": (
                {"stdin": "", "expected_stdout": "", "stdout": "", "stderr": failing_visible.get("details") or "",
                 "test_name": failing_visible.get("test_name"), "message": failing_visible.get("message") or ""}
                if failing_visible else None
            ),
            "hidden_tests": {"total": len(hidden), "failed": sum(1 for r in hidden if not r.get("passed"))},
        }
    failing = next((r for r in results if not r.get("passed")), None)
    return {
        "source_code": _strip_comments(row["source_code"]),
        "correct": row.get("verdict") == "correct",
        "failing_test": (
            {
                "stdin": failing.get("stdin", ""),
                "expected_stdout": failing.get("expected_stdout", ""),
                "stdout": failing.get("stdout") or "",
                "stderr": failing.get("stderr") or "",
            }
            if failing
            else None
        ),
    }


def shown_examples(question_id: str) -> list:
    """What the class is being shown for this question: the screen queue's
    current entry only (at most one attempt is up at a time -- see
    store.add_raised_issue()), as a list of zero or one. An entry is a raised
    discussion point's example (raise_issue()) or a single submission the
    lecturer picked from a student's attempts (store.set_submission_shown(),
    correct ones included)."""
    current = store.current_queue_entry_id(question_id)
    if current is None:
        return []
    entry = store.get_queue_entry(current)
    example = _shared_example(entry["submission_id"]) if entry else None
    return [example] if example else []


def screen_position(question_id: str):
    """{"index", "total"} of the entry on screen within the queue (0-based
    index), or None if nothing is queued -- for the projector's controls."""
    order = [r["id"] for r in store.queue_rows(question_id)]
    current = store.current_queue_entry_id(question_id)
    if current is None:
        return None
    return {"index": order.index(current), "total": len(order)}


def screen_queue(question_id: str) -> dict:
    """The lecturer's view of the screen queue: every entry in order (with
    student names -- this is for the lecturer's dashboard only) and which one
    is on screen once time is up."""
    current = store.current_queue_entry_id(question_id)
    entries = []
    for r in store.queue_rows(question_id):
        sub = store.get_submission(r["submission_id"]) or {}
        # As shown to the class -- see _shared_example().
        code = _strip_comments(sub.get("source_code") or "")
        entries.append(
            {
                "id": r["id"],
                "kind": "attempt" if r["single"] else "issue",
                "exec_verdict": r["exec_verdict"],
                "error_type": r["error_type"],
                "students": sorted(r["students"]),
                "submission_id": r["submission_id"],
                "verdict": sub.get("verdict"),
                "tests_passed": sub.get("tests_passed"),
                "tests_total": sub.get("tests_total"),
                "lines": len(code.splitlines()),
                "current": r["id"] == current,
            }
        )
    return {"entries": entries, "current_entry_id": current}


def cluster_submissions(question_id: str = None) -> list:
    """Returns clusters ranked by distinct-student count (largest first), each:
      exec_verdict, error_type, count (distinct students), example_submission_id,
      submission_ids (one per distinct student, for "view all"),
      discussion_point (None unless enough distinct students hit this cluster, or the
        lecturer raised it), raised (flagged via raise_issue() -- sorted first)

    wrong_answer is expanded into one or more similarity sub-clusters instead of a
    single entry -- see _wrong_answer_subclusters().
    """
    rows = store.all_submissions(question_id)

    clusters = defaultdict(list)
    for row in rows:
        key = (row.get("exec_verdict"), row.get("error_type"))
        clusters[key].append(row)

    result = []
    for (exec_verdict, error_type), members in clusters.items():
        if exec_verdict == "wrong_answer":
            result.extend(_wrong_answer_subclusters(members))
            continue
        example = members[0]  # all_submissions is already newest-first
        students = {m["student_name"] for m in members}
        student_count = len(students)
        raised = _is_raised(example["question_id"], exec_verdict, error_type, students)
        result.append(
            {
                "exec_verdict": exec_verdict,
                "error_type": error_type,
                "count": student_count,
                "example_submission_id": example["id"],
                "submission_ids": _distinct_student_submission_ids(members),
                "discussion_point": _cached_discussion_point(
                    example["question_id"], exec_verdict, error_type, student_count, raised
                ),
                "raised": raised,
            }
        )

    _attach_headlines(result)
    result.sort(key=lambda c: (c["raised"], c["count"]), reverse=True)
    return result


def _latest_submission_per_student(question_id: str) -> dict:
    """One row per distinct student for this question -- their most recent
    submission, since store.all_submissions() is already newest-first. Used
    by session_summary()/student_recap() below, which care about a
    student's *current* standing on a task, not every resubmission."""
    latest = {}
    for row in store.all_submissions(question_id):
        latest.setdefault(row["student_name"], row)
    return latest


def session_summary(lecture_id: int) -> list:
    """Per-task submission rate + verdict tally for every question in this
    lecture, in the order they were run -- the STATE 2 lecturer summary's
    "how did the class do across ALL tasks" view (distinct from
    cluster_submissions(), which groups by exec_verdict/error_type for
    talking points on the live per-task dashboard; this groups by the
    AI-judged `verdict`, one row per task instead of one row per issue)."""
    tasks = []
    for question in store.questions_for_lecture(lecture_id):
        latest_by_student = _latest_submission_per_student(question["id"])
        verdict_counts = defaultdict(int)
        for row in latest_by_student.values():
            verdict_counts[row.get("verdict") or "error"] += 1
        tasks.append(
            {
                "question_id": question["id"],
                "title": question["title"],
                "submitted": len(latest_by_student),
                "expected": question["expected_students"],
                "verdict_counts": dict(verdict_counts),
            }
        )
    return tasks


def _distinguishing_case(cases: list, sibling_cases: list):
    """The first of a group's shared failing cases (see _shared_failing_cases())
    whose wrong output no other group on the same task also printed for that
    input -- so two different bugs that happen to print the same thing on the
    first test don't show identical evidence. Falls back to the first case."""
    taken = {(c.get("test_id"), c["stdin"], c["stdout"]) for sibling in sibling_cases for c in sibling}
    for case in cases:
        if (case.get("test_id"), case["stdin"], case["stdout"]) not in taken:
            return case
    return cases[0] if cases else None


def carry_forward_discussion_points(lecture_id: int) -> list:
    """What students were still stuck on when each task ended -- the summary's
    "worth revisiting next time" list.

    Built from the same issues the live dashboard showed (cluster_submissions()'s
    grouping, including wrong_answer's per-task sub-clusters), not a coarser
    lecture-wide regrouping. The earlier version grouped by (exec_verdict,
    error_type) only and kept what recurred on 2+ tasks; since nearly every
    mistake is a wrong_answer, that collapsed each lecture into the single
    generic "wrong output" line "recurring" on every task -- true of any lecture
    and no use to anyone.

    A student counts as stuck on an issue if they never got a correct result on
    that task and their *latest* submission is in it -- where they ended up, not
    every bug they passed through on the way (one they fixed in class isn't
    worth carrying forward). An issue is kept once MIN_STUDENTS_FOR_DISCUSSION
    students are stuck on it, same bar as the live dashboard's talking points.

    wrong_answer sub-clusters stay per task (outputs/code aren't comparable
    across exercises -- see this module's docstring) and carry the shared failing
    test as evidence. Other categories (NameError, syntax_error, ...) mean the
    same thing on any task, so those merge across the lecture, listing every task
    they left students stuck on."""
    items = []
    merged = {}  # (exec_verdict, error_type) -> item, for the non-wrong_answer categories
    for question in store.questions_for_lecture(lecture_id):
        rows = store.all_submissions(question["id"])
        solved = {r["student_name"] for r in rows if r.get("verdict") == "correct"}
        latest_id = {name: row["id"] for name, row in _latest_submission_per_student(question["id"]).items()}

        def stuck_in(group):
            return {r["student_name"] for r in group if r["student_name"] not in solved and latest_id.get(r["student_name"]) == r["id"]}

        by_key = defaultdict(list)
        for row in rows:
            by_key[(row.get("exec_verdict"), row.get("error_type"))].append(row)

        for (exec_verdict, error_type), members in by_key.items():
            if exec_verdict in (None, "pass"):
                continue
            if exec_verdict == "wrong_answer":
                groups = _group_wrong_answers(members, question.get("reference_solution") or "", question["id"])
                cases_by_group = [_shared_failing_cases(g) for g in groups]
                for gi, group in enumerate(groups):
                    stuck = stuck_in(group)
                    if len(stuck) < MIN_STUDENTS_FOR_DISCUSSION:
                        continue
                    students = {r["student_name"] for r in group}
                    items.append(
                        {
                            "exec_verdict": exec_verdict,
                            "error_type": None,
                            "task_titles": [question["title"]],
                            "students": len(students),
                            "stuck": len(stuck),
                            "example": _distinguishing_case(cases_by_group[gi], cases_by_group[:gi] + cases_by_group[gi + 1:]),
                            "raised": _is_raised(question["id"], exec_verdict, None, students),
                            "_group": group,
                        }
                    )
                continue
            stuck = stuck_in(members)
            if not stuck:
                continue
            item = merged.setdefault(
                (exec_verdict, error_type),
                {
                    "exec_verdict": exec_verdict,
                    "error_type": error_type,
                    "task_titles": [],
                    "students": 0,
                    "stuck": 0,
                    "example": None,
                    "raised": False,
                },
            )
            students = {r["student_name"] for r in members}
            item["task_titles"].append(question["title"])
            # Summed per task: the same student stuck on two tasks is two
            # (student, task) cases to revisit, not one.
            item["students"] += len(students)
            item["stuck"] += len(stuck)
            item["raised"] = item["raised"] or _is_raised(question["id"], exec_verdict, error_type, students)

    for item in merged.values():
        if item["stuck"] < MIN_STUDENTS_FOR_DISCUSSION:
            continue
        item["discussion_point"] = _generate_discussion_point(item["exec_verdict"], item["error_type"], item["stuck"])
        if item["discussion_point"]:
            items.append(item)

    # wrong_answer labels: the same Label call (and cache -- same groups, same
    # submission ids) the live dashboard used, so a lecture summarized right
    # after it ends reuses those labels instead of asking again.
    wrong = [i for i in items if "_group" in i]
    labels = _generate_subcluster_labels(
        [(i["_group"], store.get_question_row(i["_group"][0]["question_id"]).get("reference_solution"), i["students"]) for i in wrong],
        [i["raised"] for i in wrong],
    )
    for item, label in zip(wrong, labels):
        del item["_group"]
        item["discussion_point"] = label or hints.discussion_point_for_cluster("wrong_answer", None, item["stuck"])

    items.sort(key=lambda i: (i["stuck"], i["students"]), reverse=True)
    return items


def student_recap(lecture_id: int, student_name: str) -> dict:
    """"Attempted N of M tasks" + this student's own most-recent verdict per
    task -- the STATE 2 student recap. Personal only: no comparison to
    classmates or the class average anywhere in this return value (see the
    product decision against any ranking/leaderboard UI)."""
    results = []
    for question in store.questions_for_lecture(lecture_id):
        latest = _latest_submission_per_student(question["id"]).get(student_name)
        results.append(
            {
                "question_id": question["id"],
                "title": question["title"],
                "attempted": latest is not None,
                "verdict": latest["verdict"] if latest else None,
            }
        )
    return {
        "attempted": sum(1 for r in results if r["attempted"]),
        "total": len(results),
        "results": results,
    }


# A lecture with fewer students than this isn't ranked in lecture_review() --
# with two students, one bad attempt swings the solve rate by 50 points, which
# would put dev-test and tiny sessions at the top of "needs revisiting" for no
# real reason. They're still returned, flagged, so the page can list them apart.
MIN_STUDENTS_FOR_REVIEW = 3


def _most_common_wrong_output(rows: list):
    """For "wrong answer" -- which on its own says nothing about what went wrong --
    the most common concrete failure among `rows`: the first test each one failed,
    grouped by (input, what was printed). Returns {"stdin", "expected_stdout",
    "stdout", "students"} or None. Read from stored raw_test_results, no model."""
    counts = defaultdict(int)
    detail = {}
    for row in rows:
        try:
            results = json.loads(row.get("raw_test_results") or "[]")
        except (TypeError, ValueError):
            continue
        failing = next((r for r in results if isinstance(r, dict) and not r.get("passed")), None)
        if not failing:
            continue
        if "test_id" in failing:  # test-graded: the failing test and its message
            key = (failing.get("test_name") or "", failing.get("message") or "")
            counts[key] += 1
            detail[key] = {"stdin": "", "expected_stdout": "", "stdout": key[1], "test_name": key[0],
                           "message": key[1]}
            continue
        stdout = " ".join((failing.get("stdout") or "").split())
        key = (failing.get("stdin", ""), stdout)
        counts[key] += 1
        detail[key] = {"stdin": key[0], "expected_stdout": failing.get("expected_stdout", ""), "stdout": stdout}
    if not counts:
        return None
    key, n = max(counts.items(), key=lambda kv: kv[1])
    return {**detail[key], "students": n}


def lecture_review(include_archived: bool = False) -> list:
    """How each finished lecture went, worst first -- the history page's "Needs
    revisiting" view, for deciding what a review lecture should go back over.

    Per task: students is everyone who took part in the lecture -- the larger of
    how many joined and how many distinct students submitted to any of its tasks
    (lectures from before join tracking have no joins) -- the same number for
    every task, so a student who skipped a task counts as not having solved it. solved is the
    distinct students with at least one correct submission (best result, same as
    the dashboard's Class progress chart). top_issue is the most common way the
    *unsolved* students' latest submissions went wrong, by (exec_verdict,
    error_type), with the curated line for it (hints, no model call -- this
    runs over every past lecture on each page load).

    Per lecture: solve_rate is the mean of its tasks' solve rates, so one big
    task doesn't drown out the others. Aggregate only, no student names --
    same rule as the rest of the history view."""
    reviews = []
    for lecture in store.list_lectures(include_archived=include_archived):
        if not lecture["ended_at"]:
            continue  # still running -- nothing settled to review yet
        questions = store.questions_for_lecture(lecture["id"])
        latest_by_question = {q["id"]: _latest_submission_per_student(q["id"]) for q in questions}
        submitters = set().union(*latest_by_question.values()) if questions else set()
        students = max(store.joined_count(lecture["id"]), len(submitters))
        tasks = []
        for question in questions:
            latest = latest_by_question[question["id"]]
            solved_students = {
                row["student_name"] for row in store.all_submissions(question["id"]) if row.get("verdict") == "correct"
            }
            issue_rows = defaultdict(list)
            for name, row in latest.items():
                if name not in solved_students:
                    issue_rows[(row.get("exec_verdict"), row.get("error_type"))].append(row)
            top_issue = None
            if issue_rows:
                (exec_verdict, error_type), rows = max(issue_rows.items(), key=lambda kv: len(kv[1]))
                top_issue = {
                    "exec_verdict": exec_verdict,
                    "error_type": error_type,
                    "students": len(rows),
                    "discussion_point": _generate_discussion_point(exec_verdict, error_type, len(rows)),
                    "example": _most_common_wrong_output(rows) if exec_verdict == "wrong_answer" else None,
                }
            tasks.append(
                {
                    "question_id": question["id"],
                    "title": question["title"],
                    "students": students,
                    "submitted": len(latest),
                    "solved": len(solved_students),
                    "solve_rate": len(solved_students) / students if students else None,
                    "top_issue": top_issue,
                }
            )
        rated = [t["solve_rate"] for t in tasks if t["solve_rate"] is not None]
        reviews.append(
            {
                "lecture_id": lecture["id"],
                "display_label": lecture["display_label"],
                "started_at": lecture["started_at"],
                "archived": lecture["archived"],
                "students": students,
                "solve_rate": sum(rated) / len(rated) if rated else None,
                "enough_data": students >= MIN_STUDENTS_FOR_REVIEW and bool(rated),
                # Weakest first, so the page can show "what to go back over" at a glance.
                "tasks": sorted(tasks, key=lambda t: (t["solve_rate"] is None, t["solve_rate"] or 0)),
            }
        )
    reviews.sort(key=lambda r: (not r["enough_data"], r["solve_rate"] if r["solve_rate"] is not None else 1))
    return reviews
