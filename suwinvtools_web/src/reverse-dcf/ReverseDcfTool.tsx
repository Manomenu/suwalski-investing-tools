import { Flex, Paper, Stack } from "@mantine/core";
import { useState } from "react";

import type { TickerSnapshot } from "./api";
import { DEFAULTS, withMarginOf, withValidTerminal } from "./assumptions";
import { AssumptionsPanel } from "./AssumptionsPanel";
import { ChartPanel } from "./ChartPanel";
import { Headline } from "./Headline";
import { ProjectionTable } from "./ProjectionTable";
import { useReverseDcf } from "./useReverseDcf";
import { useSnapshot } from "./useSnapshot";

/** The Reverse DCF tool: assumptions on the left, the growth the price requires and its evidence on the right. */
export function ReverseDcfTool() {
    const [symbol, setSymbol] = useState("NVDA");
    const [assumptions, setAssumptions] = useState(DEFAULTS);
    const { snapshot, loading, error: snapshotError } = useSnapshot(symbol);
    const { result, error: solveError } = useReverseDcf(snapshot, assumptions);

    // A newly fetched company resets the margin to what it earns today. Adjusting state while
    // rendering (rather than in an effect) avoids a frame with the old margin on the new company.
    const [seen, setSeen] = useState<TickerSnapshot | null>(null);
    if (snapshot !== seen) {
        setSeen(snapshot);
        if (snapshot) setAssumptions(withMarginOf(assumptions, snapshot));
    }

    return (
        <Flex direction={{ base: "column", xl: "row" }} gap="md" p="md" align={{ base: "stretch", xl: "flex-start" }}>
            <Paper withBorder p="lg" w={{ base: "100%", xl: 416 }} style={{ flexShrink: 0 }}>
                <AssumptionsPanel
                    snapshot={snapshot}
                    loading={loading}
                    error={snapshotError}
                    symbol={symbol}
                    onSymbol={setSymbol}
                    value={assumptions}
                    onChange={(next) => {
                        setAssumptions(withValidTerminal(next));
                    }}
                />
            </Paper>

            <Stack gap="md" flex={1} miw={0}>
                <Headline result={result} error={solveError} />
                {result ? (
                    <>
                        <ChartPanel years={result.projection.years} history={snapshot?.history ?? []} />
                        <ProjectionTable projection={result.projection} />
                    </>
                ) : null}
            </Stack>
        </Flex>
    );
}
