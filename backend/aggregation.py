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
     representative *canonicalized* snippets (never full original source, never real
     names) from that one sub-cluster, and explicitly told to describe only the pattern
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

# Keeps operators/brackets/literals as features instead of dropping them -- see
# the 2026-09-16 follow-up in the module docstring.
_TOKEN_PATTERN = r"\S+"

# Retuned 2026-09-16 -- see module docstring for the measured distance gap this
# sits in. Still an unvalidated first guess, not a tuned constant.
WRONG_ANSWER_SUBCLUSTER_DISTANCE = 0.05

# Below this many canonicalized tokens there's nothing real to describe a pattern
# from -- see the 2026-09-16 fabrication finding in the module docstring.
_MIN_TOKENS_FOR_PATTERN_CALL = 4

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
    "2-3 anonymized code snippets -- every variable, function, and parameter name has "
    "been replaced with VAR1, VAR2, etc. in order of first appearance in each snippet, so "
    "you cannot know what anything is actually called or what the exercise even is.\n"
    "Describe, in ONE short factual sentence, only the pattern that is visibly shared "
    "across ALL of the given snippets -- e.g. a specific operator, an off-by-one style "
    "adjustment, a missing or extra call, a particular loop or condition shape. Do not "
    "name or guess a specific bug, variable purpose, or root cause unless it is literally "
    "visible in every snippet shown. If the snippets don't share an obvious concrete "
    "pattern, say plainly that they don't rather than inventing one.\n"
    "Write in third person, for the lecturer, about the students -- never 'you' or "
    "'your'.\n"
    "Respond with ONLY a JSON object with exactly this key:\n"
    "  \"discussion_point\": the one-sentence factual note\n"
    "No other keys, no markdown fences, no explanation outside the JSON object."
)

_SECOND_PERSON_RE = re.compile(r"\byou\b|\byour\b|\byou're\b|\byours\b", re.IGNORECASE)

_discussion_cache = {}  # (question_id, exec_verdict, error_type) -> str or None
_subcluster_discussion_cache = {}  # frozenset(submission ids) -> str or None


def _canonicalize(source_code: str) -> str:
    """Renames every non-keyword identifier to VAR1/VAR2/... in order of first
    appearance, so two students' differently-named variables/functions don't make
    structurally-identical code look different for similarity comparison. Falls back
    to the raw source if it can't be tokenized -- defensive only, since wrong_answer
    by definition means the code ran without crashing, so a tokenize failure here
    would be unexpected.
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
            elif tok.type in (
                tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
                tokenize.ENCODING, tokenize.ENDMARKER, tokenize.COMMENT,
            ):
                continue
            else:
                out.append(tok.string)
        return " ".join(out)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source_code


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
    """Up to max_n canonicalized snippets from distinct students in this group, for
    the Ollama call -- never the full group (keeps the call cheap and the model from
    over-indexing on one student's resubmissions)."""
    seen_students = set()
    picked = []
    for row in group:
        if row["student_name"] in seen_students:
            continue
        seen_students.add(row["student_name"])
        picked.append(_canonicalize(row["source_code"]))
        if len(picked) >= max_n:
            break
    return picked


def _idun_available() -> bool:
    """No cheap unauthenticated health check like Ollama's /api/tags exists on the
    IDUN gateway, so this just checks a key is configured -- an actual bad key or
    unreachable network (off NTNU network/VPN) still surfaces as a request failure,
    caught by _call_idun_subcluster_pattern's caller same as any other failure mode."""
    return bool(IDUN_API_KEY)


def _call_idun_subcluster_pattern(snippets: list) -> str:
    """One JSON-mode call given 2-3 canonicalized snippets from one similarity
    sub-cluster, via IDUN's OpenAI-compatible chat-completions endpoint. Raises on
    network failure, invalid JSON, a response that doesn't satisfy the schema, or
    second-person phrasing -- caller retries/falls back to the generic wrong_answer
    line."""
    prompt = "Snippets:\n\n" + "\n\n---\n\n".join(snippets) + (
        "\n\nRespond with the JSON object described in the system prompt."
    )
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


def _subcluster_discussion_point(group: list, student_count: int):
    if student_count < MIN_STUDENTS_FOR_DISCUSSION:
        return None

    cache_key = frozenset(row["id"] for row in group)
    if cache_key in _subcluster_discussion_cache:
        return _subcluster_discussion_cache[cache_key]

    fallback = hints.discussion_point_for_cluster("wrong_answer", None, student_count)
    result = fallback
    snippets = _representative_snippets(group)
    trivial = any(len(s.split()) < _MIN_TOKENS_FOR_PATTERN_CALL for s in snippets)
    if len(snippets) >= 2 and not trivial and _idun_available():
        t0 = time.monotonic()
        for _attempt in (1, 2):
            try:
                result = _call_idun_subcluster_pattern(snippets)
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


def _wrong_answer_subclusters(members: list) -> list:
    """Sub-clusters one exec_verdict=="wrong_answer" bucket by divergence from the
    exercise's own reference solution, scoped per question_id first -- comparing
    code across different exercises would be meaningless, and each question_id has
    its own reference_solution to diff against. Returns cluster dicts in the same
    shape cluster_submissions() uses for every other category."""
    result = []
    by_question = defaultdict(list)
    for row in members:
        by_question[row["question_id"]].append(row)

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
        for group in groups:
            student_count = len({m["student_name"] for m in group})
            example = group[0]
            result.append(
                {
                    "exec_verdict": "wrong_answer",
                    "error_type": None,
                    "count": student_count,
                    "example_submission_id": example["id"],
                    "submission_ids": _distinct_student_submission_ids(group),
                    "discussion_point": _subcluster_discussion_point(group, student_count),
                }
            )
    return result


def _generate_discussion_point(exec_verdict: str, error_type: str, student_count: int):
    try:
        return hints.discussion_point_for_cluster(exec_verdict, error_type, student_count)
    except Exception:
        return None  # no recognized family -- nothing safe to say


def _cached_discussion_point(question_id, exec_verdict, error_type, student_count):
    if student_count < MIN_STUDENTS_FOR_DISCUSSION:
        return None
    cache_key = (question_id, exec_verdict, error_type)
    if cache_key not in _discussion_cache:
        _discussion_cache[cache_key] = _generate_discussion_point(
            exec_verdict, error_type, student_count
        )
    return _discussion_cache[cache_key]


def cluster_submissions(question_id: str = None) -> list:
    """Returns clusters ranked by distinct-student count (largest first), each:
      exec_verdict, error_type, count (distinct students), example_submission_id,
      submission_ids (one per distinct student, for "view all"),
      discussion_point (None unless enough distinct students hit this cluster)

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
        student_count = len({m["student_name"] for m in members})
        result.append(
            {
                "exec_verdict": exec_verdict,
                "error_type": error_type,
                "count": student_count,
                "example_submission_id": example["id"],
                "submission_ids": _distinct_student_submission_ids(members),
                "discussion_point": _cached_discussion_point(
                    example["question_id"], exec_verdict, error_type, student_count
                ),
            }
        )

    result.sort(key=lambda c: c["count"], reverse=True)
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
