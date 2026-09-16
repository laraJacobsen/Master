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
  3. Sub-clusters that clear MIN_STUDENTS_FOR_DISCUSSION get a live Ollama call, but a
     narrowly scoped one: given 2-3 representative *canonicalized* snippets (never full
     original source, never real names) from that one sub-cluster, and explicitly told to
     describe only the pattern visible in ALL of them, never invent a cause true of less
     than all. This is a different risk shape than the lecturer discussion-point call this
     project removed twice before (see pedagogical-feedback-design-decision.md) -- that one
     asked a model to explain a cause from a bare label with no evidence, which is exactly
     what it couldn't do reliably. Here the model is shown real (anonymized) evidence and
     asked to describe only what's shared across it, with a hard fallback to the generic
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
"""

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

# First guess, not yet tuned against labeled data -- see module docstring.
WRONG_ANSWER_SUBCLUSTER_DISTANCE = 0.4

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

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


def _cluster_by_similarity(rows: list) -> list:
    """Groups submissions by code similarity: canonicalize identifiers, TF-IDF the
    result, agglomerative-cluster on cosine distance with no fixed k. Returns a list
    of groups (each a list of rows); a group of size 1 is a natural outlier, not an
    error."""
    if len(rows) < 2:
        return [[r] for r in rows]

    canon = [_canonicalize(r["source_code"]) for r in rows]
    try:
        matrix = TfidfVectorizer().fit_transform(canon)
    except ValueError:
        return [[r] for r in rows]  # empty vocabulary -- nothing to compare on
    if matrix.shape[1] == 0:
        return [[r] for r in rows]

    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=WRONG_ANSWER_SUBCLUSTER_DISTANCE,
        metric="cosine",
        linkage="average",
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


def _ollama_available() -> bool:
    if not OLLAMA_MODEL:
        return False
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        available = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return False
    return OLLAMA_MODEL in available


def _call_ollama_subcluster_pattern(snippets: list) -> str:
    """One JSON-mode call given 2-3 canonicalized snippets from one similarity
    sub-cluster. Raises on network failure, invalid JSON, a response that doesn't
    satisfy the schema, or second-person phrasing -- caller retries/falls back to
    the generic wrong_answer line."""
    prompt = "Snippets:\n\n" + "\n\n---\n\n".join(snippets) + (
        "\n\nRespond with the JSON object described in the system prompt."
    )
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": WRONG_ANSWER_SUBCLUSTER_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["message"]["content"])
    point = parsed.get("discussion_point")
    if not isinstance(point, str) or not point.strip():
        raise ValueError(f"missing discussion_point in Ollama response: {parsed!r}")
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
    if len(snippets) >= 2 and _ollama_available():
        t0 = time.monotonic()
        for _attempt in (1, 2):
            try:
                result = _call_ollama_subcluster_pattern(snippets)
                break
            except Exception:
                continue
        logger.info(
            "wrong_answer sub-cluster Ollama call: %d snippets, %.3fs, used_model=%s",
            len(snippets), time.monotonic() - t0, result is not fallback,
        )

    _subcluster_discussion_cache[cache_key] = result
    return result


def _wrong_answer_subclusters(members: list) -> list:
    """Sub-clusters one exec_verdict=="wrong_answer" bucket by code similarity, scoped
    per question_id first -- comparing code across different exercises would be
    meaningless. Returns cluster dicts in the same shape cluster_submissions() uses
    for every other category."""
    result = []
    by_question = defaultdict(list)
    for row in members:
        by_question[row["question_id"]].append(row)

    for question_id, rows in by_question.items():
        t0 = time.monotonic()
        groups = _cluster_by_similarity(rows)
        logger.info(
            "wrong_answer canonicalize+cluster: question=%s, %d submissions -> %d groups, %.3fs",
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
                "discussion_point": _cached_discussion_point(
                    example["question_id"], exec_verdict, error_type, student_count
                ),
            }
        )

    result.sort(key=lambda c: c["count"], reverse=True)
    return result
