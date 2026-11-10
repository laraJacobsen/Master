import type { ClusterRow } from "../shared/types";

export function issueTag(c: ClusterRow): string {
  if (c.exec_verdict === "rejected") return "Rejected";
  if (c.exec_verdict === "pass") return "Passing";
  const verdict = (c.exec_verdict || "unknown").replace(/_/g, " ");
  const label = verdict.charAt(0).toUpperCase() + verdict.slice(1);
  return c.error_type && c.error_type !== "none" ? `${label} · ${c.error_type}` : label;
}

// Stable across polls even as students join a cluster (its submission_ids
// and example_submission_id both change then), so an open issue doesn't
// snap shut on the next refresh. Sub-clusters of one verdict are told apart
// by their discussion point, or by their earliest submission when there's
// no point yet (a single-student sub-cluster).
export function issueKey(c: ClusterRow): string {
  const ids = c.submission_ids && c.submission_ids.length ? c.submission_ids : [c.example_submission_id];
  return `${c.exec_verdict}|${c.error_type ?? ""}|${c.discussion_point ?? Math.min(...ids)}`;
}

export function clusterIds(c: ClusterRow): number[] {
  return c.submission_ids && c.submission_ids.length ? c.submission_ids : [c.example_submission_id];
}
