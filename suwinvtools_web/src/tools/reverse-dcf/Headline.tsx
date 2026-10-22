import type { ReverseDcfResult } from "../../lib/api";
import { percent } from "../../lib/format";

/** The answer. Input and solved sit in one card because they are one sentence — but the
 *  solved side is the finding, so it gets the filled panel, the accent border and the
 *  bigger figure, with an arrow marking the handover between them. */
export function Headline({ result, error }: { result: ReverseDcfResult | null; error: string | null }) {
    if (error) {
        return (
            <div className="rounded-lg border border-red/50 bg-base p-6">
                <p className="text-sm font-semibold tracking-wide text-red uppercase">No growth justifies this price</p>
                <p className="mt-3 text-base leading-relaxed text-subtext1">{error}</p>
            </div>
        );
    }
    if (!result) {
        return <div className="rounded-lg border border-surface0 bg-base p-6 text-base text-overlay0">solving…</div>;
    }

    const known = result.known_segments[0];
    const solved = result.solved_years;
    const firstSolved = solved[0] ?? 1;
    const lastSolved = solved.at(-1) ?? 1;
    const price = result.current_price.toFixed(2);

    return (
        <div className="rounded-lg border border-surface0 bg-base p-5">
            <p className="text-sm font-semibold tracking-wide text-subtext0 uppercase">Growth the price requires</p>

            <div className="mt-4 flex flex-wrap items-stretch gap-5">
                {known ? (
                    <>
                        <div className="flex flex-col justify-center">
                            <div className="text-5xl font-bold text-blue">{percent(known.growth)}</div>
                            <div className="mt-2 text-sm font-medium text-subtext0">
                                YR {known.start_year}-{known.end_year} · your input
                            </div>
                        </div>
                        <div aria-hidden className="flex items-center text-3xl text-overlay0">
                            →
                        </div>
                    </>
                ) : null}

                <div className="rounded-lg border-2 border-peach/60 bg-peach/10 px-6 py-3">
                    <div className="text-6xl font-bold text-peach">{percent(result.implied_growth)}</div>
                    <div className="mt-2 text-sm font-semibold tracking-wide text-peach/90 uppercase">
                        YR {firstSolved}-{lastSolved} · solved
                    </div>
                </div>

                <div className="flex flex-col justify-center gap-1 text-base text-subtext0">
                    <span>
                        implied revenue CAGR{" "}
                        <span className="font-semibold font-mono tabular-nums text-subtext1">
                            {percent(result.implied_revenue_cagr)}
                        </span>
                    </span>
                    <span>
                        to support{" "}
                        <span className="font-semibold font-mono tabular-nums text-subtext1">{price}</span>
                    </span>
                </div>
            </div>

            <p className="mt-4 border-t border-surface0 pt-3 text-base leading-relaxed text-subtext1">
                {known ? (
                    <>
                        If revenue grows <Figure className="text-blue">{percent(known.growth)}</Figure> a year through
                        year {known.end_year}, it must then compound{" "}
                        <Figure className="text-peach">{percent(result.implied_growth)}</Figure> a year through year{" "}
                        {lastSolved} to support today&apos;s {price}.
                    </>
                ) : (
                    <>
                        Revenue must compound{" "}
                        <Figure className="text-peach">{percent(result.implied_growth)}</Figure> a year through year{" "}
                        {lastSolved} to support today&apos;s {price}.
                    </>
                )}
            </p>
        </div>
    );
}

function Figure({ children, className }: { children: React.ReactNode; className: string }) {
    return <span className={`font-semibold font-mono tabular-nums ${className}`}>{children}</span>;
}
