# Публичная витрина Sreda Media

Статический сайт на Astro 6. Материалы лежат в [`src/content/articles`](src/content/articles), а коллекция и правила проверки полей определены в [`src/content.config.ts`](src/content.config.ts).

Для разработки нужны Node.js 22.12 или новее (поддерживаемая чётная версия) и pnpm 12.23.0, указанный в корневом `package.json`. Выполнение команды из корня репозитория.

```bash
pnpm install --frozen-lockfile
pnpm --filter site dev
```

Адрес для просмотра появится в терминале. Чтобы собрать статические страницы в `apps/site/dist`:

```bash
pnpm --filter site build
```

Команда `just build-site` сначала проверяет материалы, затем собирает сайт. Её использует CI.

Проверить форматирование без изменения файлов можно командой `pnpm --filter site format:check`. Чтобы применить форматирование `pnpm --filter site format`.

✌️
