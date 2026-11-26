# Sreda Media

> Медиа-клуб колледжа: публичная статическая витрина, микро-CMS и Telegram-бот.
> Документация, архитектурные решения и эксплуатационные процедуры — в [docs](docs/index.md).

[PRD](docs/prd.md) · [Архитектура](docs/architecture.md) · [Дорожная карта](docs/roadmap.md) · [Runbook](docs/runbook.md) · [Мониторинг](docs/monitoring.md)

## Быстрый старт

```bash
just api-db-up   # локальный PostgreSQL 18 для CMS API, если нужен полный гейд
just verify      # все обязательные проверки
just api-db-down # остановить временный контейнер
```

Подробности — в [CONTRIBUTING.md](CONTRIBUTING.md).

---

## DevOps — текущий статус

> [!NOTE]
> **Ветка:** `observability/foundation` · **Обновлено:** 25.11.2026 · **Ответственный:** Костян (Zisvit)

| Коммит | Что сделано |
| --- | --- |
| `0816aca` | Отдельная страница статуса с картой проверок и зависимостями |
| `b3651cc` | Deploy workflow как код, smoke, еженедельный alert-drill, Docker lint, Dependency Review и OSV |
| `3c631b7` | Кеши CI-инструментов, coverage, link checker, валидация Uptime Kuma, `pre-commit`, `verify-artifact` |
| `6a1f51c` | Uptime Kuma как код, restore-drill, Lighthouse-заготовка, безопасный Trivy v0.35.0 |

**Подробная страница:** [docs/DEVOPS-STATUS.md](docs/DEVOPS-STATUS.md) — карта проверок, локальные команды, таблица «подготовлено, но не включено», блокирующие зависимости и идеи на потом.

> [!IMPORTANT]
> Реальная выкладка, публикация документации и внешние алерты намеренно выключены до появления сайта в `main` (PR #16) и тестового адреса (Q-1).
