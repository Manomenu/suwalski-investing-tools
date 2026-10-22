import { Text, type TextProps } from "@mantine/core";
import type { ReactNode } from "react";

/** The small uppercase caption above a control. */
export function FieldLabel({ children, ...props }: { children: ReactNode } & TextProps) {
    return (
        <Text size="xs" fw={600} tt="uppercase" c="dimmed" lts="0.05em" {...props}>
            {children}
        </Text>
    );
}
