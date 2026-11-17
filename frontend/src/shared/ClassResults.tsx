import { CATEGORY_FILL, CATEGORY_LABEL, CATEGORY_ORDER, categoryCounts } from "./categories";
import { cx } from "./cx";

export interface ClassResultsProps {
  // Each student's best attempt's exec_verdict -- what /api/lecture/status
  // sends as shown_results. No names.
  bestExecVerdicts: string[];
  // The projector reads from the back of the room.
  size?: "md" | "lg";
  className?: string;
}

// The lecturer's "Students by outcome" as the class sees it once the lecturer
// shows it: the verdict bar and a count per outcome, same categories and
// colours as the live dashboard.
export function ClassResults({ bestExecVerdicts, size = "md", className }: ClassResultsProps) {
  const counts = categoryCounts(bestExecVerdicts.map((v) => ({ exec_verdict: v })));
  const shown = CATEGORY_ORDER.filter((c) => counts.get(c));
  const total = bestExecVerdicts.length;
  const lg = size === "lg";
  return (
    <div className={className}>
      <div
        className={cx("flex gap-0.5 overflow-hidden rounded-md", lg ? "h-12" : "h-7")}
        role="img"
        aria-label={total ? shown.map((c) => `${counts.get(c)} ${CATEGORY_LABEL[c]}`).join(", ") : "No submissions"}
      >
        {total === 0 ? (
          <span className="flex-1 rounded-[3px] bg-zinc-100" />
        ) : (
          shown.map((c) => (
            <span
              key={c}
              className={cx("min-w-1 basis-0 rounded-[3px] transition-[flex-grow] duration-500", CATEGORY_FILL[c])}
              style={{ flexGrow: counts.get(c) }}
            />
          ))
        )}
      </div>
      {total > 0 && (
        <ul className={cx("flex flex-wrap text-zinc-600", lg ? "mt-5 gap-x-10 gap-y-2 text-2xl" : "mt-4 gap-x-5 gap-y-1.5 text-sm")}>
          {shown.map((c) => {
            const n = counts.get(c) ?? 0;
            return (
              <li key={c} className={cx("flex items-center", lg ? "gap-3" : "gap-1.5")}>
                <span className={cx("rounded-[3px]", lg ? "size-5" : "size-3", CATEGORY_FILL[c])} aria-hidden="true" />
                <span className="font-mono font-semibold text-zinc-950 tabular-nums">{n}</span>
                {CATEGORY_LABEL[c]}
                <span className="font-mono text-zinc-400 tabular-nums">{Math.round((n / total) * 100)}%</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
