import { Group, SimpleGrid, Text } from "@mantine/core";

/** Label/value pairs as a description list; values in the monospace face so figures line up. */
export function FactList({ rows, cols = 1 }: { rows: readonly (readonly [string, string])[]; cols?: number }) {
    return (
        <SimpleGrid component="dl" cols={cols} spacing="md" verticalSpacing={6} m={0}>
            {rows.map(([label, value]) => (
                <Group key={label} justify="space-between" wrap="nowrap" gap="md">
                    <Text component="dt" size="sm" c="dimmed">
                        {label}
                    </Text>
                    <Text component="dd" ff="monospace" fw={500} m={0} ta="right">
                        {value}
                    </Text>
                </Group>
            ))}
        </SimpleGrid>
    );
}
