import { SegmentedControl, Stack } from "@mantine/core";

import { FieldLabel } from "./FieldLabel";

interface ChoiceProps<T extends string | number> {
    label: string;
    options: readonly T[];
    value: T;
    onChange: (value: T) => void;
    render: (value: T) => string;
}

/** One of a few options, as a segmented control under a caption. */
export function Choice<T extends string | number>({ label, options, value, onChange, render }: ChoiceProps<T>) {
    return (
        <Stack gap={6}>
            <FieldLabel>{label}</FieldLabel>
            <SegmentedControl
                fullWidth
                aria-label={label}
                value={String(value)}
                data={options.map((option) => ({ value: String(option), label: render(option) }))}
                onChange={(next) => {
                    const chosen = options.find((option) => String(option) === next);
                    if (chosen !== undefined) onChange(chosen);
                }}
            />
        </Stack>
    );
}
