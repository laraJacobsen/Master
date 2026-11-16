import { useId, useLayoutEffect, useRef, useState } from "react";
import { cx } from "../shared/cx";

// "Solved per lecture" on the history page: a smooth brand-coloured line over
// a light blue -> violet wash. Hover (or keyboard focus) shows a lecture's
// numbers; clicking selects it, which the page uses to open that lecture in
// the ranked list. Plain SVG -- no chart library for one small chart.

export interface TrendPoint {
  id: number;
  label: string;
  /** Short date under the x axis, e.g. "Oct 15". */
  date: string;
  /** Share of tasks solved, 0..1. */
  rate: number;
  /** Small secondary line in the tooltip (date, students, ...). */
  detail: string;
}

export interface TrendChartProps {
  points: TrendPoint[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  className?: string;
}

const HEIGHT = 220;
const PAD = { top: 20, right: 44, bottom: 8, left: 14 };
const GRID = [0.25, 0.5, 0.75, 1];
const MIN_LABEL_GAP = 52; // px between x-axis dates before we start skipping some

interface XY {
  x: number;
  y: number;
}

// Monotone cubic (Fritsch-Carlson): smooth, but never bends above 100% or
// below 0% between points the way a plain spline can.
function monotonePath(pts: XY[]): string {
  const n = pts.length;
  if (n === 0) return "";
  if (n === 1) return `M${pts[0].x},${pts[0].y}`;
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) slope.push((pts[i + 1].y - pts[i].y) / (pts[i + 1].x - pts[i].x));
  const tan: number[] = [slope[0]];
  for (let i = 1; i < n - 1; i++) tan.push(slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2);
  tan.push(slope[n - 2]);
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      tan[i] = 0;
      tan[i + 1] = 0;
      continue;
    }
    const a = tan[i] / slope[i];
    const b = tan[i + 1] / slope[i];
    const s = a * a + b * b;
    if (s > 9) {
      const k = 3 / Math.sqrt(s);
      tan[i] = k * a * slope[i];
      tan[i + 1] = k * b * slope[i];
    }
  }
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 0; i < n - 1; i++) {
    const dx = (pts[i + 1].x - pts[i].x) / 3;
    d += ` C${pts[i].x + dx},${pts[i].y + tan[i] * dx} ${pts[i + 1].x - dx},${pts[i + 1].y - tan[i + 1] * dx} ${pts[i + 1].x},${pts[i + 1].y}`;
  }
  return d;
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function TrendChart({ points, selectedId, onSelect, className }: TrendChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hoverId, setHoverId] = useState<number | null>(null);
  const gradId = useId();

  // Measure before first paint (so the chart never flashes empty), then keep
  // following the container's width.
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    setWidth(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const bottom = PAD.top + plotH;
  const step = points.length > 1 ? plotW / (points.length - 1) : 0;
  const xy: XY[] = points.map((p, i) => ({
    x: points.length > 1 ? PAD.left + i * step : PAD.left + plotW / 2,
    y: PAD.top + (1 - Math.max(0, Math.min(1, p.rate))) * plotH,
  }));
  const line = monotonePath(xy);
  const area = xy.length > 1 ? `${line} L${xy[xy.length - 1].x},${bottom} L${xy[0].x},${bottom} Z` : "";

  const activeId = hoverId ?? selectedId;
  const activeIdx = points.findIndex((p) => p.id === activeId);
  const active = activeIdx >= 0 ? points[activeIdx] : null;
  const labelEvery = step > 0 ? Math.max(1, Math.ceil(MIN_LABEL_GAP / step)) : 1;

  return (
    <div className={className}>
      <div ref={wrapRef} className="relative select-none" style={{ height: HEIGHT }}>
        {width > 0 && (
          <svg width={width} height={HEIGHT} className="absolute inset-0 overflow-visible" aria-hidden="true">
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" style={{ stopColor: "var(--color-brand-500)", stopOpacity: 0.26 }} />
                <stop offset="55%" style={{ stopColor: "var(--color-violet-400)", stopOpacity: 0.1 }} />
                <stop offset="100%" style={{ stopColor: "var(--color-violet-300)", stopOpacity: 0 }} />
              </linearGradient>
            </defs>

            {GRID.map((g) => {
              const y = PAD.top + (1 - g) * plotH;
              return (
                <line
                  key={g}
                  x1={PAD.left}
                  x2={PAD.left + plotW}
                  y1={y}
                  y2={y}
                  className="stroke-zinc-200"
                  strokeDasharray="3 4"
                />
              );
            })}
            <line x1={PAD.left} x2={PAD.left + plotW} y1={bottom} y2={bottom} className="stroke-zinc-200" />
            {[0, 0.5, 1].map((g) => (
              <text
                key={g}
                x={width - 4}
                y={PAD.top + (1 - g) * plotH}
                dy="0.35em"
                textAnchor="end"
                className="fill-zinc-400 font-mono text-[11px]"
              >
                {pct(g)}
              </text>
            ))}

            {area && <path d={area} fill={`url(#${CSS.escape(gradId)})`} />}

            {active && (
              <line
                x1={xy[activeIdx].x}
                x2={xy[activeIdx].x}
                y1={xy[activeIdx].y}
                y2={bottom}
                className="stroke-brand-300"
                strokeDasharray="3 3"
              />
            )}

            <path
              d={line}
              fill="none"
              className="stroke-brand-500"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {xy.map((pt, i) => {
              const p = points[i];
              const isActive = p.id === activeId;
              const isSelected = p.id === selectedId;
              return (
                <g key={p.id}>
                  {isActive && <circle cx={pt.x} cy={pt.y} r={13} className="fill-brand-500/15" />}
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r={isActive || isSelected ? 6 : 3.5}
                    strokeWidth={isActive || isSelected ? 2.5 : 2}
                    className={cx(
                      "transition-[r] duration-150",
                      isActive || isSelected ? "fill-brand-500 stroke-white" : "fill-white stroke-brand-500",
                    )}
                  />
                </g>
              );
            })}
          </svg>
        )}

        {/* One invisible column per lecture: the hover / click / keyboard target. */}
        {width > 0 &&
          points.map((p, i) => {
            const half = points.length > 1 ? step / 2 : plotW / 2;
            const left = Math.max(0, xy[i].x - half);
            const right = Math.min(width, xy[i].x + half);
            return (
              <button
                key={p.id}
                type="button"
                className="absolute top-0 rounded-md focus-visible:bg-brand-500/5 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500"
                style={{ left, width: right - left, height: HEIGHT }}
                aria-label={`${p.label}, ${p.detail}: ${pct(p.rate)} solved. Show its tasks.`}
                aria-pressed={p.id === selectedId}
                onMouseEnter={() => setHoverId(p.id)}
                onMouseLeave={() => setHoverId(null)}
                onFocus={() => setHoverId(p.id)}
                onBlur={() => setHoverId(null)}
                onClick={() => onSelect(p.id)}
              />
            );
          })}

        {active && (
          <div
            className="pointer-events-none absolute z-10 w-48 animate-fade-in rounded-lg bg-white px-3 py-2.5 shadow-card ring-1 ring-zinc-950/5"
            style={{
              left: Math.min(Math.max(xy[activeIdx].x, 96), width - 96),
              top: xy[activeIdx].y,
              transform: "translate(-50%, calc(-100% - 16px))",
            }}
          >
            <div className="truncate text-[13px] font-semibold text-zinc-900">{active.label}</div>
            <div className="truncate text-xs text-zinc-500">{active.detail}</div>
            <div className="mt-1.5 flex items-baseline gap-1.5">
              <span className="font-mono text-lg font-semibold tracking-tight text-brand-600 tabular-nums">
                {pct(active.rate)}
              </span>
              <span className="text-xs text-zinc-500">solved</span>
            </div>
          </div>
        )}
      </div>

      {/* x-axis dates */}
      <div className="relative mt-2 h-4" aria-hidden="true">
        {width > 0 &&
          points.map((p, i) => {
            const isActive = p.id === activeId;
            if (!isActive && i % labelEvery !== 0) return null;
            return (
              <span
                key={p.id}
                className={cx(
                  "absolute top-0 -translate-x-1/2 font-mono text-[11px] whitespace-nowrap",
                  isActive ? "font-semibold text-brand-700" : "text-zinc-500",
                )}
                style={{ left: xy[i].x }}
              >
                {p.date}
              </span>
            );
          })}
      </div>
    </div>
  );
}
