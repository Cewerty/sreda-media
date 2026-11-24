# Runbook — эксплуатация Sreda Media

Документ для дежурного. Актуальная версия: этап 0.1 (статическая витрина).
Основание: ADR 0006 (VPS + Caddy), ADR 0015 (Runtime and Data Operations), issues #7, #9, #14.

## 1. Состав и адреса

- Публичный адрес (после Q-1): `https://sreda.sielom.ru`.
- До разрешения Q-1 используется тестовый адрес, выданный для демо. Он фиксируется в конфиге Caddy и передаётся команде отдельно.
- Caddy раздаёт симлинк `/srv/sreda/current`, который указывает на неизменяемый каталог `/srv/sreda/releases/<UTC-метка>`.
- `/srv/sreda/releases/.previous` хранит путь к предыдущему рабочему релизу.

Секреты и токены не хранятся в репозитории. Ответственный за доступы — Костя (Zisvit).

## 2. Проверка перед выкладкой

На чистом checkout:

```bash
uvx --from rust-just just build-site
```

Команда проверяет контракт ADR 0014, валидирует материалы и медиа (`just check-content`) и собирает Astro, когда `apps/site` присутствует в main (PR #16). В CI те же шаги выполняются через `site-build` и итоговый статус `ci`.

## 3. Выкладка

```bash
just build-site
scripts/deploy-static.sh deploy dist /srv/sreda/releases /srv/sreda/current
scripts/deploy-static.sh verify https://sreda.sielom.ru
```

Скрипт отказывается выкладывать артефакт без `index.html` и `404.html`, копирует его в новый каталог с UTC-меткой и только после проверки состава переключает symlink атомарно. Caddy продолжает раздавать прежний каталог, пока переключение не завершено.

## 4. Откат

```bash
scripts/deploy-static.sh rollback /srv/sreda/releases /srv/sreda/current
scripts/deploy-static.sh verify https://sreda.sielom.ru /srv/sreda/releases/<предыдущий>
```

Откат — это переключение symlink на предыдущий релиз, этот каталог не пересобирается. Если previous-указателя нет, скрипт останавливается с ошибкой: в таком случае используется список `/srv/sreda/releases` и ручное переключение с фиксацией действия в журнале инцидента.

## 5. Признаки инцидента

- Uptime Kuma сообщает о недоступности (или, наоборот, о восстановлении) публичной витрины.
- `verify` возвращает код отличный от 200 для главной или отличный от 404 для несуществующей страницы.
- Пользователи сообщают об устаревшем содержимом после выкладки.

## 6. Реагирование

1. Зафиксировать время, адрес и симптом; открыть карточку инцидента.
2. Проверить, что `current` указывает на ожидаемый релиз: `readlink /srv/sreda/current`.
3. Проверить главную и 404 через `scripts/deploy-static.sh verify ...`.
4. При подозрении на плохой артефакт выполнить откат по §4.
5. При недоступности VPS целиком — использовать независимую точку проверки (внешний мониторинг); она ещё не настроена, это открытая зависимость этапа 0.1 (#14).
6. После восстановления записать причину, действие и время восстановления в карточку.

## 7. Мониторинг (этап 0.1, план)

Целевой стек: Uptime Kuma для HTTP(S)-проверки витрины и уведомлений в Telegram; Grafana + Alloy + Loki для логов, GlitchTip для исключений (#14). На текущем этапе рабочий сайт/тестовый адрес ещё не зафиксирован, поэтому конкретные URL и порты в этот runbook не вписываются до завершения Q-1.

Базовый контур логирования **включён по умолчанию**: Loki + Alloy + Grafana
поднимаются из `deploy/observability/docker-compose.yml` без дополнительных
профилей. Alloy собирает Caddy и Docker stdout без сэмплирования; локальная разработка
и CI этого compose не требуют. Prometheus, node_exporter, PostgreSQL и GlitchTip остаются
под profiles. Схема SQL — `deploy/observability/schema.sql`, дашборд —
`deploy/observability/grafana-dashboards/overview.json`, контракт логов проверяется
через `just check-logs` (входит в `just check` в CI). Решение по Kafka и триггеры
его возврата описаны в ADR 0005. `serv` не используется. В проде переопределяем
секреты через env.

Grafana provisioning лежит строго в подпапках
`deploy/observability/grafana-provisioning/{datasources,dashboards,alerting}/`.
Правила в `alerting/rules.yml` и контакт `alerting/contact-points.yml` подготовлены,
но все правила имеют label `enabled="false"` и не попадают под маршрут из
`alerting/policies.yml`, поэтому уведомлений нет. Включение алертов — после PR #16
и Q-1: заменить label на `enabled="true"` и задать `GRAFANA_TELEGRAM_CHAT_ID`
и `GRAFANA_TELEGRAM_BOT_TOKEN` переменными окружения на VPS. Provisioned-ресурсы
редактируются только в этих файлах, не в UI Grafana.

При настройке мониторинга обязательны: дедупликация уведомлений, защита от alert storm, проверка восстановления после недоступности, документирование ограничения при падении VPS и фактические расходы (память/CPU/диск/стоимость).

## 8. Резервное копирование и восстановление (этап 0.2)

Бэкап операционных событий PostgreSQL и пользовательских данных Grafana:

```bash
BACKUP_DIR=/srv/sreda/backups just backup-obs
```

Скрипт `scripts/backup-observability.sh` снимает `pg_dump` (профиль `sql` должен быть поднят) и tar volume Grafana, проверяет сжатие и пишет манифест SHA256 с UTC-меткой. Устаревшие копии удаляются по `RETENTION_DAYS` (по умолчанию 14 дней). Loki не копируется: логи имеют собственный retention 30 дней, восстановление логов не предусмотрено. Рецепты `backup-obs`/`restore-obs` намеренно не входят в `just verify`.

Восстановление по UTC-метке из имени файла:

```bash
CONFIRM=1 just restore-obs <UTC-метка>
```

Скрипт `scripts/restore-observability.sh` сверяет манифест, перезаписывает таблицы SQL, останавливает Grafana, распаковывает volume и поднимает сервис обратно. Только SQL можно восстановить командой `CONFIRM=1 ./scripts/restore-observability.sh <UTC-метка> --sql-only`. Без `CONFIRM=1` скрипт отказывается; репетицию делать на тестовом окружении до боевого применения.

## 9. Открытые зависимости

- Q-1 с Артёмом — финальный домен и адрес выкладки.
- PR #16 — собираемый Astro-сайт в main.
- #14 — мониторинг, уведомления, Grafana/Alloy/Loki, GlitchTip, backup/restore.
- #41 — конфигурация Django для `deploy-strict` (относится к CMS, не к витрине).
