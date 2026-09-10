import { useState } from "react";

import type { HistoryPoint } from "../../lib/api";
import { money, percent } from "../../lib/format";

export type Metric = "margin" | "growth";

const LABELS: Record<Metric, string> = {
    margin: "FCF margin",
    growth: "Revenue growth",
};

/** Reported years for one measure. A single series, so no legend and one colour — the
 *  sign is carried by which side of the zero line a bar sits on, never by hue. */
export function HistoryChart({ points, metric }: { points: HistoryPoint[]; metric: Metric }) {
    const [hovered, setHovered] = useState<number | null>(null);

    const series = points
        .map((point) => ({ point, value: metric === "margin" ? point.fcf_margin : point.revenue_growth }))
        .filter((entry): entry is { point: HistoryPoint; value: number } => entry.value !== null);

    if (series.length === 0) {
        return (
            <p className="flex h-full items-center justify-center text-base text-overlay0">
                no reported years for this company yet
            </p>
        );
    }

    const values = series.map((entry) => entry.value);
    const top = Math.max(0, ...values);
    const bottom = Math.min(0, ...values);
    const span = top - bottom || 1;
    const zeroFromTop = (top / span) * 100;
    const active = series.find((entry) => entry.point.year === hovered) ?? null;

    return (
        <div className="flex h-full flex-col">
            <div className="flex min-h-0 flex-1 gap-3">
                <div className="flex w-16 shrink-0 flex-col justify-between pb-6 text-right text-sm font-mono tabular-nums text-overlay0">
                    <span>{percent(top, 0)}</span>
                    {bottom < 0 ? <span>{percent(bottom, 0)}</span> : <span>0%</span>}
                </div>

                <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
                    <div className="relative min-h-0 flex-1">
                        <div className="absolute inset-x-0 border-t border-surface1" style={{ top: `${zeroFromTop}%` }} />
                        <div className="absolute inset-0 flex items-stretch gap-[2px]">
                            {series.map(({ point, value }) => (
                                <button
                                    key={point.year}
                                    type="button"
                                    aria-label={`FY${point.year}: ${percent(value)}`}
                                    onMouseEnter={() => setHovered(point.year)}
                                    onMouseLeave={() => setHovered(null)}
                                    onFocus={() => setHovered(point.year)}
                                    onBlur={() => setHovered(null)}
                                    className="relative min-w-0 flex-1 cursor-default"
                                >
                                    <span
                                        className={`absolute left-1/2 w-full max-w-[4.5rem] -translate-x-1/2 bg-mauve transition-opacity ${
                                            value >= 0 ? "rounded-t-[4px]" : "rounded-b-[4px]"
                                        } ${hovered !== null && hovered !== point.year ? "opacity-45" : ""}`}
                                        style={
                                            value >= 0
                                                ? { bottom: `${100 - zeroFromTop}%`, height: `${(value / span) * 100}%` }
                                                : { top: `${zeroFromTop}%`, height: `${(-value / span) * 100}%` }
                                        }
                                    />
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="mt-2 flex h-4 gap-[2px] text-center text-sm font-mono tabular-nums text-overlay0">
                        {series.map(({ point }) => (
                            <span key={point.year} className="min-w-0 flex-1">
                                {`'${String(point.year).slice(2)}`}
                            </span>
                        ))}
                    </div>
                </div>
            </div>

            <div className="mt-4 flex h-[4.5rem] shrink-0 items-center rounded-md border border-surface0 bg-mantle px-4">
                {active ? (
                    <dl className="grid w-full grid-cols-4 gap-x-6 text-base">
                        <Cell label={`FY${active.point.year}`} value={LABELS[metric]} />
                        <Cell label={LABELS[metric]} value={percent(active.value, 1)} />
                        <Cell label="Revenue" value={money(active.point.revenue)} />
                        <Cell label="FCF" value={money(active.point.fcf)} />
                    </dl>
                ) : (
                    <p className="text-base text-overlay0">
                        {series.length} reported {series.length === 1 ? "year" : "years"} — hover one for its revenue and
                        cash flow
                    </p>
                )}
            </div>
        </div>
    );
}

function Cell({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <dt className="text-sm text-overlay0">{label}</dt>
            <dd className="font-medium font-mono tabular-nums text-subtext1">{value}</dd>
        </div>
    );
}
