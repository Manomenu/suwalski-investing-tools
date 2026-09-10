import type { Projection } from "../../lib/api";
import { money, percent } from "../../lib/format";

/** The numbers behind the chart — also the accessible view of the same data. */
export function ProjectionTable({ projection }: { projection: Projection }) {
    const summary: [string, string][] = [
        ["PV of projected years", money(projection.pv_explicit)],
        ["PV of terminal value", money(projection.pv_terminal)],
        ["Enterprise value", money(projection.enterprise_value)],
        ["Equity value", money(projection.equity_value)],
        ["Revenue CAGR", percent(projection.revenue_cagr, 2)],
        ["Intrinsic value / share", projection.intrinsic_value_per_share.toFixed(2)],
    ];

    return (
        <div className="flex h-full flex-col rounded-lg border border-surface0 bg-base p-5">
            <div className="min-h-0 min-w-0 flex-1 overflow-auto">
                <table className="w-full text-base font-mono tabular-nums">
                    <thead>
                        <tr className="text-sm font-semibold tracking-wide text-overlay0 uppercase">
                            <th className="py-1.5 text-left">Yr</th>
                            <th className="py-1.5 text-right">Growth</th>
                            <th className="py-1.5 text-right">Revenue</th>
                            <th className="py-1.5 text-right">FCF</th>
                            <th className="py-1.5 text-right">PV</th>
                        </tr>
                    </thead>
                    <tbody>
                        {projection.years.map((year) => (
                            <tr key={year.year} className="border-t border-surface0/60">
                                <td className="py-1.5 text-left text-overlay0">{year.year}</td>
                                <td
                                    className={`py-1.5 text-right font-semibold ${
                                        year.source === "input" ? "text-blue" : "text-peach"
                                    }`}
                                >
                                    {percent(year.growth, 2)}
                                </td>
                                <td className="py-1.5 text-right text-subtext1">{money(year.revenue)}</td>
                                <td className="py-1.5 text-right text-subtext1">{money(year.fcf)}</td>
                                <td className="py-1.5 text-right text-subtext0">{money(year.present_value)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <dl className="mt-4 grid shrink-0 grid-cols-2 gap-x-6 gap-y-1.5 border-t border-surface0 pt-4 text-base xl:grid-cols-4 wide:grid-cols-2">
                {summary.map(([label, value]) => (
                    <div key={label} className="contents">
                        <dt className="text-sm text-overlay0">{label}</dt>
                        <dd className="text-right font-medium font-mono tabular-nums text-subtext1">{value}</dd>
                    </div>
                ))}
            </dl>
        </div>
    );
}
