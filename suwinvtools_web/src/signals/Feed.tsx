import { Anchor, Badge, Chip, Group, Paper, Stack, Text } from "@mantine/core";

import type { Outcome, Verdict } from "./api";
import { newestFirst, VERDICT_COLOR, VERDICT_LABEL } from "./present";

const FEED_VERDICTS: readonly Verdict[] = ["red", "green", "unconfirmed", "invalid"];

/** Verdicts newest first — what Discord got, muted greens included. */
export function Feed({
    outcomes,
    verdicts,
    onVerdicts,
    onOpen,
}: {
    outcomes: readonly Outcome[];
    verdicts: readonly Verdict[];
    onVerdicts: (next: Verdict[]) => void;
    onOpen: (checkId: string) => void;
}) {
    return (
        <Stack gap="sm">
            <Chip.Group multiple value={[...verdicts]} onChange={(next) => onVerdicts(next)}>
                <Group gap="xs">
                    {FEED_VERDICTS.map((verdict) => (
                        <Chip key={verdict} value={verdict} color={VERDICT_COLOR[verdict]} size="xs">
                            {VERDICT_LABEL[verdict]}
                        </Chip>
                    ))}
                </Group>
            </Chip.Group>
            {outcomes.length === 0 ? <Text c="dimmed">Nic takiego jeszcze nie było.</Text> : null}
            {newestFirst(outcomes).map((outcome) => (
                <Paper key={`${outcome.check_id}-${outcome.subject}-${outcome.period}`} withBorder p="sm" radius="md">
                    <Group gap="xs" mb={4}>
                        <Badge color={VERDICT_COLOR[outcome.verdict]} variant="light">
                            {VERDICT_LABEL[outcome.verdict]}
                        </Badge>
                        <Anchor component="button" type="button" fw={600} onClick={() => onOpen(outcome.check_id)}>
                            {outcome.check_id} · {outcome.subject}
                        </Anchor>
                        <Text size="xs" c="dimmed" ff="monospace">
                            {outcome.period}
                        </Text>
                    </Group>
                    <Text size="sm">{outcome.summary}</Text>
                </Paper>
            ))}
        </Stack>
    );
}
