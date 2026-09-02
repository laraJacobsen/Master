"""
Cheap aggregation over stored submissions: group by (exec_verdict, error_type)
-- the deterministic Judge0-derived taxonomy plus Claude's own error_type --
and rank clusters by submission count. This is the groupby fallback from the
aggregation-pipeline sketch: cheap enough to run live during a lecture, not
a semantic clustering/embedding pipeline.
"""

from collections import defaultdict

from backend import store


def cluster_submissions(question_id: str = None) -> list:
    """Returns clusters ranked by size (largest first), each:
      exec_verdict, error_type, count, example_submission_id, example_discussion_point
    """
    rows = store.all_submissions(question_id)

    clusters = defaultdict(list)
    for row in rows:
        key = (row.get("exec_verdict"), row.get("error_type"))
        clusters[key].append(row)

    result = []
    for (exec_verdict, error_type), members in clusters.items():
        example = members[0]  # all_submissions is already newest-first
        result.append(
            {
                "exec_verdict": exec_verdict,
                "error_type": error_type,
                "count": len(members),
                "example_submission_id": example["id"],
                "example_discussion_point": example.get("discussion_point"),
            }
        )

    result.sort(key=lambda c: c["count"], reverse=True)
    return result
