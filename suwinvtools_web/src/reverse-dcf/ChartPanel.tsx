import { ColorSwatch, Group, Paper, SegmentedControl, Stack, Text } from "@mantine/core";
import { useState } from "react";

import type { HistoryPoint, YearProjection } from "./api";
import { SERIES_COLOR } from "./chart";
import { HistoryChart } from "./HistoryChart";
import { ProjectionChart } from "./ProjectionChart";

type Tab = "projected" | "margin" | "growth";

const TABS: { value: Tab; label: string }[] = [
    { value: "projected", label: "Projected FCF" },
    { value: "margin", label: "Historical FCF margin" },
    { value: "growth", label: "Historical revenue growth" },
];

/** One card, three views of the same company: what the price demands ahead, and what the
 *  filings actually delivered. The history tabs are there to make the assumptions on the
 *  left arguable — a 35% margin reads differently next to ten years of 20%. */
export function ChartPanel({ years, history }: { years: YearProjection[]; history: HistoryPoint[] }) {
    const [tab, setTab] = useState<Tab>("projected");

    return (
        <Paper withBorder p="lg" component="figure" m={0}>
            <Stack gap="lg">
                <Group component="figcaption" justify="space-between" gap="md">
                    <SegmentedControl
                        aria-label="Chart"
                        value={tab}
                        data={TABS}
                        onChange={(next) => {
                            setTab(TABS.find((entry) => entry.value === next)?.value ?? "projected");
                        }}
                    />
                    {tab === "projected" ? (
                        <Group gap="lg">
                            <Key color={SERIES_COLOR.input} label="your input" />
                            <Key color={SERIES_COLOR.solved} label="solved" />
                        </Group>
                    ) : (
                        <Text size="sm" c="dimmed">
                            as reported, oldest first
                        </Text>
                    )}
                </Group>

                {tab === "projected" ? <ProjectionChart years={years} /> : <HistoryChart points={history} metric={tab} />}
            </Stack>
        </Paper>
    );
}

function Key({ color, label }: { color: string; label: string }) {
    return (
        <Group gap={6}>
            <ColorSwatch color={color} size={10} withShadow={false} />
            <Text size="sm" c="dimmed">
                {label}
            </Text>
        </Group>
    );
}
