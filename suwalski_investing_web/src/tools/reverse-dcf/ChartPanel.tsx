import { useState } from "react";

import type { HistoryPoint, YearProjection } from "../../lib/api";
import { HistoryChart } from "./HistoryChart";
import { ProjectionChart } from "./ProjectionChart";

type Tab = "projected" | "margin" | "growth";

const TABS: { id: Tab; label: string }[] = [
    { id: "projected", label: "Projected FCF" },
    { id: "margin", label: "Historical FCF margin" },
    { id: "growth", label: "Historical revenue growth" },
];

/** One card, three views of the same company: what the price demands ahead, and what the
 *  filings actually delivered. The history tabs are there to make the assumptions on the
 *  left arguable — a 35% margin reads differently next to ten years of 20%. */
export function ChartPanel({ years, history }: { years: YearProjection[]; history: HistoryPoint[] }) {
    const [tab, setTab] = useState<Tab>("projected");

    return (
        <figure className="flex h-full min-w-0 flex-col rounded-lg border border-surface0 bg-base p-5">
            <figcaption className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex gap-1.5">
                    {TABS.map((entry) => (
                        <button
                            key={entry.id}
                            type="button"
                            onClick={() => setTab(entry.id)}
                            aria-pressed={entry.id === tab}
                            className={`rounded-md border px-3 py-1.5 text-sm font-semibold tracking-wide uppercase transition-colors ${
                                entry.id === tab
                                    ? "border-mauve bg-surface0 text-text"
                                    : "border-transparent text-subtext0 hover:text-text"
                            }`}
                        >
                            {entry.label}
                        </button>
                    ))}
                </div>
                {tab === "projected" ? (
                    <span className="flex items-center gap-5 text-sm text-subtext0">
                        <Key color="bg-blue" label="your input" />
                        <Key color="bg-peach" label="solved" />
                    </span>
                ) : (
                    <span className="text-sm text-subtext0">as reported, oldest first</span>
                )}
            </figcaption>

            <div className="mt-5 min-h-0 flex-1">
                {tab === "projected" ? (
                    <ProjectionChart years={years} />
                ) : (
                    <HistoryChart points={history} metric={tab} />
                )}
            </div>
        </figure>
    );
}

function Key({ color, label }: { color: string; label: string }) {
    return (
        <span className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${color}`} />
            {label}
        </span>
    );
}
