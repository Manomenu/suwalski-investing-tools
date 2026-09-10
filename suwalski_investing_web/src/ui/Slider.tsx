interface SliderProps {
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
export function Slider({ label, value, min, max, step, onChange, format, hint }: SliderProps) {
    return (
        <label className="block">
            <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-semibold tracking-wide text-subtext0 uppercase">{label}</span>
                <span className="text-lg font-semibold font-mono tabular-nums text-text">{format(value)}</span>
            </div>
            <input
                type="range"
                className="mt-2 w-full"
                value={value}
                min={min}
                max={max}
                step={step}
                onChange={(event) => onChange(Number(event.target.value))}
            />
            {hint ? <p className="mt-1.5 text-sm leading-snug text-overlay0">{hint}</p> : null}
        </label>
    );
}
