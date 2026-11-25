# Локальная наблюдаемость для разработчиков

Небольшой контур Loki + Alloy + Grafana для локальной проверки контракта логов ADR 0005. Он **не мешает** основным сервисам: использует высокие порты, отдельные volume и не монтирует системные логи.

## Что не трогается

- Продакшен-стек `deploy/observability/docker-compose.yml` не изменяется.
- Порты `3000` (Grafana prod), `3100` (Loki prod), `12345` (Alloy prod) и `3001` (Uptime Kuma) не используются.
- Не монтируются `/var/log/caddy` и `/var/lib/docker/containers`.
- `serv` и любые внешние серверы не используются.

## Порты

| Сервис | Адрес |
| --- | --- |
| Grafana | http://127.0.0.1:13000 |
| Loki | http://127.0.0.1:13100 |
| Alloy | http://127.0.0.1:13345 |

## Запуск

```bash
GRAFANA_ADMIN_PASSWORD=dev-only \
  docker compose -f deploy/dev/docker-compose.yml up -d
```

Данные для проверки берутся из `docs/examples/logs/*.jsonl` — те же файлы, которые проверяет `just check-logs`. После запуска в Grafana доступен датасорс Loki и дашборд `Sreda overview`.

Остановка без удаления данных:

```bash
docker compose -f deploy/dev/docker-compose.yml down
```

Полная очистка локального стека:

```bash
docker compose -f deploy/dev/docker-compose.yml down -v
```

## Проверка контракта

```bash
uvx --from rust-just just check-logs
uvx --from rust-just just backup-drill
```

`backup-drill` работает в `DRY_RUN=1` и во временном каталоге: не требует PostgreSQL, Docker-демона и внешних путей.
