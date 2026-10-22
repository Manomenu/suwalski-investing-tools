import { Alert, Box, Divider, Group, Loader, Paper, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

import type { ReverseDcfResult } from "./api";
import { FieldLabel } from "./FieldLabel";
import { percent } from "./format";

/** The answer. Input and solved sit in one card because they are one sentence — but the
 *  solved side is the finding, so it gets the filled panel, the accent border and the
 *  bigger figure, with an arrow marking the handover between them. */
export function Headline({ result, error }: { result: ReverseDcfResult | null; error: string | null }) {
    if (error) {
        return (
            <Alert color="red" variant="light" title="No growth justifies this price">
                {error}
            </Alert>
        );
    }
    if (!result) {
        return (
            <Paper withBorder p="lg">
                <Group gap="xs">
                    <Loader size="xs" />
                    <Text c="dimmed">solving…</Text>
                </Group>
            </Paper>
        );
    }

    const known = result.known_segments[0];
    const solved = result.solved_years;
    const firstSolved = solved[0] ?? 1;
    const lastSolved = solved.at(-1) ?? 1;
    const price = result.current_price.toFixed(2);

    return (
        <Paper withBorder p="lg">
            <Stack gap="md">
                <FieldLabel>Growth the price requires</FieldLabel>

                <Group gap="lg" align="stretch">
                    {known ? (
                        <>
                            <Stack gap={4} justify="center">
                                <Text fz={48} fw={700} lh={1} c="blue.4">
                                    {percent(known.growth)}
                                </Text>
                                <Text size="sm" fw={500} c="dimmed">
                                    YR {known.start_year}-{known.end_year} · your input
                                </Text>
                            </Stack>
                            <Text aria-hidden fz={30} c="dimmed" style={{ alignSelf: "center" }}>
                                →
                            </Text>
                        </>
                    ) : null}

                    <Box
                        px="lg"
                        py="sm"
                        bd="2px solid orange.4"
                        bg="var(--mantine-color-orange-light)"
                        style={{ borderRadius: "var(--mantine-radius-md)" }}
                    >
                        <Text fz={60} fw={700} lh={1.1} c="orange.4">
                            {percent(result.implied_growth)}
                        </Text>
                        <FieldLabel c="orange.4">
                            YR {firstSolved}-{lastSolved} · solved
                        </FieldLabel>
                    </Box>

                    <Stack gap={4} justify="center" c="dimmed">
                        <Text>
                            implied revenue CAGR <Figure>{percent(result.implied_revenue_cagr)}</Figure>
                        </Text>
                        <Text>
                            to support <Figure>{price}</Figure>
                        </Text>
                    </Stack>
                </Group>

                <Divider />

                <Text lh={1.6}>
                    {known ? (
                        <>
                            If revenue grows <Figure c="blue.4">{percent(known.growth)}</Figure> a year through year {known.end_year}, it
                            must then compound <Figure c="orange.4">{percent(result.implied_growth)}</Figure> a year through year{" "}
                            {lastSolved} to support today&apos;s {price}.
                        </>
                    ) : (
                        <>
                            Revenue must compound <Figure c="orange.4">{percent(result.implied_growth)}</Figure> a year through year{" "}
                            {lastSolved} to support today&apos;s {price}.
                        </>
                    )}
                </Text>
            </Stack>
        </Paper>
    );
}

function Figure({ children, c = "var(--mantine-color-text)" }: { children: ReactNode; c?: string }) {
    return (
        <Text span ff="monospace" fw={600} c={c}>
            {children}
        </Text>
    );
}
