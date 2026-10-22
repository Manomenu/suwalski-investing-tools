import { Group, Paper, SimpleGrid, Stack, Text, Title, UnstyledButton } from "@mantine/core";

import type { BoardItem } from "./api";
import { columns, formatValue, VERDICT_COLOR } from "./present";
import { Sparkline } from "./Sparkline";
import { VerdictDot } from "./VerdictDot";

/** One column per category, one row per check: the light, the check, its latest value and trend. */
export function Board({ items, onOpen }: { items: readonly BoardItem[]; onOpen: (checkId: string) => void }) {
    return (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3, xl: 5 }} spacing="md">
            {columns(items).map((column) => (
                <Paper key={column.category} withBorder p="sm" radius="md">
                    <Title order={2} size="h5" mb="xs">
                        {column.category} · {column.name}
                    </Title>
                    <Stack gap={4}>
                        {column.items.map((item) => (
                            <CheckRow key={item.check.id} item={item} onOpen={onOpen} />
                        ))}
                    </Stack>
                </Paper>
            ))}
        </SimpleGrid>
    );
}

function CheckRow({ item, onOpen }: { item: BoardItem; onOpen: (checkId: string) => void }) {
    const headline = item.headline ?? null;
    const latestValue = item.spark.at(-1);
    const color = headline ? `var(--mantine-color-${VERDICT_COLOR[headline.verdict]}-5)` : "var(--mantine-color-gray-6)";
    return (
        <UnstyledButton
            className="signal-row"
            onClick={() => onOpen(item.check.id)}
            aria-label={`${item.check.id} ${item.check.title}`}
            p={6}
            style={{ borderRadius: "var(--mantine-radius-sm)" }}
        >
            <Group gap="xs" wrap="nowrap" align="flex-start">
                <div style={{ paddingTop: 4 }}>
                    <VerdictDot verdict={headline?.verdict ?? null} />
                </div>
                <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
                    <Text size="sm" fw={600} lineClamp={2}>
                        {item.check.id} {item.check.title}
                    </Text>
                    <Group gap="xs" justify="space-between" wrap="nowrap">
                        <Text size="xs" c="dimmed" ff="monospace" truncate>
                            {headline ? `${formatValue(latestValue, item.check.unit)} · ${headline.period}` : "jeszcze nie odczytany"}
                        </Text>
                        <Sparkline values={item.spark} color={color} />
                    </Group>
                </Stack>
            </Group>
        </UnstyledButton>
    );
}
