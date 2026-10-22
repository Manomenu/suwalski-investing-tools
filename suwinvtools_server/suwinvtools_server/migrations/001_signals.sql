-- The AI cycle signals: what each check read, what it concluded, and every run of the job.

CREATE TABLE signal_readings (
    check_id text NOT NULL,
    subject text NOT NULL,
    period text NOT NULL,
    value double precision,
    data jsonb NOT NULL DEFAULT '{}',
    evidence jsonb NOT NULL DEFAULT '[]',
    read_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (check_id, subject, period)
);

-- One row per check, subject and period: the latest verdict on it. notified_at says whether
-- that verdict reached Discord; a changed verdict (unconfirmed -> red) is sent again.
CREATE TABLE signal_outcomes (
    check_id text NOT NULL,
    subject text NOT NULL,
    period text NOT NULL,
    verdict text NOT NULL,
    summary text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]',
    details jsonb NOT NULL DEFAULT '{}',
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    notified_at timestamptz,
    PRIMARY KEY (check_id, subject, period)
);

CREATE INDEX signal_outcomes_recent ON signal_outcomes (evaluated_at DESC);

CREATE TABLE signal_runs (
    id bigserial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    dry_run boolean NOT NULL,
    counts jsonb NOT NULL DEFAULT '{}'
);
