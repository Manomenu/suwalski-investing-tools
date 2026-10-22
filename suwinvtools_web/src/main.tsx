import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@mantine/core/styles.css";

import { MantineProvider, createTheme } from "@mantine/core";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const theme = createTheme({
    // Close to the mauve of the former palette.
    primaryColor: "violet",
    defaultRadius: "md",
    // Inter carries the UI; JetBrains Mono carries every figure, so columns of numbers line up.
    fontFamily: '"Inter Variable", system-ui, -apple-system, sans-serif',
    fontFamilyMonospace: '"JetBrains Mono Variable", ui-monospace, monospace',
});

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

createRoot(root).render(
    <StrictMode>
        <MantineProvider theme={theme} defaultColorScheme="dark">
            <App />
        </MantineProvider>
    </StrictMode>,
);
