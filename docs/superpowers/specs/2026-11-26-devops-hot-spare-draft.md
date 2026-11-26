# Spec: горячий точный дубль витрины (DRAFT, NOT-ENABLED)

## Статус

DRAFT / NOT-ENABLED. Документ описывает проект только как дизайн. Он **не**
включает деплой, DNS, алерты, `ENABLE_*`, второй сервер и автоматический
switchover. Решение о переводе в рабочую конфигурацию принимает Илья
(`@Cewerty`) после Q-1 и замера ресурсного gate ADR 0006 §4.

Ответственный за подготовку: Костя (`@Zisvit`), DevOps.

## Граница

В области này — только статический артефакт витрины. CMS, PostgreSQL,
очереди, media и миграции находятся в зоне Ильи (ADR 0008, ADR 0013,
ADR 0015) и явно попадают в `does_not_prove`.

Личный сервер автора не используется как площадка проекта. `/srv/sreda` —
целевой путь запланированного VPS, не объект удаления.

## Источник истины

Иммутабельная пара:

1. `commit` из git `main`.
2. `artifact_sha256` — канонический дайджест дерева артефакта,вычисленный
   `scripts/canonical_tree_digest.py` по сортированным относительным путям,
   режиму файла и symlink target.

Подпись (cosign) — необязательный слой. Отсутствие бинарника или ключа даёт
честный `SKIP` с `does_not_prove: ["authenticity/signature not verified"]`.
Запущенная и провалившаяся проверка даёт `FAIL`. `cosign_verified=true` без
реального вызова проверки запрещено.

## Синхронизация

* Один publisher, который публикует один и тот же артефакт.
* Standby выполняет **pull по каноническому digest**, не получает
  write-доступа из CI и не пересобирает артефакт.
* Активация — atomic swap симлинка `current` на новую generation.
* Предыдущая generation сохраняется; `.last` и last-verified удалять
  запрещено (защита: `scripts/retention_guard.py`).
* Standby остаётся read-only до ручного promotion.

## Проверка равенства

Равенство доказывается только при совпадении:

* `commit`;
* `artifact_sha256` / canonical tree digest;
* per-file SHA-256 и symlink target;
* байты ответа (decoded body), а не заголовки, gzip или chunked transfer;
* TTL контракта не истёк.

Контракт формируется `scripts/emit_drill_contract.py` и проверяется
`scripts/verify_drill_contract.py`. Exit-коды: `0` PASS, `3` NO-GO
(обязательный SKIP, истёкший TTL, чужой commit), `1` FAIL (невалидный
контракт или проваленная проверка). `SKIP` никогда не превращается в `PASS`.

## Switchover и split-brain

* Переключение — только вручную, с `CONFIRM=1` и повторной верификацией
  commit/digest/TTL непосредственно перед активацией.
* Старый primary сначала переводится в read-only; автоматический failback
  запрещён.
* Узел без lease не отвечает на публичный hostname. Lease/fencing — только
  в этой спецификации, без запущенного арбитра до Q-1 и §4.
* При расхождении digest между узлами — NO-GO, а не перезапись и не
  автослияние.

## RPO / RTO

* Статика: RPO равен интервалу публикации и успешной проверки.
* RTO не заявлен числом: до реального DRM-дриля и низкого DNS TTL он
  остаётся `SKIP` / NOT-MEASURED.
* CMS/БД: RPO и RTO не заявляются там, где нет синхронной репликации и
  согласованного решения Ильи.

## Ресурсный gate

По ADR 0006 §4 текущий бюджет — 0₽ и 0 дополнительного RAM без решения
Ильи. Второй VPS означает примерно удвоение платежа (~500₽/мес) плюс
трафик, хранилище и DNS с низким TTL. Пока замеры и одобрение отсутствуют,
результат resource gate — `SKIP`, а не PASS.

## Что доказывается и что нет

| Проверка | proves | does_not_prove |
| --- | --- | --- |
| `drill-contract` | честная агрегация PASS/SKIP/FAIL, TTL, commit | реальный cutover, доступность |
| `canonical-tree-digest` | равенство байтов артефакта на двух узлах | корректность контента и CMS |
| `retention-guard` | `.last` и минимум наборов сохраняются | успешность реального restore |
| `verify-artifact` (существующий) | целостность архива | подлинность без cosign |

## Проверки перед включением

```bash
python3 scripts/emit_drill_contract.py unit --artifact-sha256 "$(printf a%.0s {1..64})" \
  --checks <checks.json> --out <contract.json>
python3 scripts/verify_drill_contract.py <contract.json>
python3 scripts/canonical_tree_digest.py dist
python3 scripts/retention_guard.py <backup-dir>
python3 scripts/test_drill_contract.py
git diff --name-only
```

Последняя команда обязана содержать только разрешённые зоны Кости. Строка
`verify` в `justfile` и `ci.yml` остаются байт-в-байт неизменными.

@241@
