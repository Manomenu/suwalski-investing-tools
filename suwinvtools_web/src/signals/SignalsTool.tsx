import { Alert, Group, Loader, ScrollArea, SegmentedControl, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";

import { fetchBoard, fetchFeed, type Verdict } from "./api";
import { Board } from "./Board";
import { CheckPanel } from "./CheckPanel";
import { Feed } from "./Feed";
import { runLine } from "./present";
import { parseRoute, pathFor } from "./route";
import { useLoad } from "./useLoad";

/** The AI cycle signals: the board (default) or the timeline, and the panel of one check.
 *  `path` is the location's pathname (/signals, /signals/feed, /signals/A1). */
export function SignalsTool({ path, navigate }: { path: string; navigate: (to: string) => void }) {
    const route = parseRoute(path);
    const [verdicts, setVerdicts] = useState<Verdict[]>(["red", "green"]);
    const board = useLoad("board", fetchBoard);

    return (
        <ScrollArea h="100vh">
            <Stack p="md" gap="md">
                <Group justify="space-between" wrap="wrap">
                    <Group gap="md">
                        <Title order={1} size="h3">
                            Sygnały końca hossy na AI
                        </Title>
                        <SegmentedControl
                            size="xs"
                            value={route.view}
                            onChange={(view) => navigate(pathFor({ view: view, checkId: null }))}
                            data={[
                                { value: "board", label: "Tablica" },
                                { value: "feed", label: "Oś czasu" },
                            ]}
                        />
                    </Group>
                    <Text size="sm" c="dimmed">
                        {board.kind === "ready" ? runLine(board.data.last_run) : ""}
                    </Text>
                </Group>

                {board.kind === "loading" ? <Loader size="sm" /> : null}
                {board.kind === "failed" ? <Alert color="red">{board.message}</Alert> : null}
                {board.kind === "ready" && route.view === "board" ? (
                    <Board items={board.data.items} onOpen={(checkId) => navigate(pathFor({ view: "board", checkId }))} />
                ) : null}
                {route.view === "feed" ? (
                    <FeedView
                        verdicts={verdicts}
                        onVerdicts={setVerdicts}
                        onOpen={(checkId) => navigate(pathFor({ view: "board", checkId }))}
                    />
                ) : null}
            </Stack>
            <CheckPanel checkId={route.checkId} onClose={() => navigate(pathFor({ view: "board", checkId: null }))} />
        </ScrollArea>
    );
}

function FeedView({
    verdicts,
    onVerdicts,
    onOpen,
}: {
    verdicts: Verdict[];
    onVerdicts: (next: Verdict[]) => void;
    onOpen: (checkId: string) => void;
}) {
    const feed = useLoad(`feed:${verdicts.join(",")}`, (signal) => fetchFeed(verdicts, signal));
    if (feed.kind === "failed") return <Alert color="red">{feed.message}</Alert>;
    return <Feed outcomes={feed.kind === "ready" ? feed.data : []} verdicts={verdicts} onVerdicts={onVerdicts} onOpen={onOpen} />;
}
