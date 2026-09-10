import type { TickerSnapshot } from "../../lib/api";
import { ago, money, percent } from "../../lib/format";
import { Slider } from "../../ui/Slider";

export type GrowthMode = "single" | "split";

export interface AssumptionState {
    mode: GrowthMode;
    optimizedMargin: number;
    nearTermGrowth: number;
    splitAfter: number;
    discount: number;
    terminal: number;
    years: number;
}

const HORIZONS = [3, 5, 7, 10, 15, 20];

interface AssumptionsProps {
    snapshot: TickerSnapshot | null;
    loading: boolean;
    error: string | null;
    symbol: string;
    onSymbol: (symbol: string) => void;
    value: AssumptionState;
    onChange: (next: AssumptionState) => void;
}

export function Assumptions({ snapshot, loading, error, symbol, onSymbol, value, onChange }: AssumptionsProps) {
    const [pending, setPending] = [symbol, onSymbol];
    const set = <K extends keyof AssumptionState>(key: K) => (next: AssumptionState[K]) =>
        onChange({ ...value, [key]: next });

    return (
        <div className="flex h-full flex-col gap-5 overflow-y-auto rounded-lg border border-surface0 bg-base p-5">
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    const input = new FormData(event.currentTarget).get("ticker");
                    if (typeof input === "string" && input.trim()) setPending(input.trim().toUpperCase());
                }}
            >
                <label className="block text-sm font-semibold tracking-wide text-subtext0 uppercase" htmlFor="ticker">
                    Ticker
                </label>
                <input
                    id="ticker"
                    name="ticker"
                    defaultValue={pending}
                    key={pending}
                    spellCheck={false}
                    className="mt-2 w-full rounded-md border border-surface0 bg-mantle px-3 py-2.5 text-2xl font-semibold tracking-wide text-text uppercase outline-none focus:border-mauve"
                />
            </form>

            {loading ? <p className="text-base text-overlay0">loading…</p> : null}
            {error ? <p className="text-base text-red">{error}</p> : null}
            {snapshot ? <Facts snapshot={snapshot} /> : null}

            <div className="flex flex-col gap-5 border-t border-surface0 pt-5">
                <Choice
                    label="Growth"
                    options={["single", "split"] as GrowthMode[]}
                    value={value.mode}
                    onChange={set("mode")}
                    render={(mode) => (mode === "single" ? "Single rate" : "Split growth")}
                />

                {value.mode === "split" ? (
                    <>
                        <Slider
                            label={`Near-term growth · YR 1-${value.splitAfter}`}
                            value={value.nearTermGrowth}
                            min={-0.2}
                            max={1}
                            step={0.01}
                            onChange={set("nearTermGrowth")}
                            format={(rate) => percent(rate)}
                            hint="the years you have a view on — analyst or industry forecast"
                        />
                        <Choice
                            label="Split after"
                            options={[1, 2, 3, 4, 5]}
                            value={value.splitAfter}
                            onChange={set("splitAfter")}
                            render={(year) => `YR ${year}`}
                        />
                    </>
                ) : (
                    <p className="-mt-2 text-sm leading-snug text-overlay0">
                        One rate for the whole horizon — the tool solves it against today&apos;s price.
                    </p>
                )}

                <Slider
                    label="Optimized FCF margin"
                    value={value.optimizedMargin}
                    min={0.01}
                    max={0.8}
                    step={0.005}
                    onChange={set("optimizedMargin")}
                    format={(rate) => percent(rate)}
                    hint={
                        snapshot
                            ? `what the business settles at. Today: ${percent(snapshot.fcf_ttm / snapshot.revenue_ttm)}`
                            : "what the business settles at once it stops investing for growth"
                    }
                />
                <Slider
                    label="Discount rate"
                    value={value.discount}
                    min={0.03}
                    max={0.2}
                    step={0.005}
                    onChange={set("discount")}
                    format={(rate) => percent(rate)}
                    hint="the annual return you demand. Higher means the same price implies more growth"
                />
                <Slider
                    label="Terminal growth"
                    value={value.terminal}
                    min={0}
                    max={Math.min(0.06, value.discount - 0.005)}
                    step={0.0025}
                    onChange={set("terminal")}
                    format={(rate) => percent(rate, 2)}
                    hint="growth forever after the last projected year. Long-run GDP (~3%) is the honest ceiling"
                />
                <Choice
                    label="Horizon"
                    options={HORIZONS}
                    value={value.years}
                    onChange={set("years")}
                    render={(years) => `${years}Y`}
                />
            </div>
        </div>
    );
}

function Facts({ snapshot }: { snapshot: TickerSnapshot }) {
    const rows: [string, string][] = [
        ["Price", `${snapshot.price.toFixed(2)}${snapshot.currency ? ` ${snapshot.currency}` : ""}`],
        ["Market cap", money(snapshot.price * snapshot.shares_outstanding)],
        ["Revenue TTM", money(snapshot.revenue_ttm)],
        ["FCF TTM", `${money(snapshot.fcf_ttm)} (${percent(snapshot.fcf_ttm / snapshot.revenue_ttm)})`],
        ["Net debt", money(snapshot.net_debt)],
    ];
    return (
        <div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
                {rows.map(([label, value]) => (
                    <div key={label} className="contents">
                        <dt className="text-sm text-overlay0">{label}</dt>
                        <dd className="text-right text-base font-medium font-mono tabular-nums text-subtext1">{value}</dd>
                    </div>
                ))}
            </dl>
            <p className="mt-3 text-sm text-overlay0">
                {snapshot.source}, fetched {ago(snapshot.as_of)}
            </p>
        </div>
    );
}

interface ChoiceProps<T extends string | number> {
    label: string;
    options: T[];
    value: T;
    onChange: (value: T) => void;
    render: (value: T) => string;
}

function Choice<T extends string | number>({ label, options, value, onChange, render }: ChoiceProps<T>) {
    return (
        <div>
            <span className="text-sm font-semibold tracking-wide text-subtext0 uppercase">{label}</span>
            <div className="mt-2 flex gap-1.5">
                {options.map((option) => (
                    <button
                        key={option}
                        type="button"
                        onClick={() => onChange(option)}
                        aria-pressed={option === value}
                        className={`flex-1 rounded-md border px-2 py-1.5 text-base font-medium transition-colors ${
                            option === value
                                ? "border-mauve bg-surface0 text-text"
                                : "border-surface0 text-subtext0 hover:text-text"
                        }`}
                    >
                        {render(option)}
                    </button>
                ))}
            </div>
        </div>
    );
}
