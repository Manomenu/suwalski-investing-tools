import { useState } from "react";

import type { YearProjection } from "../../lib/api";
import { money, percent } from "../../lib/format";

/** Free cash flow per projected year. Two categories — the years you pinned and the years
 *  the solver filled in — so identity is carried by a legend plus the hover panel, never
 *  by colour alone. Palette: Catppuccin blue/peach, validated against the #1e1e2e surface. */
export function ProjectionChart({ years }: { years: YearProjection[] }) {
    const [hovered, setHovered] = useState<number | null>(null);
    const max = Math.max(...years.map((year) => year.fcf), 0);
    const active = years.find((year) => year.year === hovered) ?? null;

    return (
        <div className="flex h-full min-w-0 flex-col">
            <div className="flex min-h-0 flex-1 gap-3">
                <div className="flex w-16 shrink-0 flex-col justify-between pb-6 text-right text-sm font-mono tabular-nums text-overlay0">
                    <span>{money(max)}</span>
                    <span>{money(max / 2)}</span>
                    <span>0</span>
                </div>

                <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
                    {[0, 50].map((offset) => (
                        <div
                            key={offset}
                            className="absolute inset-x-0 border-t border-surface0"
                            style={{ top: `${offset}%` }}
                        />
                    ))}
                    <div className="absolute inset-x-0 bottom-0 border-t border-surface1" />
                    <div className="relative flex min-h-0 flex-1 items-end gap-[2px]">
                        {years.map((year) => (
                            <button
                                key={year.year}
                                type="button"
                                aria-label={`Year ${year.year}: FCF ${money(year.fcf)}`}
                                onMouseEnter={() => setHovered(year.year)}
                                onMouseLeave={() => setHovered(null)}
                                onFocus={() => setHovered(year.year)}
                                onBlur={() => setHovered(null)}
                                className="group flex h-full min-w-0 flex-1 cursor-default items-end justify-center"
                            >
                                <span
                                    className={`w-full max-w-[4.5rem] rounded-t-[4px] transition-opacity ${
                                        year.source === "input" ? "bg-blue" : "bg-peach"
                                    } ${hovered !== null && hovered !== year.year ? "opacity-45" : ""}`}
                                    style={{ height: `${max > 0 ? (year.fcf / max) * 100 : 0}%` }}
                                />
                            </button>
                        ))}
                    </div>
                    <div className="mt-2 flex h-4 gap-[2px] text-center text-sm font-mono tabular-nums text-overlay0">
                        {years.map((year) => (
                            <span key={year.year} className="min-w-0 flex-1">
                                {year.year}
                            </span>
                        ))}
                    </div>
                </div>
            </div>

            {/* Fixed height on purpose: the readout swaps between a hint and four figures,
                and a panel that resizes on hover makes the whole dashboard jump. */}
            <div className="mt-4 flex h-[4.5rem] shrink-0 items-center rounded-md border border-surface0 bg-mantle px-4">
                {active ? (
                    <dl className="grid w-full grid-cols-4 gap-x-6 text-base">
                        <Cell label={`Year ${active.year}`} value={active.source === "input" ? "your input" : "solved"} />
                        <Cell label="Growth" value={percent(active.growth, 2)} />
                        <Cell label="Revenue" value={money(active.revenue)} />
                        <Cell label="FCF" value={`${money(active.fcf)} @ ${percent(active.fcf_margin)}`} />
                    </dl>
                ) : (
                    <p className="text-base text-overlay0">hover a year for its revenue, margin and discounted value</p>
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
