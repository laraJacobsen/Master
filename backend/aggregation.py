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
     VARn form until 2026-10-13, see the entry at the end) from that one sub-cluster, and explicitly told to describe only the pattern
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

2026-09-16 finding, first real-corpus run (feedback-research/corpus.py's and
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
subcluster_ground_truth_sample.csv -- 29 real wrong_answer submissions across 3
exercises, hand-labeled into bug groups -- and feedback-research/run_tfidf_baseline.py/
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
differs. See feedback-research/run_diff_baseline.py for the full threshold-sweep results this
was chosen from (diff-against-reference stays well above the TF-IDF baseline across
0.02-0.30, not just at 0.05).

This does NOT close every gap: feedback-research/double-it-shape-vs-behavior-limitation-2026-09-21.md
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
discussion-point spot-check (feedback-research/real_discussion_point_sample_2026-09-21_round3.csv)
rated all 16 rows lecturer-facing, but 9 only partially grounded -- every one of them because
_canonicalize() renames builtins and methods along with the students' own names, so the model
could only describe a missing .replace(" ", "") as "the subsequent method call that takes the
two string literals". The Label call now gets each snippet and the reference solution as written
by the student, minus comments (_strip_comments()). Clustering is untouched: it still diffs
canonicalized code, which is where name-independence actually matters. The VARn/STMT_BREAK leak
backstop added in round 3 was removed along with the placeholders it guarded against.
"""

import difflib
import io
import json
import keyword
import logging
import os
import re
import time
import tokenize
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from backend import hints, store

# Nothing else in this project configures logging -- without this, the per-stage
# latency numbers below (the actual research question: is this fast enough to run
# live in a lecture) would silently go nowhere.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_STUDENTS_FOR_DISCUSSION = 2

# Issues the lecturer chose to show to the students on the live dashboard -- see
# raise_issue(). A raised issue gets a discussion point even below
# MIN_STUDENTS_FOR_DISCUSSION, sorts to the top, and its example is sent to the
# students' waiting screen (shown_examples()). Keyed by (question_id,
# exec_verdict, error_type, frozenset(student names in the issue when it was
# raised)), so an issue stays raised as more students land in it; the value is
# the submission id shown to students, in the order raised. In-memory, same as
# the discussion-point caches below: a restart forgets them.
_raised_issues = {}

# Keeps operators/brackets/literals as features instead of dropping them -- see
# the 2026-09-16 follow-up in the module docstring.
_TOKEN_PATTERN = r"\S+"

# Retuned 2026-09-16 -- see module docstring for the measured distance gap this
# sits in. Still an unvalidated first guess, not a tuned constant.
WRONG_ANSWER_SUBCLUSTER_DISTANCE = 0.05

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

WRONG_ANSWER_SUBCLUSTER_PROMPT = (
    "You are writing a short, factual note for a lecturer's own dashboard about a group "
    "of students whose code produced the wrong output on the same exercise. You are given "
    "1-3 of those students' code snippets (comments removed). Different students may use "
    "different variable names for the same thing. You may also be given the exercise's own "
    "reference (correct) solution -- it is for context only, never one of the snippets to "
    "describe.\n"
    "Describe, in ONE short factual sentence, only the pattern that is visibly shared "
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
    "Respond with ONLY a JSON object with exactly this key:\n"
    "  \"discussion_point\": the one-sentence factual note\n"
    "No other keys, no markdown fences, no explanation outside the JSON object."
)

_SECOND_PERSON_RE = re.compile(r"\byou\b|\byour\b|\byou're\b|\byours\b", re.IGNORECASE)

_discussion_cache = {}  # (question_id, exec_verdict, error_type) -> str or None
_subcluster_discussion_cache = {}  # frozenset(submission ids) -> str or None

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
    (see _call_idun_subcluster_pattern's docstring for why that's no longer the
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


def _representative_snippets(group: list, max_n: int = 3) -> list:
    """Up to max_n comment-stripped snippets (_strip_comments()) from distinct
    students in this group, for the Label call -- never the full group (keeps the
    call cheap and the model from over-indexing on one student's resubmissions)."""
    seen_students = set()
    picked = []
    for row in group:
        if row["student_name"] in seen_students:
            continue
        seen_students.add(row["student_name"])
        picked.append(_strip_comments(row["source_code"]))
        if len(picked) >= max_n:
            break
    return picked


def _idun_available() -> bool:
    """No cheap unauthenticated health check like Ollama's /api/tags exists on the
    IDUN gateway, so this just checks a key is configured -- an actual bad key or
    unreachable network (off NTNU network/VPN) still surfaces as a request failure,
    caught by _call_idun_subcluster_pattern's caller same as any other failure mode."""
    return bool(IDUN_API_KEY)


def _call_idun_subcluster_pattern(snippets: list, reference_solution: str = None) -> str:
    """One JSON-mode call given 2-3 comment-stripped snippets from one similarity
    sub-cluster, via IDUN's OpenAI-compatible chat-completions endpoint. Raises on
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
    inherited from reusing the clustering input. Student names are still never sent."""
    parts = []
    if reference_solution:
        parts.append(
            "Reference (correct) solution -- for context only, not one of the "
            "snippets to describe:\n\n" + reference_solution
        )
    parts.append("Snippets:\n\n" + "\n\n---\n\n".join(snippets))
    prompt = "\n\n".join(parts) + "\n\nRespond with the JSON object described in the system prompt."
    resp = requests.post(
        f"{IDUN_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {IDUN_API_KEY}"},
        json={
            "model": IDUN_MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": WRONG_ANSWER_SUBCLUSTER_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    point = parsed.get("discussion_point")
    if not isinstance(point, str) or not point.strip():
        raise ValueError(f"missing discussion_point in IDUN response: {parsed!r}")
    point = point.strip()
    if _SECOND_PERSON_RE.search(point):
        raise ValueError(f"discussion_point addressed the student, not the lecturer: {point!r}")
    return point


def _subcluster_discussion_point(group: list, reference_solution: str, student_count: int, raised: bool = False):
    """`reference_solution` -- the exercise's raw (not yet canonicalized) reference
    solution, or None/empty if unavailable -- is comment-stripped here and passed as
    context to the IDUN call (see _call_idun_subcluster_pattern's docstring for
    why). None is a legitimate value, not an error: it just means the call falls
    back to the pre-2026-09-21 behavior of describing the snippets with no
    reference-relative context.

    `raised` -- the lecturer flagged this issue (see raise_issue()) -- lifts the
    MIN_STUDENTS_FOR_DISCUSSION gate, so a one-student sub-cluster is labeled
    from its single snippet. Single-snippet labels haven't been through a
    spot-check round yet; every rated round so far had 2-3 snippets per row."""
    if student_count < MIN_STUDENTS_FOR_DISCUSSION and not raised:
        return None

    cache_key = frozenset(row["id"] for row in group)
    if cache_key in _subcluster_discussion_cache:
        return _subcluster_discussion_cache[cache_key]

    fallback = hints.discussion_point_for_cluster("wrong_answer", None, student_count)
    result = fallback
    snippets = _representative_snippets(group)
    reference = _strip_comments(reference_solution) if reference_solution else None
    # Token count measured on the canonicalized form, same as before the 2026-10-13
    # switch to showing real code -- this is a "too little code to describe" gate,
    # independent of what the model is shown.
    trivial = any(len(_canonicalize(s).split()) < _MIN_TOKENS_FOR_PATTERN_CALL for s in snippets)
    if snippets and not trivial and _idun_available():
        t0 = time.monotonic()
        for _attempt in (1, 2):
            try:
                result = _call_idun_subcluster_pattern(snippets, reference)
                break
            except Exception:
                continue
        logger.info(
            "wrong_answer sub-cluster IDUN call: %d snippets, %.3fs, used_model=%s",
            len(snippets), time.monotonic() - t0, result is not fallback,
        )

    _subcluster_discussion_cache[cache_key] = result
    return result


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
    """Sub-clusters one exec_verdict=="wrong_answer" bucket by divergence from the
    exercise's own reference solution, scoped per question_id first -- comparing
    code across different exercises would be meaningless, and each question_id has
    its own reference_solution to diff against. Returns cluster dicts in the same
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
            t0 = time.monotonic()
            groups = _cluster_by_similarity(rows, reference_solution)
            logger.info(
                "wrong_answer diff+cluster: question=%s, %d submissions -> %d groups, %.3fs",
                question_id, len(rows), len(groups), time.monotonic() - t0,
            )
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
            }
        )
    return result


def _generate_discussion_point(exec_verdict: str, error_type: str, student_count: int):
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
        (q, v, e) == (question_id, exec_verdict, error_type) and flagged & students
        for q, v, e, flagged in _raised_issues
    )


def raise_issue(question_id: str, exec_verdict: str, error_type, submission_ids: list, raised: bool) -> None:
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
    shares a student with it. Raises ValueError if none of the ids exist."""
    students = set()
    for sub_id in submission_ids:
        row = store.get_submission(sub_id)
        if row:
            students.add(row["student_name"])
    if not students:
        raise ValueError(f"no submissions found for ids {submission_ids!r}")
    if raised:
        _raised_issues[(question_id, exec_verdict, error_type, frozenset(students))] = submission_ids[0]
    else:
        for entry in list(_raised_issues):
            if entry[:3] == (question_id, exec_verdict, error_type) and entry[3] & students:
                del _raised_issues[entry]


def shown_examples(question_id: str) -> list:
    """The examples the lecturer raised for this question, in the order raised, as
    the students see them: code with comments stripped (the one free-text field
    in a submission, see _strip_comments()) and the first test it failed. No
    student name, no discussion point -- see raise_issue()."""
    examples = []
    for (q, _v, _e, _students), sub_id in _raised_issues.items():
        if q != question_id:
            continue
        row = store.get_submission(sub_id)
        if not row:
            continue
        results = json.loads(row.get("raw_test_results") or "[]")
        failing = next((r for r in results if not r.get("passed")), None)
        examples.append(
            {
                "source_code": _strip_comments(row["source_code"]),
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
        )
    return examples


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


def carry_forward_discussion_points(lecture_id: int) -> list:
    """Issues that cleared the discussion threshold on 2+ distinct tasks in
    this lecture -- worth raising again next time rather than treated as
    resolved. Coarse (exec_verdict, error_type) grouping only, same as
    cluster_submissions() uses for every category except wrong_answer:
    wrong_answer's code-similarity sub-clustering is inherently per-question
    (comparing code across different exercises is meaningless -- see this
    module's docstring), so it wouldn't make sense to carry a specific bug
    *shape* forward across tasks. This only asks "did wrong_answer itself
    recur," not "did the same bug recur.\""""
    occurrences_by_signature = defaultdict(list)  # (exec_verdict, error_type) -> [(question, student_count), ...]
    for question in store.questions_for_lecture(lecture_id):
        students_by_signature = defaultdict(set)
        for row in store.all_submissions(question["id"]):
            key = (row.get("exec_verdict"), row.get("error_type"))
            students_by_signature[key].add(row["student_name"])
        for key, students in students_by_signature.items():
            if len(students) >= MIN_STUDENTS_FOR_DISCUSSION:
                occurrences_by_signature[key].append((question, len(students)))

    result = []
    for (exec_verdict, error_type), occurrences in occurrences_by_signature.items():
        if len(occurrences) < 2:
            continue  # only on one task this lecture -- not a carry-forward pattern
        total_students = sum(count for _, count in occurrences)
        point = _generate_discussion_point(exec_verdict, error_type, total_students)
        if not point:
            continue  # unrecognized family -- nothing safe to say, same rule as the live dashboard
        result.append(
            {
                "exec_verdict": exec_verdict,
                "error_type": error_type,
                "task_titles": [q["title"] for q, _ in occurrences],
                "discussion_point": point,
            }
        )

    result.sort(key=lambda c: len(c["task_titles"]), reverse=True)
    return result


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
