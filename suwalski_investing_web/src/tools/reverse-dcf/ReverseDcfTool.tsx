import { useEffect, useState } from "react";

import { fetchSnapshot, solveReverseDcf, type ReverseDcfResult, type TickerSnapshot } from "../../lib/api";
import { Assumptions, type AssumptionState } from "./Assumptions";
import { Headline } from "./Headline";
import { ProjectionChart } from "./ProjectionChart";
import { ProjectionTable } from "./ProjectionTable";

// Deliberately fixed, never seeded from the fetched snapshot: the margin and the growth are
// the opinions this tool exists to test. Today's margin is shown beside the slider instead.
const DEFAULTS: AssumptionState = {
    mode: "split",
    optimizedMargin: 0.35,
    nearTermGrowth: 0.15,
    splitAfter: 3,
    discount: 0.1,
    terminal: 0.025,
    years: 10,
};

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
            .then(setSnapshot)
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
                    onChange={setAssumptions}
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
                            <ProjectionChart years={result.projection.years} />
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
