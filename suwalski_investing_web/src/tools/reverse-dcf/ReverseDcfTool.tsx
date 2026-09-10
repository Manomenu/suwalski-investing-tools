import { useEffect, useState } from "react";

import { fetchSnapshot, solveReverseDcf, type ReverseDcfResult, type TickerSnapshot } from "../../lib/api";
import { Assumptions, type AssumptionState } from "./Assumptions";
import { ChartPanel } from "./ChartPanel";
import { Headline } from "./Headline";
import { ProjectionTable } from "./ProjectionTable";

const DEFAULTS: AssumptionState = {
    mode: "split",
    optimizedMargin: 0.35,
    nearTermGrowth: 0.15,
    splitAfter: 3,
    discount: 0.1,
    terminal: 0.025,
    years: 10,
};

/** Terminal growth must stay below the discount rate, and the discount slider can move
 *  under a terminal rate that was fine when it was set — the API rejects that pairing, so
 *  it never gets sent. */
function withValidTerminal(next: AssumptionState): AssumptionState {
    const ceiling = next.discount - 0.005;
    return next.terminal > ceiling ? { ...next, terminal: Math.max(0, ceiling) } : next;
}

export function ReverseDcfTool() {
    const [symbol, setSymbol] = useState("NVDA");
    const [snapshot, setSnapshot] = useState<TickerSnapshot | null>(null);
    const [snapshotError, setSnapshotError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [assumptions, setAssumptions] = useState(DEFAULTS);
    const [result, setResult] = useState<ReverseDcfResult | null>(null);
    const [solveError, setSolveError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();
        setLoading(true);
        setSnapshotError(null);
        fetchSnapshot(symbol, controller.signal)
            .then((fetched) => {
                setSnapshot(fetched);
                // Start the margin at what the company actually earns today. A fixed default
                // is itself an assumption, and a worse one: 35% is unremarkable for NVDA and
                // absurd for a grocery chain running at 2%, where it values three years of
                // cash above the entire market cap and the solver has nothing to solve.
                const today = fetched.fcf_ttm / fetched.revenue_ttm;
                setAssumptions((current) => ({
                    ...current,
                    optimizedMargin: Math.min(0.8, Math.max(0.01, Math.round(today * 1000) / 1000)),
                }));
            })
            .catch((error: Error) => {
                if (error.name !== "AbortError") {
                    setSnapshot(null);
                    setSnapshotError(error.message);
                }
            })
            .finally(() => setLoading(false));
        return () => controller.abort();
    }, [symbol]);

    useEffect(() => {
        if (!snapshot) return;
        const controller = new AbortController();
        // Sliders fire continuously while dragging; one request per rest, not per pixel.
        const timer = setTimeout(() => {
            const { mode, splitAfter, years } = assumptions;
            // Single rate means no pinned years at all — the solver fills the whole horizon.
            const pinned = mode === "split" && splitAfter < years;
            solveReverseDcf(
                {
                    revenue: snapshot.revenue_ttm,
                    optimized_fcf_margin: assumptions.optimizedMargin,
                    shares_outstanding: snapshot.shares_outstanding,
                    net_debt: snapshot.net_debt,
                    discount_rate: assumptions.discount,
                    terminal_growth: assumptions.terminal,
                    projection_years: years,
                    current_price: snapshot.price,
                    growth_segments: pinned
                        ? [{ start_year: 1, end_year: splitAfter, growth: assumptions.nearTermGrowth }]
                        : [],
                },
                controller.signal,
            )
                .then((solved) => {
                    setResult(solved);
                    setSolveError(null);
                })
                .catch((error: Error) => {
                    if (error.name !== "AbortError") {
                        setSolveError(error.message);
                        setResult(null);
                    }
                });
        }, 200);
        return () => {
            controller.abort();
            clearTimeout(timer);
        };
    }, [snapshot, assumptions]);

    return (
        <div className="flex h-full flex-col gap-4 overflow-y-auto p-4 xl:flex-row xl:overflow-hidden">
            <section className="shrink-0 xl:h-full xl:w-[26rem]">
                <Assumptions
                    snapshot={snapshot}
                    loading={loading}
                    error={snapshotError}
                    symbol={symbol}
                    onSymbol={setSymbol}
                    value={assumptions}
                    onChange={(next) => setAssumptions(withValidTerminal(next))}
                />
            </section>

            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
                {/* Above both columns — otherwise it eats half the chart's height. */}
                <div className="shrink-0">
                    <Headline result={result} error={solveError} />
                </div>

                {/* On 21:9 the table sits beside the chart; below that it stacks under it. */}
                <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 wide:flex-row">
                    {result ? (
                        <div className="min-h-64 min-w-0 flex-[2]">
                            <ChartPanel years={result.projection.years} history={snapshot?.history ?? []} />
                        </div>
                    ) : null}
                    {result ? (
                        <section className="min-h-56 min-w-0 flex-[3] wide:h-full wide:w-[32rem] wide:flex-none">
                            <ProjectionTable projection={result.projection} />
                        </section>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
