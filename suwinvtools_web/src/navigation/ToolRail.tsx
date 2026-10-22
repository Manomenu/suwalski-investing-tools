import { ActionIcon, AppShell, Stack, Tooltip } from "@mantine/core";
import type { ReactNode } from "react";

/** Width of the rail of tool icons; the app shell reserves exactly this much. */
export const NAVBAR_WIDTH = 56;

export interface RailTool {
    path: string;
    name: string;
    icon: ReactNode;
}

/** A narrow navbar of icons only: one button per tool, named by its tooltip and aria-label. */
export function ToolRail({
    tools,
    activePath,
    onSelect,
}: {
    tools: readonly RailTool[];
    activePath: string;
    onSelect: (path: string) => void;
}) {
    return (
        <AppShell.Navbar p="xs" component="nav" aria-label="Narzędzia">
            <Stack gap="xs" align="center">
                {tools.map((tool) => (
                    <Tooltip key={tool.path} label={tool.name} position="right">
                        <ActionIcon
                            size="lg"
                            variant={tool.path === activePath ? "filled" : "subtle"}
                            aria-label={tool.name}
                            aria-current={tool.path === activePath ? "page" : undefined}
                            onClick={() => onSelect(tool.path)}
                        >
                            {tool.icon}
                        </ActionIcon>
                    </Tooltip>
                ))}
            </Stack>
        </AppShell.Navbar>
    );
}
