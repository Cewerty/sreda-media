# Официальные Agent Skills `django-modern-rest`

`.agents/skills/dmr*` — официальные скиллы, которые поставляются **внутри
пакета** `django-modern-rest` (`dmr/.agents/skills/`). Скопированы без изменений.

| | |
| --- | --- |
| Источник | `django-modern-rest==0.16.0` из корневого `uv.lock` |
| Путь в пакете | `.venv/Lib/site-packages/dmr/.agents/skills/` |
| Лицензия | MIT, © 2025 wemake-services — текст в [`LICENSE`](LICENSE) |
| Апстрим | <https://github.com/wemake-services/django-modern-rest> |
| Документация | <https://django-modern-rest.readthedocs.io/en/latest/pages/ai/agent-skills.html> |

Состав (6): `dmr`, `dmr-upgrade`, `dmr-openapi-skeleton`, `dmr-from-drf`,
`dmr-from-django-ninja`, `dmr-from-dj-rest-auth`.

## Почему копии, а не симлинки

Официальная команда `uvx library-skills` создаёт в `.agents/skills/`
**симлинки**, чтобы скиллы автоматически следовали за версией установленного
пакета. Рабочий диск проекта — exFAT, симлинки на нём не поддерживаются (то же
ограничение, что уже описано для pnpm в `docs/dhr-transfer.md` §6). Использован
штатный fallback из документации `library-skills`:

```bash
uvx library-skills --all -y --copy --no-tool-skill
```

Установка проверена: `scan` видит все 6 скиллов из uv-workspace, скопировано
34 файла; сверка по SHA-256 с файлами пакета — 34/34, расхождений 0. Файлы
пакета на Windows приходят с CRLF, а `.gitattributes` (`* text=auto eol=lf`)
нормализует их в LF при коммите: в Git лежит LF-версия того же содержимого.
OpenCode подхватывает все 6 скиллов из `.agents/skills/` сразу после установки.

**Нюанс, который надо знать:** скопированные каталоги `library-skills`
классифицирует как `hand-authored` и не обновляет и не удаляет их сам. Поэтому
`uvx library-skills --check` **не является** контролем рассинхрона версий для
нашего случая — версия фиксируется `uv.lock` и этим файлом.

## Обновление после апгрейда DMR

После смены версии `django-modern-rest` в `uv.lock`:

```bash
uv sync --all-packages
Remove-Item -Recurse -Force .agents/skills/dmr*
uvx library-skills --all -y --copy --no-tool-skill
```

Затем обновить версию в шапке этого файла и в `docs/dhr-transfer.md`, сверить
количество файлов и хеши с `.venv/Lib/site-packages/dmr/.agents/skills/`.
`README.md` и `LICENSE` в этом каталоге — наши, glob `dmr*` их не задевает.

## Использование

Формат `.agents/skills/` читают OpenCode, Codex, Cursor, GitHub Copilot и др.
Правила работы с ними для CMS-бэкенда — в [`apps/cms-api/AGENTS.md`](../../apps/cms-api/AGENTS.md).

Claude Code не читает `.agents/`: официальный путь — плагин из маркетплейса
(`/plugin marketplace add wemake-services/django-modern-rest`, затем
`/plugin install dmr@django-modern-rest`), либо `uvx library-skills --claude --copy`.

> Скиллы — помощник, а не источник решений. Официальная документация прямо
> требует ревью сгенерированного кода, проверки типов и тестов. При конфликте
> рекомендаций скилла с Accepted ADR и PRD приоритет у проекта (см. корневой
> `AGENTS.md`).
