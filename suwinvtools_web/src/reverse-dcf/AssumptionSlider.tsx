import { Group, Slider, Stack, Text } from "@mantine/core";

import { FieldLabel } from "./FieldLabel";

interface AssumptionSliderProps {
    label: string;
    value: number;
    min: number;
    max: number;
    step: number;
    onChange: (value: number) => void;
    format: (value: number) => string;
    hint?: string;
}

/** Label, live value, track. The hint says what the number means to an investor —
 *  the same job the CLI's --help does. */
export function AssumptionSlider({ label, value, min, max, step, onChange, format, hint }: AssumptionSliderProps) {
    return (
        <Stack gap={6}>
            <Group justify="space-between" align="baseline" wrap="nowrap">
                <FieldLabel>{label}</FieldLabel>
                <Text ff="monospace" fw={600} size="lg">
                    {format(value)}
                </Text>
            </Group>
            <Slider value={value} min={min} max={max} step={step} onChange={onChange} label={null} thumbLabel={label} aria-label={label} />
            {hint ? (
                <Text size="sm" c="dimmed" lh={1.35}>
                    {hint}
                </Text>
            ) : null}
        </Stack>
    );
}
