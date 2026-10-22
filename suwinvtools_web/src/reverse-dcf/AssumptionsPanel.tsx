import { Alert, Divider, Group, Loader, Stack, Text, TextInput } from "@mantine/core";

import type { TickerSnapshot } from "./api";
import { HORIZONS, SPLIT_AFTER_OPTIONS, currentMargin, terminalMax, type AssumptionState, type GrowthMode } from "./assumptions";
import { AssumptionSlider } from "./AssumptionSlider";
import { Choice } from "./Choice";
import { FactList } from "./FactList";
import { ago, money, percent } from "./format";

const MODES: readonly GrowthMode[] = ["single", "split"];

interface AssumptionsPanelProps {
    snapshot: TickerSnapshot | null;
    loading: boolean;
    error: string | null;
    symbol: string;
    onSymbol: (symbol: string) => void;
    value: AssumptionState;
    onChange: (next: AssumptionState) => void;
}

export function AssumptionsPanel({ snapshot, loading, error, symbol, onSymbol, value, onChange }: AssumptionsPanelProps) {
    const set =
        <K extends keyof AssumptionState>(key: K) =>
        (next: AssumptionState[K]) => {
            onChange({ ...value, [key]: next });
        };

    return (
        <Stack gap="lg">
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    const input = new FormData(event.currentTarget).get("ticker");
                    if (typeof input === "string" && input.trim()) onSymbol(input.trim().toUpperCase());
                }}
            >
                <TextInput
                    // Remounts with the accepted symbol, so the field shows the upper-cased one.
                    key={symbol}
                    label="Ticker"
                    name="ticker"
                    defaultValue={symbol}
                    spellCheck={false}
                    size="lg"
                    styles={{ input: { textTransform: "uppercase", fontWeight: 600 } }}
                />
            </form>

            {loading ? (
                <Group gap="xs">
                    <Loader size="xs" />
                    <Text c="dimmed">loading…</Text>
                </Group>
            ) : null}
            {error ? (
                <Alert color="red" variant="light">
                    {error}
                </Alert>
            ) : null}
            {snapshot ? <Facts snapshot={snapshot} /> : null}

            <Divider />

            <Choice
                label="Growth"
                options={MODES}
                value={value.mode}
                onChange={set("mode")}
                render={(mode) => (mode === "single" ? "Single rate" : "Split growth")}
            />

            {value.mode === "split" ? (
                <>
                    <AssumptionSlider
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
                        options={SPLIT_AFTER_OPTIONS}
                        value={value.splitAfter}
                        onChange={set("splitAfter")}
                        render={(year) => `YR ${year}`}
                    />
                </>
            ) : (
                <Text size="sm" c="dimmed" lh={1.35}>
                    One rate for the whole horizon — the tool solves it against today&apos;s price.
                </Text>
            )}

            <AssumptionSlider
                label="Optimized FCF margin"
                value={value.optimizedMargin}
                min={0.01}
                max={0.8}
                step={0.005}
                onChange={set("optimizedMargin")}
                format={(rate) => percent(rate)}
                hint={
                    snapshot
                        ? `what the business settles at. Today: ${percent(currentMargin(snapshot))}`
                        : "what the business settles at once it stops investing for growth"
                }
            />
            <AssumptionSlider
                label="Discount rate"
                value={value.discount}
                min={0.03}
                max={0.2}
                step={0.005}
                onChange={set("discount")}
                format={(rate) => percent(rate)}
                hint="the annual return you demand. Higher means the same price implies more growth"
            />
            <AssumptionSlider
                label="Terminal growth"
                value={value.terminal}
                min={0}
                max={terminalMax(value.discount)}
                step={0.0025}
                onChange={set("terminal")}
                format={(rate) => percent(rate, 2)}
                hint="growth forever after the last projected year. Long-run GDP (~3%) is the honest ceiling"
            />
            <Choice label="Horizon" options={HORIZONS} value={value.years} onChange={set("years")} render={(years) => `${years}Y`} />
        </Stack>
    );
}

function Facts({ snapshot }: { snapshot: TickerSnapshot }) {
    const rows: [string, string][] = [
        ["Price", `${snapshot.price.toFixed(2)}${snapshot.currency ? ` ${snapshot.currency}` : ""}`],
        ["Market cap", money(snapshot.price * snapshot.shares_outstanding)],
        ["Revenue TTM", money(snapshot.revenue_ttm)],
        ["FCF TTM", `${money(snapshot.fcf_ttm)} (${percent(currentMargin(snapshot))})`],
        ["Net debt", money(snapshot.net_debt)],
    ];
    return (
        <Stack gap="xs">
            <FactList rows={rows} />
            <Text size="sm" c="dimmed">
                {snapshot.source}, fetched {ago(snapshot.as_of)}
            </Text>
        </Stack>
    );
}
