import { useState } from "react";

import { TOOLS } from "./tools";

export function App() {
    const [activeId, setActiveId] = useState(TOOLS[0]!.id);
    const active = TOOLS.find((tool) => tool.id === activeId) ?? TOOLS[0]!;
    const Tool = active.component;

    return (
        <div className="grid h-full grid-cols-[15rem_1fr]">
            <nav className="flex flex-col gap-1 overflow-y-auto border-r border-surface0 bg-crust p-3">
                {TOOLS.map((tool) => {
                    const selected = tool.id === active.id;
                    return (
                        <button
                            key={tool.id}
                            type="button"
                            onClick={() => setActiveId(tool.id)}
                            aria-current={selected ? "page" : undefined}
                            className={`rounded-md px-3 py-2 text-left transition-colors ${
                                selected ? "bg-surface0 text-text" : "text-subtext0 hover:bg-mantle hover:text-text"
                            }`}
                        >
                            <span className="block text-base font-semibold">{tool.name}</span>
                            <span className="block text-sm text-overlay0">{tool.blurb}</span>
                        </button>
                    );
                })}
            </nav>
            <main className="min-h-0 min-w-0 overflow-hidden">
                <Tool />
            </main>
        </div>
    );
}
