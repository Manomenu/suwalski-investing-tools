import { AppShell } from "@mantine/core";
import { IconChartLine, IconTrafficLights } from "@tabler/icons-react";
import { useEffect } from "react";

import { NAVBAR_WIDTH, ToolRail, type RailTool } from "./navigation/ToolRail";
import { isToolPath, toolFor } from "./navigation/routing";
import { usePathname } from "./navigation/usePathname";
import { ReverseDcfTool } from "./reverse-dcf/ReverseDcfTool";
import { SignalsTool } from "./signals/SignalsTool";

/** The tools in rail order; the first is where `/` and unknown paths land. */
const TOOLS: readonly RailTool[] = [
    { path: "/signals", name: "Sygnały", icon: <IconTrafficLights size={20} /> },
    { path: "/reverse-dcf", name: "Reverse DCF", icon: <IconChartLine size={20} /> },
];
const TOOL_PATHS = TOOLS.map((tool) => tool.path);

/** Puts the page together from features: the rail of tools and the open tool beside it. */
export function App() {
    const { pathname, navigate } = usePathname();
    const activePath = toolFor(pathname, TOOL_PATHS);
    // Until the redirect from `/` lands, the tool sees the path it is about to be at.
    const toolLocation = isToolPath(pathname, TOOL_PATHS) ? pathname : activePath;

    useEffect(() => {
        if (!isToolPath(pathname, TOOL_PATHS)) navigate(activePath, { replace: true });
    }, [pathname, activePath, navigate]);

    return (
        <AppShell navbar={{ width: NAVBAR_WIDTH, breakpoint: 0 }}>
            <ToolRail tools={TOOLS} activePath={activePath} onSelect={(path) => navigate(path)} />
            <AppShell.Main>
                {activePath === "/signals" ? <SignalsTool path={toolLocation} navigate={navigate} /> : <ReverseDcfTool />}
            </AppShell.Main>
        </AppShell>
    );
}
