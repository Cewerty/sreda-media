-- Структурированные события и артефакты выкладки (ADR 0005, ADR 0015).
-- Приложение НЕ пишет сюда напрямую: логи идут в stdout -> Alloy -> Loki.
-- В SQL попадают только отобранные операционные события (деплой, CI, backup),
-- которые удобно запросить как таблицу и включить в отчёт/аудит.

CREATE TABLE IF NOT EXISTS structured_events (
    id             bigserial PRIMARY KEY,
    ts             timestamptz NOT NULL DEFAULT now(),
    environment    text NOT NULL,
    component      text NOT NULL,
    event          text NOT NULL,
    operation      text,
    outcome        text,
    release        text,
    correlation_id text,
    elapsed_ms     integer,
    payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Высококардинальные значения остаются в payload; индексируем только то,
    -- что реально используется в фильтрах дашбордов и отчётов.
    http_status    integer GENERATED ALWAYS AS (NULLIF(payload ->> 'http_status', '')::integer) STORED
);

CREATE INDEX IF NOT EXISTS structured_events_ts_idx ON structured_events (ts DESC);
CREATE INDEX IF NOT EXISTS structured_events_component_event_idx
    ON structured_events (component, event, ts DESC);
CREATE INDEX IF NOT EXISTS structured_events_outcome_idx
    ON structured_events (outcome, ts DESC) WHERE outcome IS NOT NULL;
CREATE INDEX IF NOT EXISTS structured_events_correlation_idx
    ON structured_events (correlation_id) WHERE correlation_id IS NOT NULL;

COMMENT ON TABLE structured_events IS
    'Структурированные операционные события по контракту ADR 0005; PII не сохраняется.';

CREATE TABLE IF NOT EXISTS deploy_events (
    id            bigserial PRIMARY KEY,
    started_at    timestamptz NOT NULL,
    finished_at   timestamptz,
    environment   text NOT NULL,
    revision      text NOT NULL,
    artifact_sha  text,
    action        text NOT NULL CHECK (action IN ('deploy', 'rollback')),
    outcome       text NOT NULL CHECK (outcome IN ('success', 'failure')),
    previous_path text,
    details       jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS deploy_events_started_idx ON deploy_events (started_at DESC);
CREATE INDEX IF NOT EXISTS deploy_events_revision_idx ON deploy_events (revision, started_at DESC);

COMMENT ON TABLE deploy_events IS
    'Журнал выкладок и откатов по ADR 0015: неизменяемые релизы и атомарный symlink.';

-- Отдельный只读 пользователь для Grafana создаётся на VPS, не в репозитории.
-- CREATE ROLE grafana LOGIN PASSWORD '...';
-- GRANT SELECT ON structured_events, deploy_events TO grafana;
