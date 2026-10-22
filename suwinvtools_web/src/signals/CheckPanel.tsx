import { Alert, Anchor, Badge, Drawer, Group, List, Loader, ScrollArea, Stack, Table, Text, Title } from "@mantine/core";

import { fetchHistory, type CheckHistory, type Reading } from "./api";
import { formatValue, VERDICT_COLOR, VERDICT_LABEL } from "./present";
import { Sparkline } from "./Sparkline";
import { useLoad } from "./useLoad";

/** Width of the panel that opens over the board; the board stays visible to its left. */
const PANEL_WIDTH = 560;

/** One check: the rule in words, its history per subject, every verdict and the words it rests on. */
export function CheckPanel({ checkId, onClose }: { checkId: string | null; onClose: () => void }) {
    return (
        <Drawer
            opened={checkId !== null}
            onClose={onClose}
            position="right"
            size={PANEL_WIDTH}
            title={checkId ?? ""}
            closeButtonProps={{ "aria-label": "Zamknij" }}
            scrollAreaComponent={ScrollArea.Autosize}
        >
            {checkId === null ? null : <CheckBody checkId={checkId} />}
        </Drawer>
    );
}

function CheckBody({ checkId }: { checkId: string }) {
    const loaded = useLoad(checkId, (signal) => fetchHistory(checkId, signal));
    if (loaded.kind === "loading") return <Loader size="sm" />;
    if (loaded.kind === "failed") return <Alert color="red">{loaded.message}</Alert>;
    return <CheckDetails history={loaded.data} />;
}

function CheckDetails({ history }: { history: CheckHistory }) {
    const { check, readings, outcomes } = history;
    const subjects = groupBySubject(readings);
    return (
        <Stack gap="md">
            <Title order={3} size="h4">
                {check.title}
            </Title>
            <Text size="sm">{check.question}</Text>
            <Stack gap={4}>
                <Text size="sm">
                    <Badge color="red" variant="light" mr="xs">
                        RED
                    </Badge>
                    {check.rule_red}
                </Text>
                <Text size="sm">
                    <Badge color="green" variant="light" mr="xs">
                        GREEN
                    </Badge>
                    {check.rule_green}
                </Text>
                <Text size="xs" c="dimmed">
                    {check.caveat}
                </Text>
            </Stack>

            {subjects.length > 0 ? (
                <Stack gap={6}>
                    <Title order={4} size="h6">
                        Historia odczytów
                    </Title>
                    {subjects.map(([subject, points]) => (
                        <Group key={subject} justify="space-between" wrap="nowrap">
                            <Text size="sm" w={140} truncate>
                                {subject}
                            </Text>
                            <Sparkline values={points.map((point) => point.value ?? 0)} color="var(--mantine-color-violet-4)" />
                            <Text size="xs" ff="monospace" c="dimmed">
                                {formatValue(points.at(-1)?.value, check.unit)} · {points.at(-1)?.period}
                            </Text>
                        </Group>
                    ))}
                </Stack>
            ) : (
                <Text c="dimmed" size="sm">
                    Ten check jeszcze nic nie odczytał.
                </Text>
            )}

            {outcomes.length > 0 ? (
                <Stack gap={6}>
                    <Title order={4} size="h6">
                        Werdykty
                    </Title>
                    <Table verticalSpacing={6} fz="sm">
                        <Table.Tbody>
                            {outcomes.map((outcome) => (
                                <Table.Tr key={`${outcome.subject}-${outcome.period}`}>
                                    <Table.Td style={{ verticalAlign: "top" }}>
                                        <Badge color={VERDICT_COLOR[outcome.verdict]} variant="light" size="sm">
                                            {VERDICT_LABEL[outcome.verdict]}
                                        </Badge>
                                        <Text size="xs" c="dimmed" ff="monospace">
                                            {outcome.period}
                                        </Text>
                                    </Table.Td>
                                    <Table.Td>
                                        <Text size="sm">{outcome.summary}</Text>
                                        {outcome.evidence.length > 0 ? (
                                            <List size="xs" mt={4} spacing={2}>
                                                {outcome.evidence.map((item) => (
                                                    <List.Item key={item.url + item.quote}>
                                                        <Anchor href={item.url} target="_blank" rel="noreferrer">
                                                            {item.title}
                                                        </Anchor>
                                                        {item.quote ? (
                                                            <Text span c="dimmed">
                                                                {" "}
                                                                — „{item.quote}”
                                                            </Text>
                                                        ) : null}
                                                    </List.Item>
                                                ))}
                                            </List>
                                        ) : null}
                                    </Table.Td>
                                </Table.Tr>
                            ))}
                        </Table.Tbody>
                    </Table>
                </Stack>
            ) : null}
        </Stack>
    );
}

function groupBySubject(readings: readonly Reading[]): [string, Reading[]][] {
    const grouped = new Map<string, Reading[]>();
    for (const reading of readings) grouped.set(reading.subject, [...(grouped.get(reading.subject) ?? []), reading]);
    return [...grouped.entries()];
}
