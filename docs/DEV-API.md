# Локальный PostgreSQL для CMS API

`just verify` включает полный гейд CMS API из `apps/cms-api/justfile`. Ему нужен PostgreSQL 18 с базой/пользователем `sreda`. Раньше контейнер приходилось поднимать руками; теперь это делает рецепт `just api-db-up`.

## Запуск

```bash
just api-db-up      # postgres:18-alpine на 127.0.0.1:55432
just verify         # внутри api-check используется POSTGRES_PORT=55432
just api-db-down    # остановить и удалить контейнер
```

Контейнер описан в `deploy/dev/postgres.yml`. Он слушает порт **55432**, чтобы не конфликтовать с basic-стеком на 5432, и не трогает продовую базу. В CI рецепт `api-db-up` ничего не поднимает: там используется сервис PostgreSQL на 5432 из `cms-api.yml`.

Если docker недоступен, рецепт честно пишет предупреждение, а `verify` упадёт на тестах CMS API — это ожидаемо, без иллюзии зелёного прогона.
