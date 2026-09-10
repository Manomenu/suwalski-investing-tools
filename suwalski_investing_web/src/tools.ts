import type { ComponentType } from "react";

import { ReverseDcfTool } from "./tools/reverse-dcf/ReverseDcfTool";

export interface Tool {
    id: string;
    name: string;
    blurb: string;
    component: ComponentType;
}

/** Adding a tool is one entry here plus its component — the shell needs no changes. */
export const TOOLS: Tool[] = [
    {
        id: "reverse-dcf",
        name: "Reverse DCF",
        blurb: "growth the price implies",
        component: ReverseDcfTool,
    },
];
