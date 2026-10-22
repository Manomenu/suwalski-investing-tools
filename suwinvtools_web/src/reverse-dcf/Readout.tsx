import { Paper, SimpleGrid, Stack, Text } from "@mantine/core";

/** The fixed-height strip under a chart: a hint, or the figures of the hovered bar. Fixed on
 *  purpose — the readout swaps between a hint and four figures, and a strip that resizes on
 *  hover makes the whole dashboard jump. */
export function Readout({ hint, cells }: { hint: string; cells: readonly (readonly [string, string])[] | null }) {
    return (
        <Paper withBorder px="md" h={72} style={{ display: "flex", alignItems: "center" }}>
            {cells ? (
                <SimpleGrid component="dl" cols={4} spacing="lg" w="100%" m={0}>
                    {cells.map(([label, value]) => (
                        <Stack key={label} gap={0}>
                            <Text component="dt" size="sm" c="dimmed">
                                {label}
                            </Text>
                            <Text component="dd" ff="monospace" fw={500} m={0}>
                                {value}
                            </Text>
                        </Stack>
                    ))}
                </SimpleGrid>
            ) : (
                <Text c="dimmed">{hint}</Text>
            )}
        </Paper>
    );
}
