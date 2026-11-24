# Ротация секретов

Документ описывает порядок ротации секретов, которые живут **вне репозитория**. В репозитории хранятся только шаблоны (`.env.example`, `deploy/observability/.env.example`) и ссылки на переменные окружения.

## Что ротировать

- GitHub PAT в `/home/deb/.config/opencode/kilo.jsonc` (вне репозитория, зона владельца).
- `GRAFANA_ADMIN_PASSWORD`, `POSTGRES_GRAFANA_PASSWORD`, `POSTGRES_OBSERVABILITY_PASSWORD`.
- `GRAFANA_TELEGRAM_BOT_TOKEN`, `GRAFANA_TELEGRAM_CHAT_ID`.
- Токен Uptime Kuma (`UPTIME_KUMA_TOKEN`) и URL (`UPTIME_KUMA_URL`).

## Порядок

1. Создать новый секрет в issuers' системе, не переиспользуя старый.
2. Записать его в окружение VPS / systemd credentials, а не в файлы репозитория.
3. Обновить значение в `deploy/observability/.env` (файл игнорируется git).
4. Перезапустить только Depends-on сервисы (Grafana/Alloy/Loki), не убивая чужие процессы.
5. Проверить `just obs-health`, `just check-alerts`, `just check-uptime`.
6. Отозвать старый секрет и зафиксировать дату ротации здесь.

## Проверки

`just secrets` (gitleaks по всей истории) и `scripts/pre-commit.sh` не заменяют ротацию: они находят утечки в git, но не проверяют срок жизни секрета.

## История ротации

- Записи добавлять вручную с датой и типом секрета, без самих значений.
